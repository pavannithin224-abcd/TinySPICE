"""Replay SAVED raw model outputs through the REAL interpreter code path under three policies:
  raw (no grounding) | ground (block) | ground+prune (drop spurious measurements). Deterministic; no model is run.
Usage: python scripts/replay_policies.py [set ...]   (default: dev frozen frozen2 [frozen3 if present])
Uses the latest result file per (model, set); result files must come from --no-ground runs."""
import glob
import json
import os
import re
import sys
from pathlib import Path

from tinyspice.benchmark import evaluate, load_tasks
from tinyspice.providers.base import LLMResponse

ROOT = Path(__file__).resolve().parents[1]
FILES = {"dev": "group1_dev.json", "frozen": "group1_frozen.json", "frozen2": "group1_frozen2.json", "frozen3": "group1_frozen3.json", "probe": "group1_probe.json"}
MODELS = ["smollm2-135m", "smollm2-360m", "qwen3.5-0.8b", "qwen3.5-2b"]


class Replay:
    name = "replay"

    def __init__(self, by_text):
        self.by_text = by_text

    def complete_json(self, system, user, schema, max_tokens=700, seed=0):
        req = re.search(r"REQUEST:\n(.*?)\n\nReturn the JSON", user, re.S).group(1)
        raw = self.by_text[req.strip()]
        return LLMResponse(text="" if raw is None else json.dumps(raw), model="replay", latency_s=0.0)


def main(sets):
    latest = {}
    for f in sorted(glob.glob(str(ROOT / "results/benchmark/group1_*_llamacpp-*.json")), key=os.path.getmtime):
        m = re.search(r"group1_(dev|frozen3|frozen2|frozen|probe)_llamacpp-(.+?)_2026", f)
        latest[(m[2], m[1])] = f
    print(f"{'model':13s} {'set':8s} {'policy':12s} | exact  WRONG  bad-accepted  safe-reject(valid)  pruned-items")
    for model in MODELS:
        for s in sets:
            f = latest.get((model, s))
            if not f:
                continue
            tasks = load_tasks(ROOT / "tests/benchmark" / FILES[s])
            saved = json.load(open(f))
            prov = Replay({t["text"].strip(): r["raw"] for t, r in zip(tasks, saved["tasks"]) if t["id"] == r["id"]})
            nv = sum(t["expect"] == "valid" for t in tasks)
            nr = len(tasks) - nv
            for label, kw in (("raw", dict(ground=False)), ("ground", dict(ground=True)), ("ground+prune", dict(ground=True, prune=True))):
                res = evaluate(prov, tasks, **kw)
                v = [r for r in res["tasks"] if r["expect"] == "valid"]
                j = [r for r in res["tasks"] if r["expect"] == "reject"]
                ex = sum(r["exact"] for r in v)
                wr = sum(r["wrong_value"] for r in v)
                ba = sum(r["produced_valid"] for r in j)
                sr = sum((not r["produced_valid"]) for r in v)
                pr = sum(len(r["pruned"]) for r in res["tasks"])
                print(f"{model:13s} {s:8s} {label:12s} | {ex}/{nv}    {wr}      {ba}/{nr}          {sr}/{nv}               {pr}")


if __name__ == "__main__":
    main(sys.argv[1:] or ["dev", "frozen", "frozen2"])
