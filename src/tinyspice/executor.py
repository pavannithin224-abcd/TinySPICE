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
from tinyspice.schemas import DeviceLimits, ExperimentSpec, ExperimentStatus
from tinyspice.simulator.base import SimResult, Simulator


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

    sim = simulator.run(spec, run_dir / "sim")
    _dump(run_dir / "result.json", {
        "ok": sim.ok, "error_code": sim.error_code, "error_detail": sim.error_detail, "exit_code": sim.exit_code,
        "runtime_s": sim.runtime_s, "simulator": simulator.name, "simulator_version": sim.simulator_version,
        "points": None if sim.x is None else int(len(sim.x)), "meta": sim.meta,
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


def _solver_floor(spec: ExperimentSpec, sim: SimResult) -> float | None:
    """gmin * |VDS| from the recorded solver options: the current floor the simulator itself puts under Id."""
    m = re.search(r"gmin=([0-9.eE+\-]+)", (sim.meta or {}).get("solver_options", ""))
    vds = spec.vds_v
    return float(m.group(1)) * abs(vds) if (m and vds is not None) else None
