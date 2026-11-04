"""Reliable experiment runner: validated spec -> plan -> budgeted, recoverable simulation -> honest status -> provenance record.

Everything here is deterministic code. The LLM never reaches this layer. See tests/benchmark/stage5_injection_expected.json
for the pre-registered counting rules and the expected status of every injected fault.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

import numpy as np

from tinyspice.budget import BudgetExceeded, BudgetLedger
from tinyspice.errors import PlanRejected
from tinyspice.executor import _dump, _solver_floor, new_run_id, run_sweep
from tinyspice.measurements import MeasurementResult, extract_all
from tinyspice.planner import build_plan
from tinyspice.planner.planner import spec_hash
from tinyspice.provenance import ProvenanceStore, git_state, utc_now, write_manifest
from tinyspice.recovery import SOLVER_LADDER, SS_REFUSAL_CODES, classify
from tinyspice.sampling import window_points
from tinyspice.schemas import DeviceLimits, ExperimentSpec, ExperimentStatus
from tinyspice.simulator.base import SimResult, Simulator
from tinyspice.status import check_evidence, final_status

REPO = Path(__file__).resolve().parents[2]
SS_RECOVERY_TARGET = 6          # points guaranteed inside the SS window by measurement-level recovery
SS_RECOVERY_MAX_NEW = 12


@dataclass
class RunResult:
    run_id: str
    status: ExperimentStatus
    message: str
    events: list[dict]
    recovery_chain: list[str]
    retries_used: int
    budget: dict
    measurements: dict[str, MeasurementResult] | None
    sim: SimResult | None
    run_dir: Path | None
    flags: list[str] = field(default_factory=list)
    n_points: int = 0


def _pre_check(ledger: BudgetLedger, calls: int) -> None:
    """Would the next action fit? Raises BudgetExceeded WITHOUT mutating the ledger."""
    ledger.check_deadline()
    if ledger.tool_calls + calls > ledger.max_tool_calls - 1:
        raise BudgetExceeded("tool_calls", f"{calls} more would exceed {ledger.max_tool_calls} (1 reserved for persistence)")


def _defaults(spec: ExperimentSpec, strategy: str, pilot_frac: float, window_target: int) -> list[tuple]:
    out = []
    for f in ("vbs_v", "vth_ic_a", "output_format"):
        if f not in spec.model_fields_set:
            out.append((f, getattr(spec, f), "documented default"))
    for f in ("max_runtime_s", "max_tool_calls", "max_retries"):
        if f not in spec.budget.model_fields_set:
            out.append((f"budget.{f}", getattr(spec.budget, f), "documented default"))
    out += [("strategy", strategy, "system choice"), ("pilot_frac", pilot_frac, "tuned in Stage 4 (tuning conditions only)"),
            ("window_target", window_target, "tuned in Stage 4 (tuning conditions only)"), ("ss_recovery_target", SS_RECOVERY_TARGET, "Stage 5 design"),
            ("solver_ladder", SOLVER_LADDER, "Stage 5 recovery catalog; never touches gmin/abstol")]
    return out


def run_experiment(spec: ExperimentSpec, limits: DeviceLimits, simulator: Simulator, runs_root: Path, strategy: str = "uniform",
                   store: ProvenanceStore | None = None, pilot_frac: float = 0.4, window_target: int = 5,
                   clock=time.monotonic, llm_info: dict | None = None, injected: dict | None = None, replay_of: str | None = None) -> RunResult:
    runs_root = Path(runs_root)
    run_id = new_run_id(spec)
    created = utc_now()
    ledger = BudgetLedger.from_spec(spec, clock=clock)
    events: list[dict] = []
    chain: list[str] = []
    run_dir = runs_root / run_id
    run_dir.mkdir(parents=True, exist_ok=False)          # unique id; never overwrite an earlier experiment
    _dump(run_dir / "spec.json", spec.model_dump(mode="json"))
    plan = None
    sim: SimResult | None = None
    meas: dict[str, MeasurementResult] | None = None
    flags: list[str] = []
    message = ""
    try:
        plan = build_plan(spec, limits, strategy)
        _dump(run_dir / "plan.json", plan.model_dump(mode="json"))
    except PlanRejected as e:
        events.append({"kind": "rejected", "status": e.status.value, "code": e.code, "message": e.message})
        message = f"{e.code}: {e.message}"

    if plan is not None:
        calls = 4 if strategy in ("curvature", "window") else 2
        overrides: dict | None = None
        ladder_i = 0
        timeout_prev: float | None = None
        attempt = 0
        while True:
            attempt += 1
            try:
                ledger.charge_calls(calls)
                timeout = ledger.attempt_timeout(timeout_prev)
            except BudgetExceeded as b:
                events.append({"kind": "stop", "reason": "budget", "dimension": b.dimension, "detail": b.detail})
                message = f"stopped by budget ({b.dimension}): {b.detail}"
                break
            timeout_prev = timeout
            sim = run_sweep(spec, simulator, run_dir / f"attempt{attempt:02d}", strategy, pilot_frac, window_target,
                            timeout_s=timeout, solver_overrides=overrides)
            if sim.ok:
                try:
                    ledger.set_points(int(len(sim.x)))
                except BudgetExceeded as b:               # cannot happen after a valid plan; never crash, never accept
                    events.append({"kind": "stop", "reason": "budget", "dimension": b.dimension, "detail": b.detail})
                    message = f"stopped by budget ({b.dimension}): {b.detail}"
                    sim = None
                    break
                events.append({"kind": "output_ok", "attempt": attempt, "points": int(len(sim.x))})
                break
            rule = classify(sim.error_code)
            events.append({"kind": "fault", "code": rule.code, "recognised": rule.recognised, "recoverable": rule.recoverable,
                           "attempt": attempt, "detail": sim.error_detail})
            if not rule.recoverable:
                events.append({"kind": "stop", "reason": "unrecognised" if not rule.recognised else "unrecoverable", "code": rule.code})
                message = f"{rule.code}: {rule.action}"
                break
            if ledger.retries_left() <= 0:
                events.append({"kind": "stop", "reason": "budget", "dimension": "retries", "detail": f"retry limit {ledger.max_retries} reached"})
                message = f"stopped by budget (retries) after {rule.code}"
                break
            if rule.action == "solver_ladder":
                if ladder_i >= len(SOLVER_LADDER):
                    events.append({"kind": "stop", "reason": "ladder_exhausted", "code": rule.code})
                    message = f"{rule.code}: solver ladder exhausted"
                    break
                next_overrides, label = SOLVER_LADDER[ladder_i], f"{rule.code}:solver_ladder_{ladder_i + 1}"
            else:
                next_overrides, label = overrides, f"{rule.code}:{rule.action}"
            try:
                _pre_check(ledger, calls)                 # only record a recovery that can actually run
            except BudgetExceeded as b:
                events.append({"kind": "stop", "reason": "budget", "dimension": b.dimension, "detail": b.detail})
                message = f"stopped by budget ({b.dimension}) before recovering from {rule.code}"
                break
            if rule.action == "solver_ladder":
                ladder_i += 1
            overrides = next_overrides
            ledger.charge_retry()
            events.append({"kind": "recovery", "label": label, "attempt": attempt})
            chain.append(label)

        if sim is not None and sim.ok:
            floor = _solver_floor(spec, sim)
            meas = extract_all(spec, sim.x, sim.y, floor_a=floor)
            refused = {k: v.error_code for k, v in meas.items() if not v.ok}
            # measurement-level recovery: SS refused for lack of points in its window and points remain in the budget
            if refused.get("SS") in SS_REFUSAL_CODES and ledger.points_left() > 0 and ledger.retries_left() > 0:
                extra = window_points(sim.x, sim.y, spec.vth_ic_a * spec.width_um / spec.length_um, target=SS_RECOVERY_TARGET,
                                      max_new=min(ledger.points_left(), SS_RECOVERY_MAX_NEW))
                if len(extra) >= 2:
                    try:
                        _pre_check(ledger, 2)
                        ledger.charge_calls(2)
                        ledger.charge_retry()
                        s2 = simulator.run(spec, run_dir / "attempt_ss_refine", points=extra,
                                           timeout_s=ledger.attempt_timeout(None), solver_overrides=overrides) if overrides else \
                            simulator.run(spec, run_dir / "attempt_ss_refine", points=extra, timeout_s=ledger.attempt_timeout(None))
                    except BudgetExceeded as b:
                        events.append({"kind": "note", "msg": f"SS_REFUSED:window_refine not run ({b.dimension})"})
                        s2 = None
                    if s2 is not None and s2.ok:
                        order = np.argsort(np.concatenate([sim.x, s2.x]))
                        x = np.concatenate([sim.x, s2.x])[order]
                        y = np.concatenate([sim.y, s2.y])[order]
                        if len(x) <= ledger.max_points and (np.diff(x) > 0).all():
                            ledger.set_points(int(len(x)))
                            sim = SimResult(ok=True, x=x, y=y, runtime_s=sim.runtime_s + s2.runtime_s, simulator_version=sim.simulator_version,
                                            netlist_path=sim.netlist_path, raw_path=sim.raw_path,
                                            meta={**sim.meta, "ss_refine_points": int(len(extra))})
                            meas = extract_all(spec, sim.x, sim.y, floor_a=floor)
                            refused = {k: v.error_code for k, v in meas.items() if not v.ok}
                            events.append({"kind": "recovery", "label": "SS_REFUSED:window_refine", "points_added": int(len(extra))})
                            chain.append("SS_REFUSED:window_refine")
                    elif s2 is not None:
                        events.append({"kind": "note", "msg": f"SS_REFUSED:window_refine attempt failed: {s2.error_code}"})
            if overrides:
                flags.append("SOLVER_OVERRIDE:" + ",".join(f"{k}={v}" for k, v in sorted(overrides.items())))
            events.append({"kind": "measurements", "ok": [k for k, v in meas.items() if v.ok], "refused": refused})
            message = f"{len(meas) - len(refused)}/{len(meas)} measurements ok" + (f"; refused: {refused}" if refused else "")

    status = final_status(events)
    bad = check_evidence(status, events)
    if bad:                                              # an internal bug must never be reported as a result
        raise AssertionError(f"status {status} not justified by evidence: {bad}")
    ledger.charge_persist()
    n_pts = int(len(sim.x)) if (sim is not None and sim.ok) else 0
    result = RunResult(run_id, status, message, events, chain, ledger.retries, ledger.snapshot(), meas, sim, run_dir, flags, n_pts)
    _persist(result, spec, plan, strategy, pilot_frac, window_target, store, simulator, created, llm_info, injected, replay_of)
    return result


def _persist(r: RunResult, spec, plan, strategy, pilot_frac, window_target, store, simulator, created, llm_info, injected, replay_of=None) -> None:
    d = r.run_dir
    meas_rows = {}
    for k, m in (r.measurements or {}).items():
        row = m.to_dict()
        meas_rows[k] = {"ok": m.ok, "value": m.value, "unit": getattr(m, "unit", None), "error_code": m.error_code,
                        "flags": list(r.flags) if m.ok else [], "diagnostics": row.get("diagnostics", {})}
    _dump(d / "events.json", r.events)
    _dump(d / "measurements.json", meas_rows)
    _dump(d / "budget.json", r.budget)
    defaults = _defaults(spec, strategy, pilot_frac, window_target)
    _dump(d / "defaults.json", [{"field": f, "value": v, "reason": why} for f, v, why in defaults])
    _dump(d / "result.json", {"status": r.status.value, "message": r.message, "strategy": strategy, "retries_used": r.retries_used,
                              "recovery_chain": r.recovery_chain, "flags": r.flags, "points": r.n_points,
                              "x": None if r.sim is None or r.sim.x is None else [float(v) for v in r.sim.x],
                              "y": None if r.sim is None or r.sim.y is None else [float(v) for v in r.sim.y]})
    man, man_sha = write_manifest(d)
    if store is None:
        return
    head, dirty = git_state(REPO)
    meta = (r.sim.meta if r.sim is not None else {}) or {}
    row = {"run_id": r.run_id, "created_utc": created, "spec_sha256": spec_hash(spec), "status": r.status.value, "message": r.message,
           "strategy": strategy, "retries_used": r.retries_used, "tool_calls": r.budget["tool_calls"]["used"], "points": r.n_points,
           "wallclock_s": r.budget["wallclock_s"]["used"], "budget_json": json.dumps(r.budget), "recovery_chain_json": json.dumps(r.recovery_chain),
           "code_git_commit": head, "code_dirty": None if dirty is None else int(dirty),
           "ngspice_version": (r.sim.simulator_version if r.sim is not None else None) or simulator.version(),
           "model_files_json": json.dumps(meta.get("model_files_sha256", {})), "llm_json": json.dumps(llm_info) if llm_info else None,
           "run_dir": str(d), "manifest_sha256": man_sha, "injected_json": json.dumps(injected) if injected else None,
           "replay_of": replay_of}
    store.record_run(row, r.events, meas_rows, defaults, man)
