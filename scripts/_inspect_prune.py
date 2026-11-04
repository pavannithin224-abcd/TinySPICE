import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
import glob
import os

from replay_policies import FILES, ROOT, Replay

from tinyspice.benchmark import evaluate, load_tasks

for model, s in (("qwen3.5-2b", "frozen2"), ("qwen3.5-2b", "frozen"), ("qwen3.5-0.8b", "frozen2"), ("qwen3.5-0.8b", "frozen")):
    f = sorted(glob.glob(str(ROOT / f"results/benchmark/group1_{s}_llamacpp-{model}_*.json")), key=os.path.getmtime)[-1]
    tasks = load_tasks(ROOT / "tests/benchmark" / FILES[s])
    saved = json.load(open(f))
    prov = Replay({t["text"].strip(): r["raw"] for t, r in zip(tasks, saved["tasks"])})
    res = evaluate(prov, tasks, ground=True, prune=True)
    for r in res["tasks"]:
        bad_valid = r["expect"] == "valid" and r["wrong_value"]
        bad_rej = r["expect"] == "reject" and r["produced_valid"]
        if bad_valid or bad_rej:
            print(model, s, r["id"], "WRONG" if bad_valid else "BAD-ACCEPT", "pruned:", r["pruned"], "diff:", r.get("diff"))
            print("    raw measurements:", (r["raw"] or {}).get("measurements"))
