"""Run the Group-1 task set against a provider and save machine-readable results.

  python scripts/run_group1.py rules                         # no-LLM floor
  python scripts/run_group1.py qwen3.5-2b [--tasks dev]      # local llama.cpp model installed by setup_llm.py
Records exact model/runtime identity, startup time, per-task latency and tokens. Nothing leaves the machine.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from tinyspice.benchmark import evaluate, load_tasks, save
from tinyspice.providers import LlamaCppProvider, ProviderUnavailable, RuleBasedProvider

ROOT = Path(__file__).resolve().parents[1]
SETS = {"dev": ROOT / "tests" / "benchmark" / "group1_dev.json", "frozen": ROOT / "tests" / "benchmark" / "group1_frozen.json"}

ap = argparse.ArgumentParser()
ap.add_argument("provider", help="'rules' or a model key from .tools/manifest.json")
ap.add_argument("--tasks", default="dev", choices=sorted(SETS))
ap.add_argument("--threads", type=int, default=4)
ap.add_argument("--seed", type=int, default=0)
ap.add_argument("--only", nargs="*", help="task ids to run, e.g. --only D01 D04")
a = ap.parse_args()

tasks = load_tasks(SETS[a.tasks])
if a.provider == "rules":
    res = evaluate(RuleBasedProvider(), tasks, seed=a.seed, only=a.only)
    meta = {}
else:
    try:
        prov = LlamaCppProvider(a.provider, threads=a.threads)
    except ProviderUnavailable as e:
        sys.exit(f"provider unavailable: {e}")
    with prov:
        res = evaluate(prov, tasks, seed=a.seed, only=a.only)
        man = prov.tools.manifest
        meta = {"startup_s": round(prov.startup_s, 2), "threads": a.threads, "ctx": prov.ctx,
                "llama_cpp_tag": man["llama_cpp"]["tag"], "model": man["models"][a.provider]}
res["run_meta"] = meta
out = save(res, ROOT / "results" / "benchmark", a.tasks)
m = res["metrics"]
print(f"provider={res['provider']} tasks={a.tasks} (valid={m['n_valid_tasks']}, reject={m['n_reject_tasks']}) {meta}")
for k in ("valid_rate", "exact_match_rate", "wrong_value_rate", "correct_rejection", "false_accept_rate", "reason_match_rate",
          "repair_rate", "mean_llm_calls", "mean_latency_s"):
    v = m[k]
    print(f"  {k:20s} {'n/a' if v is None else round(v, 3)}")
print("saved:", out)
for t in res["tasks"]:
    bad = (t["expect"] == "valid" and not t["exact"]) or (t["expect"] == "reject" and not t["rejected"])
    if bad:
        print("  MISS", t["id"], t.get("diff") or t["errors"])
