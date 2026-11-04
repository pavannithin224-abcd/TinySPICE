"""Independent scoring for TinySPICEBench, exactly as defined in docs/BENCH_PREREG.md. Ground truth is re-derived from the GOLD spec and a dense
plain-dc reference; it never trusts what a configuration reports."""
from __future__ import annotations

import hashlib
import json
import math
import shutil
from pathlib import Path

import numpy as np
from scipy.stats import binomtest

from tinyspice.agent.raw import raw_to_spec_dict
from tinyspice.benchmark.bench import ROOT, TOL, Outcome, full_raw
from tinyspice.errors import PlanRejected
from tinyspice.executor import _solver_floor
from tinyspice.measurements import extract_all
from tinyspice.planner import build_plan
from tinyspice.schemas import ExperimentSpec
from tinyspice.simulator import NgspiceSimulator

TOL = {**TOL, "GDS": 5.0}
SUCCESS_CLAIMS = ("successful", "recovered_after_failure")
REF_DIR = ROOT / "results" / "bench" / "ref"


def gold_spec(task: dict) -> ExperimentSpec | None:
    if task["expected_status"] not in SUCCESS_CLAIMS:
        return None
    return ExperimentSpec.model_validate(raw_to_spec_dict(full_raw(task["gold_raw"])))


def reference_values(spec: ExperimentSpec, workdir: Path) -> dict:
    """Measurements from a dense (1 mV) plain-dc sweep of the GOLD spec; cached by spec hash."""
    d = spec.model_dump(mode="json")
    d["sweep"] = {"start": spec.sweep.start, "stop": spec.sweep.stop, "step": 0.001}
    d["budget"] = {"max_points": 2000, "max_runtime_s": 120.0}
    dense = ExperimentSpec.model_validate(d)
    key = hashlib.sha256(json.dumps(d, sort_keys=True).encode()).hexdigest()[:16]
    f = REF_DIR / f"{key}.json"
    if f.exists():
        return json.loads(f.read_text())
    run_dir = Path(workdir) / f"ref_{key}"
    if run_dir.exists():
        shutil.rmtree(run_dir)
    sim = NgspiceSimulator().run(dense, run_dir)
    if not sim.ok:
        raise RuntimeError(f"reference run failed: {sim.error_code} {sim.error_detail}")
    m = extract_all(dense, sim.x, sim.y, floor_a=_solver_floor(dense, sim))
    out = {k: {"ok": v.ok, "value": v.value} for k, v in m.items()}
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(out))
    return out


def _close(a, b) -> bool:
    return a == b if not isinstance(a, (int, float)) or isinstance(a, bool) else (b is not None and math.isclose(a, b, rel_tol=1e-6, abs_tol=1e-9))


def spec_matches(executed: dict | None, gold: ExperimentSpec, gold_raw: dict) -> bool:
    if executed is None:
        return False
    g = gold.model_dump(mode="json")
    for k in ("width_um", "length_um", "temperature_c", "analysis", "vds_v", "vgs_v", "ion_vgs_v", "ioff_vgs_v"):
        if not _close(executed.get(k), g.get(k)):
            return False
    if set(executed["measurements"]) != set(g["measurements"]):
        return False
    for k in ("start", "stop", "step", "points"):
        if not _close(executed["sweep"].get(k), g["sweep"].get(k)):
            return False
    for k in ("max_points", "max_runtime_s", "max_tool_calls", "max_retries"):
        if k in gold_raw and not _close(executed["budget"].get(k), g["budget"].get(k)):
            return False
    return True


def _err(name: str, v: float, ref: float) -> float | None:
    if v is None or ref is None:
        return None
    if name == "VTH":
        return abs(v - ref) * 1e3
    if name == "IOFF":
        return abs(math.log10(abs(v) / abs(ref))) if v and ref else None
    return abs(v - ref) / abs(ref) * 100.0


