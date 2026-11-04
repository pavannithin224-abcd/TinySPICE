"""Replay and verify. `replay` re-executes a stored run's spec + strategy in a fresh folder (recorded as its own run) and compares
every measurement with the stored one; `verify_run` (provenance) checks the stored artefacts' hashes."""
from __future__ import annotations

import math
from pathlib import Path

from tinyspice.planner.planner import spec_hash
from tinyspice.provenance import ProvenanceStore
from tinyspice.runner import run_experiment
from tinyspice.schemas import DeviceLimits, ExperimentSpec


def replay(store: ProvenanceStore, run_id: str, simulator, limits: DeviceLimits, runs_root: Path, rtol: float = 1e-6) -> dict:
    rec = store.run(run_id)
    if rec is None:
        raise KeyError(f"unknown run {run_id}")
    spec = ExperimentSpec.model_validate_json((Path(rec["run_dir"]) / "spec.json").read_text(encoding="utf-8"))
    if spec_hash(spec) != rec["spec_sha256"]:
        return {"matched": False, "reason": "stored spec.json does not match the recorded spec hash", "new_run_id": None}
    new = run_experiment(spec, limits, simulator, runs_root, strategy=rec["strategy"], store=store, replay_of=run_id)
    stored = store.measurements(run_id)
    per = {}
    for name, m in stored.items():
        n = (new.measurements or {}).get(name)
        if n is None:
            per[name] = {"match": False, "why": "missing in replay"}
        elif m["ok"] != n.ok:
            per[name] = {"match": False, "why": f"ok differs (stored {m['ok']}, replay {n.ok})"}
        elif not m["ok"]:
            per[name] = {"match": m["error_code"] == n.error_code, "why": "both refused"}
        else:
            ok = math.isclose(m["value"], n.value, rel_tol=rtol, abs_tol=0.0)
            per[name] = {"match": ok, "stored": m["value"], "replay": n.value}
    return {"matched": bool(per) and all(v["match"] for v in per.values()), "per_measurement": per, "new_run_id": new.run_id,
            "stored_status": rec["status"], "replay_status": new.status.value}
