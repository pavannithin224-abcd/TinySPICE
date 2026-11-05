"""Stage 6b: R0 / R1 / R2 on the frozen fresh set R1 (docs/STAGE6B_PREREG.md). ONE frozen evaluation.
  R0 = current parse (stray -> pydantic reject); R1 = deterministic prune of inapplicable bias fields; R2 = one deterministic re-ask.
R0 is run live and its FIRST response is recorded; R1 and R2 replay that same first response (R2's re-ask, and any format repair, goes live).
Implementation note (no result seen): R1 prunes only the three bias-inapplicability strays; step-AND-points is re-askable (R2) but R1 does not guess which to drop.
Usage: python scripts/run_r1.py        (checkpointed per model; refuses to start if results/r1/result.json exists)"""
import hashlib
import json
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "r1"
RESULT = OUT / "result.json"
SET = ROOT / "tests" / "benchmark" / "group1_r1.json"
MODELS = ["qwen3.5-2b", "qwen3.5-0.8b"]
SEEDS = (0, 1, 2)
TEMPERATURE = 0.2
if len(sys.argv) != 1:
    sys.exit("usage: run_r1.py (no arguments)")
if RESULT.exists():
    sys.exit("result.json exists: the frozen evaluation executes ONCE. Refusing.")
want = (ROOT / "tests" / "benchmark" / "group1_r1.sha256").read_text().split()[0]
if hashlib.sha256(SET.read_bytes()).hexdigest() != want:
    sys.exit("group1_r1.json does not match its frozen hash; refusing")

from tinyspice.agent import interpret_request
from tinyspice.benchmark.group1 import specs_equal
from tinyspice.providers import LlamaCppProvider, ScriptedProvider
from tinyspice.providers.base import LLMResponse
from tinyspice.schemas import ExperimentSpec


class ReplayThenLive:
    """First call returns the recorded first response; any later call goes to the live model."""
    def __init__(self, first_text, live, model):
        self.first, self.live, self.n, self.name = first_text, live, 0, getattr(live, "name", "?")
        self.model = model

    def complete_json(self, system, user, schema, max_tokens=700, seed=0):
        self.n += 1
        if self.n == 1:
            return LLMResponse(text=self.first, model=self.model, latency_s=0.0)
        return self.live.complete_json(system, user, schema, max_tokens=max_tokens, seed=seed)


class Recorder:
    def __init__(self, inner):
        self.inner, self.name, self.first = inner, getattr(inner, "name", "?"), None

    def complete_json(self, *a, **k):
        r = self.inner.complete_json(*a, **k)
        if self.first is None:
            self.first = r.text
        return r


def score(task, r):
    rec = {"id": task["id"], "expect": task["expect"], "ok": r.ok, "llm_calls": r.llm_calls, "reasked": r.reasked, "pruned": r.pruned,
           "errors": [f"{e['loc']}: {e['msg']}" for e in r.errors][:4]}
    if task["expect"] == "valid":
        gold = ExperimentSpec.model_validate(task["gold"])
        rec["exact"] = bool(r.ok and specs_equal(r.spec, gold))
        rec["wrong"] = bool(r.ok and not rec["exact"])
    else:
        rec["accepted"] = bool(r.ok)
    return rec


tasks = json.loads(SET.read_text(encoding="utf-8"))["tasks"]
OUT.mkdir(parents=True, exist_ok=True)
allrows = {}
for model in MODELS:
    ck = OUT / f"rows_{model}.json"
    rows = json.loads(ck.read_text()) if ck.exists() else []
    done = {(r["task"], r["seed"], r["arm"]) for r in rows}
    with LlamaCppProvider(model, temperature=TEMPERATURE) as live:
        for t in tasks:
            for seed in SEEDS:
                if (t["id"], seed, "R2") in done:
                    continue
                rec = Recorder(live)
                r0 = interpret_request(t["text"], rec, seed=seed, ground=True)
                first = rec.first or "{}"
                r1 = interpret_request(t["text"], ReplayThenLive(first, live, model), seed=seed, ground=True, stray="prune")
                r2 = interpret_request(t["text"], ReplayThenLive(first, live, model), seed=seed, ground=True, stray="reask")
                for arm, r in (("R0", r0), ("R1", r1), ("R2", r2)):
                    rows.append({"model": model, "task": t["id"], "seed": seed, "arm": arm, **score(t, r)})
                ck.write_text(json.dumps(rows))
            print(model, t["id"], "done", flush=True)
    allrows[model] = rows
RESULT.write_text(json.dumps({"rows": allrows, "temperature": TEMPERATURE, "seeds": list(SEEDS), "set_sha256": want}, indent=1))
print("complete")