def measurements_ok(outcome: Outcome, gold: ExperimentSpec, ref: dict) -> tuple[bool, list[float]]:
    errs = []
    for m in [x.value if hasattr(x, "value") else x for x in gold.measurements]:
        got = outcome.values.get(m)
        if not got or not got["ok"]:
            return False, errs
        if m == "ID":
            continue
        e = _err(m, got["value"], ref[m]["value"])
        if e is None or e > TOL[m]:
            return False, errs
        errs.append(e / TOL[m])
    return True, errs


def budget_violation(outcome: Outcome, gold_raw: dict) -> bool:
    if outcome.sim_calls == 0:
        return False
    if outcome.points > gold_raw.get("max_points", 10**9):
        return True
    if "max_runtime_s" in gold_raw and outcome.wallclock_s > gold_raw["max_runtime_s"]:
        return True
    if "max_tool_calls" in gold_raw and 2 * outcome.sim_calls > gold_raw["max_tool_calls"]:
        return True
    return False


def planner_valid(outcome: Outcome, limits) -> bool | None:
    if outcome.spec is None or outcome.sim_calls == 0:
        return None
    try:
        build_plan(ExperimentSpec.model_validate(outcome.spec), limits, "uniform")
        return True
    except PlanRejected:
        return False
    except Exception:
        return False


def score(task: dict, outcome: Outcome, limits, workdir: Path, reproducible: bool | None = None) -> dict:
    gold = gold_spec(task)
    claim = outcome.status in SUCCESS_CLAIMS
    executed = outcome.sim_calls > 0
    sm = mo = False
    errs: list[float] = []
    if gold is not None and executed:
        sm = spec_matches(outcome.spec, gold, task["gold_raw"])
        if sm:
            mo, errs = measurements_ok(outcome, gold, reference_values(gold, workdir))
    viol = budget_violation(outcome, task["gold_raw"])
    truth = bool(gold is not None and executed and sm and mo and not viol)
    return {
        "task": task["id"], "group": task["group"], "config": outcome.config, "status": outcome.status, "expected": task["expected_status"],
        "completion": outcome.status == task["expected_status"], "claim": claim, "truth_achieved": truth,
        "false_success": bool(claim and not truth), "honest_failure": bool((not truth) and (not claim)),
        "executed": executed, "invented": bool(executed and task["expected_status"] == "rejected_invalid_input"),
        "spec_valid": (sm if (gold is not None and executed) else None), "planner_valid": planner_valid(outcome, limits),
        "budget_violation": viol, "meas_err_norm": errs, "reproducible": reproducible, "points": outcome.points,
        "wallclock_s": outcome.wallclock_s, "sim_calls": outcome.sim_calls, "retries": outcome.retries, "notes": outcome.notes,
    }


# ---------------- statistics ----------------
def wilson(k: int, n: int, z: float = 1.96) -> tuple[float, float]:
    if n == 0:
        return (float("nan"), float("nan"))
    p = k / n
    d = 1 + z * z / n
    c = (p + z * z / (2 * n)) / d
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n)) / d
    return (max(0.0, c - h), min(1.0, c + h))


def sign_test_one_sided(worse_only: int, better_only: int) -> float:
    """P(X >= worse_only | n = worse_only + better_only, p = .5): the first configuration is worse more often than chance."""
    n = worse_only + better_only
    return 1.0 if n == 0 else float(binomtest(worse_only, n, 0.5, alternative="greater").pvalue)


def cluster_bootstrap_diff(pairs: list[tuple[str, float, float]], B: int = 2000, seed: int = 20261104) -> tuple[float, float, float]:
    """pairs: (task_id, value_first, value_second). Resample TASKS; return (mean diff first-second, lo, hi)."""
    by: dict[str, list[tuple[float, float]]] = {}
    for t, a, c in pairs:
        by.setdefault(t, []).append((a, c))
    tasks = sorted(by)
    rng = np.random.default_rng(seed)
    full = float(np.mean([a - c for t in tasks for a, c in by[t]]))
    boots = []
    for _ in range(B):
        samp = [tasks[i] for i in rng.integers(0, len(tasks), len(tasks))]
        boots.append(np.mean([a - c for t in samp for a, c in by[t]]))
    lo, hi = np.percentile(boots, [2.5, 97.5])
    return full, float(lo), float(hi)
