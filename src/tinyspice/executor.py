"""Minimal executor: validated spec -> deterministic plan -> simulator -> honest status + run directory.

Stage-1 scope. Measurement extraction does not exist yet, so a validated simulation can only reach
PARTIAL: SUCCESSFUL requires validated output AND successful extraction of every requested measurement.
Recovery, runtime budget enforcement and the SQLite store are later stages.
"""
from __future__ import annotations

import datetime as dt
import json
import re
import uuid
from dataclasses import dataclass
from pathlib import Path

from tinyspice.errors import PlanRejected
from tinyspice.measurements import MeasurementResult, extract_all
from tinyspice.planner import ExecutionPlan, build_plan
from tinyspice.planner.planner import spec_hash
from tinyspice.sampling import pilot_base, pilot_grid, refine_points, uniform_grid
from tinyspice.schemas import DeviceLimits, ExperimentSpec, ExperimentStatus
from tinyspice.simulator.base import SimResult, Simulator

import numpy as np


@dataclass(frozen=True)
class RunRecord:
    run_id: str
    status: ExperimentStatus
    message: str
    plan: ExecutionPlan | None = None
    sim: SimResult | None = None
    run_dir: Path | None = None
    error_code: str | None = None
    measurements: dict[str, MeasurementResult] | None = None


def new_run_id(spec: ExperimentSpec) -> str:
    ts = dt.datetime.now(dt.timezone.utc).strftime("%Y%m%dT%H%M%S")
    return f"{ts}_{spec_hash(spec)[:8]}_{uuid.uuid4().hex[:4]}"


def _dump(path: Path, obj) -> None:
    path.write_text(json.dumps(obj, indent=2, sort_keys=True, default=str), encoding="utf-8", newline="\n")


def execute(spec: ExperimentSpec, limits: DeviceLimits, simulator: Simulator, runs_root: Path,
            strategy: str = "uniform") -> RunRecord:
    run_id = new_run_id(spec)
    try:
        plan = build_plan(spec, limits, strategy)
    except PlanRejected as e:
        return RunRecord(run_id, e.status, e.message, error_code=e.code)

    run_dir = Path(runs_root) / run_id
    run_dir.mkdir(parents=True, exist_ok=False)  # unique id; never overwrite an earlier experiment
    _dump(run_dir / "spec.json", spec.model_dump(mode="json"))
    _dump(run_dir / "plan.json", plan.model_dump(mode="json"))

    sim = run_sweep(spec, simulator, run_dir, strategy)
    _dump(run_dir / "result.json", {
        "ok": sim.ok, "error_code": sim.error_code, "error_detail": sim.error_detail, "exit_code": sim.exit_code,
        "runtime_s": sim.runtime_s, "simulator": simulator.name, "simulator_version": sim.simulator_version,
        "points": None if sim.x is None else int(len(sim.x)), "meta": sim.meta, "strategy": strategy,
    })
    if not sim.ok:
        return RunRecord(run_id, ExperimentStatus.FAILED, f"{sim.error_code}: {sim.error_detail}",
                         plan, sim, run_dir, sim.error_code)

    meas = extract_all(spec, sim.x, sim.y, floor_a=_solver_floor(spec, sim))
    _dump(run_dir / "measurements.json", {k: v.to_dict() for k, v in meas.items()})
    bad = {k: v.error_code for k, v in meas.items() if not v.ok}
    if not bad:
        return RunRecord(run_id, ExperimentStatus.SUCCESSFUL, f"{len(meas)} measurement(s) extracted from validated output",
                         plan, sim, run_dir, measurements=meas)
    if len(bad) == len(meas):
        return RunRecord(run_id, ExperimentStatus.FAILED, f"every measurement failed: {bad}", plan, sim, run_dir,
                         "MEASUREMENT_FAILED", meas)
    return RunRecord(run_id, ExperimentStatus.PARTIAL, f"simulation validated; failed measurements: {bad}",
                     plan, sim, run_dir, "MEASUREMENT_PARTIAL", meas)


