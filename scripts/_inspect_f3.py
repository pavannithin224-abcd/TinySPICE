import collections
import glob
import json
import os
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent))
from replay_policies import FILES, ROOT, Replay

from tinyspice.benchmark import evaluate, load_tasks

for model in ("qwen3.5-2b", "smollm2-360m"):
    f = sorted(glob.glob(str(ROOT / f"results/benchmark/group1_frozen3_llamacpp-{model}_*.json")), key=os.path.getmtime)[-1]
    tasks = load_tasks(ROOT / "tests/benchmark" / FILES["frozen3"])
    saved = json.load(open(f))
    print("=====", model, "mean latency", round(saved["metrics"]["mean_latency_s"], 1), "s/task (inflated: CPU shared with other jobs)")
    res = evaluate(Replay({t["text"].strip(): r["raw"] for t, r in zip(tasks, saved["tasks"])}), tasks, ground=True)
    why = collections.Counter()
    for r in res["tasks"]:
        if r["expect"] == "valid" and not r["produced_valid"]:
            why[r["errors"][0].split(":")[0] + " | " + (r["errors"][0].split(": ", 1)[-1][:60] if r["errors"] else "")] += 1
        if r["expect"] == "valid" and r["wrong_value"]:
            print("WRONG", r["id"], r["diff"])
        if r["expect"] == "reject" and r["produced_valid"]:
            print("BAD-ACCEPT", r["id"])
    print("valid-request rejection reasons:")
    for k, v in why.most_common():
        print("  ", v, k)
