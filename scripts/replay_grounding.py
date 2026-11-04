"""Replay the grounding check over SAVED raw model outputs (no model re-run): with vs without grounding.
Uses the latest result file per (model, set). Deterministic. Reports correct outputs lost to grounding (false rejections)."""
import glob
import json
import os
import re
from pathlib import Path

from tinyspice.agent.grounding import ungrounded_fields

ROOT = Path(__file__).resolve().parents[1]
SETS = {"dev": "group1_dev.json", "frozen": "group1_frozen.json"}
latest = {}
for f in sorted(glob.glob(str(ROOT / "results/benchmark/group1_*_llamacpp-*.json")), key=os.path.getmtime):
    m = re.search(r"group1_(dev|frozen)_llamacpp-(.+?)_2026", f)
    latest[(m[2], m[1])] = f

out = []
print(f"{'model':14s} {'set':7s} | {'exact':>9s} {'WRONG':>9s} {'false-acc':>11s} | lost-correct")
print(f"{'':22s} | {'raw→gnd':>9s} {'raw→gnd':>9s} {'raw→gnd':>11s} |")
for (model, s), f in sorted(latest.items(), key=lambda kv: (["smollm2-135m", "smollm2-360m", "qwen3.5-0.8b", "qwen3.5-2b"].index(kv[0][0]), kv[0][1])):
    res = json.load(open(f))
    tasks = {t["id"]: t for t in json.load(open(ROOT / "tests/benchmark" / SETS[s]))["tasks"]}
    nv = sum(t["expect"] == "valid" for t in tasks.values())
    nr = sum(t["expect"] == "reject" for t in tasks.values())
    ex0 = wr0 = fa0 = ex1 = wr1 = fa1 = lost = 0
    for r in res["tasks"]:
        t = tasks[r["id"]]
        blocked = bool(r["raw"] is not None and ungrounded_fields(r["raw"], t["text"]))
        if t["expect"] == "valid":
            e, w = bool(r.get("exact")), bool(r.get("wrong_value"))
            ex0 += e; wr0 += w
            ex1 += e and not blocked; wr1 += w and not blocked
            lost += e and blocked
        else:
            a = bool(r["produced_valid"])
            fa0 += a; fa1 += a and not blocked
    out.append((model, s))
    print(f"{model:14s} {s:7s} | {ex0}/{nv}→{ex1}/{nv}".ljust(40) + f"  {wr0}→{wr1}".ljust(10) + f"  {fa0}/{nr}→{fa1}/{nr}".ljust(14) + f"| {lost}")
