"""Group-1 (experiment understanding) evaluation harness. Provider-agnostic.

Metrics (per provider, per task set)
- valid_rate           : valid-expected tasks for which a valid spec was produced / valid-expected tasks
- exact_match_rate     : valid-expected tasks whose produced spec equals gold (floats rel 1e-6, measurement order ignored)
- wrong_value_rate     : valid-expected tasks that produced a valid but DIFFERENT spec (silent wrong spec; the dangerous case)
- correct_rejection    : reject-expected tasks that were rejected / reject-expected tasks
- false_accept_rate    : reject-expected tasks that still produced a valid spec (invented/accepted bad input)
- reason_match_rate    : rejected reject-expected tasks whose error text contains the expected field/phrase
- mean_latency_s, mean_llm_calls, repair_rate
"""
from __future__ import annotations

import json
import math
import statistics
import time
from pathlib import Path

from tinyspice.agent.interpret import interpret_request
from tinyspice.providers.base import LLMProvider
from tinyspice.schemas import ExperimentSpec


def load_tasks(path: Path) -> list[dict]:
    return json.loads(Path(path).read_text(encoding="utf-8"))["tasks"]


def _norm(o):
    if isinstance(o, dict):
        return {k: _norm(v) for k, v in sorted(o.items())}
    if isinstance(o, list):
        return sorted((_norm(x) for x in o), key=lambda z: json.dumps(z, sort_keys=True))
    return o


def _eq(a, b) -> bool:
    if isinstance(a, dict) and isinstance(b, dict):
        return a.keys() == b.keys() and all(_eq(a[k], b[k]) for k in a)
    if isinstance(a, list) and isinstance(b, list):
        return len(a) == len(b) and all(_eq(x, y) for x, y in zip(a, b))
    if isinstance(a, (int, float)) and isinstance(b, (int, float)) and not isinstance(a, bool):
        return math.isclose(a, b, rel_tol=1e-6, abs_tol=1e-9)
    return a == b


def specs_equal(a: ExperimentSpec, b: ExperimentSpec) -> bool:
    return _eq(_norm(a.model_dump(mode="json")), _norm(b.model_dump(mode="json")))


def evaluate(provider: LLMProvider, tasks: list[dict], seed: int = 0, only: list[str] | None = None, ground: bool = True) -> dict:
    recs = []
    for t in tasks:
        if only and t["id"] not in only:
            continue
        r = interpret_request(t["text"], provider, seed=seed, ground=ground)
        rec = {"id": t["id"], "expect": t["expect"], "produced_valid": r.ok, "llm_calls": r.llm_calls, "repaired": r.repaired,
               "latency_s": round(r.latency_s, 3), "errors": [f"{e['loc']}: {e['msg']}" for e in r.errors][:6], "raw": r.raw,
               "raw_text_head": r.raw_text[:600], "raw_text_tail": r.raw_text[-300:], "raw_text_len": len(r.raw_text)}
        if t["expect"] == "valid":
            gold = ExperimentSpec.model_validate(t["gold"])
            rec["exact"] = bool(r.ok and specs_equal(r.spec, gold))
            rec["wrong_value"] = bool(r.ok and not rec["exact"])
            if r.ok and not rec["exact"]:
                rec["diff"] = {k: (v, r.spec.model_dump(mode="json").get(k)) for k, v in gold.model_dump(mode="json").items()
                               if not _eq(_norm(v), _norm(r.spec.model_dump(mode="json").get(k)))}
        else:
            blob = " ".join(rec["errors"]).lower()
            rec["rejected"] = not r.ok
            rec["reason_match"] = bool((not r.ok) and all(s.lower() in blob for s in t.get("reject_match", [])))
        recs.append(rec)
    v = [r for r in recs if r["expect"] == "valid"]
    j = [r for r in recs if r["expect"] == "reject"]
    rate = lambda xs, f: (sum(1 for x in xs if f(x)) / len(xs)) if xs else None  # noqa: E731
    m = {
        "n_valid_tasks": len(v), "n_reject_tasks": len(j),
        "valid_rate": rate(v, lambda r: r["produced_valid"]),
        "exact_match_rate": rate(v, lambda r: r["exact"]),
        "wrong_value_rate": rate(v, lambda r: r["wrong_value"]),
        "correct_rejection": rate(j, lambda r: r["rejected"]),
        "false_accept_rate": rate(j, lambda r: r["produced_valid"]),
        "reason_match_rate": rate([r for r in j if r["rejected"]], lambda r: r["reason_match"]),
        "mean_latency_s": statistics.mean(r["latency_s"] for r in recs), "mean_llm_calls": statistics.mean(r["llm_calls"] for r in recs),
        "repair_rate": rate(recs, lambda r: r["repaired"]),
    }
    return {"provider": getattr(provider, "name", "?"), "seed": seed, "metrics": m, "tasks": recs}


def save(result: dict, outdir: Path, tag: str) -> Path:
    outdir.mkdir(parents=True, exist_ok=True)
    p = outdir / f"group1_{tag}_{result['provider'].replace(':', '-')}_{time.strftime('%Y%m%dT%H%M%S')}.json"
    p.write_text(json.dumps(result, indent=2, default=str), encoding="utf-8", newline="\n")
    return p
