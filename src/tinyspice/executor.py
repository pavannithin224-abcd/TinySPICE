"""Minimal executor: validated spec -> deterministic plan -> simulator -> honest status + run directory.

Stage-1 scope. Measurement extraction does not exist yet, so a validated simulation can only reach
PARTIAL: SUCCESSFUL requires validated output AND successful extraction of every requested measurement.
Recovery, runtime budget enforcement and the SQLite store are later stages.
"""
from __future__ import annotations

import datetime as dt
import json
import uuid
from dataclasses import dataclass
from pathlib import Path

from tinyspice.errors import PlanRejected
from tinyspice.planner import ExecutionPlan, build_plan
from tinyspice.planner.planner import spec_hash
from tinyspice.schemas import DeviceLimits, ExperimentSpec, ExperimentStatus
from tinyspice.simulator.base import SimResult, Simulator

MEASUREMENTS_IMPLEMENTED = False  # flipped in Stage 2; until then SUCCESSFUL is unreachable by construction


@dataclass(frozen=True)
class RunRecord:
    run_id: str
    status: ExperimentStatus
    message: str
    plan: ExecutionPlan | None = None
    sim: SimResult | None = None
    run_dir: Path | None = None
    error_code: str | None = None


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
    if not MEASUREMENTS_IMPLEMENTED:
        return RunRecord(run_id, ExperimentStatus.PARTIAL,
                         "simulation validated; measurement extraction not implemented yet (Stage 2)",
                         plan, sim, run_dir)
    raise NotImplementedError("wire measurement extraction here in Stage 2")  # pragma: no cover