PILOT_FRAC = 0.3


def run_sweep(spec: ExperimentSpec, simulator: Simulator, run_dir: Path, strategy: str = "uniform",
              pilot_frac: float = PILOT_FRAC) -> SimResult:
    """Run the sweep under a sampling strategy; ALWAYS spends exactly spec.sweep.n_points simulated points (never more).
      uniform      - the spec's own uniform dc sweep (1 process)
      uniform_pwl  - BENCHMARK ONLY: the same uniform points through the explicit-point path, so uniform and curvature
                     share the identical ngspice mechanism
      curvature    - pilot (coarse uniform + forced ION/IOFF bias points), then ONLY the remaining points placed by
                     log10(Id) curvature of the pilot (2 processes)."""
    n = spec.sweep.n_points
    if strategy == "uniform":
        return simulator.run(spec, run_dir / "sim")
    if strategy == "uniform_pwl":
        return simulator.run(spec, run_dir / "sim", points=uniform_grid(spec.sweep.start, spec.sweep.stop, n))
    if strategy != "curvature":
        raise ValueError(f"unknown strategy {strategy!r}")
    forced = [v for v in (spec.ion_vgs_v, spec.ioff_vgs_v) if v is not None]
    pilot = pilot_grid(spec.sweep.start, spec.sweep.stop, pilot_base(n, len(forced), pilot_frac), forced)
    if n - len(pilot) == 1:                       # a 1-point explicit run is undefined: fold it into the pilot grid
        pilot = pilot_grid(spec.sweep.start, spec.sweep.stop, pilot_base(n, len(forced), pilot_frac) + 1, forced)
    s1 = simulator.run(spec, run_dir / "sim_pilot", points=pilot)
    if not s1.ok:
        return s1
    n_new = n - len(pilot)
    try:
        new = refine_points(s1.x, s1.y, n_new) if n_new > 0 else np.array([])
    except ValueError as e:
        return SimResult(ok=False, error_code="SAMPLING_ERROR", error_detail=str(e), meta=s1.meta,
                         simulator_version=s1.simulator_version, runtime_s=s1.runtime_s)
    phases = [{"phase": "pilot", "points": int(len(pilot)), "runtime_s": s1.runtime_s}]
    x, y, runtime = s1.x, s1.y, s1.runtime_s
    if len(new) > 0:
        s2 = simulator.run(spec, run_dir / "sim_refine", points=new)
        if not s2.ok:
            return s2
        order = np.argsort(np.concatenate([s1.x, s2.x]))
        x, y = np.concatenate([s1.x, s2.x])[order], np.concatenate([s1.y, s2.y])[order]
        runtime += s2.runtime_s
        phases.append({"phase": "refine", "points": int(len(new)), "runtime_s": s2.runtime_s})
    if len(x) > n or not (np.diff(x) > 0).all():  # never exceed the point budget, never hand on a non-monotone axis
        return SimResult(ok=False, error_code="SAMPLING_ERROR", meta=s1.meta, simulator_version=s1.simulator_version,
                         error_detail=f"merged sweep invalid: {len(x)} points (budget {n}), monotone={bool((np.diff(x) > 0).all())}")
    return SimResult(ok=True, x=x, y=y, runtime_s=runtime, simulator_version=s1.simulator_version, netlist_path=s1.netlist_path,
                     raw_path=s1.raw_path, meta={**s1.meta, "strategy": "curvature", "phases": phases,
                                                "points_requested": n, "points_simulated": int(len(x))})


def _solver_floor(spec: ExperimentSpec, sim: SimResult) -> float | None:
    """gmin * |VDS| from the recorded solver options: the current floor the simulator itself puts under Id."""
    m = re.search(r"gmin=([0-9.eE+\-]+)", (sim.meta or {}).get("solver_options", ""))
    vds = spec.vds_v
    return float(m.group(1)) * abs(vds) if (m and vds is not None) else None
