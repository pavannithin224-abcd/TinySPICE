"""Stage 7a (docs/STAGE7A_PREREG.md).
  python scripts/run_f4.py record          # live: record the model's FIRST response for every (model, task, seed); resumable
  python scripts/run_f4.py score <label>   # replay the recorded responses through the CURRENT code: arms default + prune -> results/f4/scores_<label>.json
  python scripts/run_f4.py report          # compare scores_v0 (before the guard change) with scores_v1 (after)
"""
import hashlib
import json
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "f4"
SET = ROOT / "tests" / "benchmark" / "group1_f4.json"
MODELS = ["qwen3.5-2b", "qwen3.5-0.8b"]
SEEDS = (0, 1, 2)
PHASES = {"record": 2, "score": 3, "report": 2}
if len(sys.argv) < 2 or sys.argv[1] not in PHASES or len(sys.argv) != PHASES[sys.argv[1]]:
    sys.exit("usage: run_f4.py record | score <label> | report")
want = (ROOT / "tests" / "benchmark" / "group1_f4.sha256").read_text().split()[0]
if hashlib.sha256(SET.read_bytes()).hexdigest() != want:
    sys.exit("group1_f4.json does not match its frozen hash; refusing")

from tinyspice.agent import interpret_request
from tinyspice.benchmark.group1 import specs_equal
from tinyspice.providers import LlamaCppProvider, ScriptedProvider
from tinyspice.schemas import ExperimentSpec

tasks = json.loads(SET.read_text(encoding="utf-8"))["tasks"]
OUT.mkdir(parents=True, exist_ok=True)


class Recorder:
    def __init__(self, inner):
        self.inner, self.name, self.first = inner, getattr(inner, "name", "?"), None

    def complete_json(self, *a, **k):
        r = self.inner.complete_json(*a, **k)
        if self.first is None:
            self.first = r.text
        return r


def rec_of(t, r):
    out = {"id": t["id"], "cat": t["cat"], "expect": t["expect"], "ok": r.ok, "pruned": r.pruned, "errors": [f"{e['loc']}: {e['msg']}" for e in r.errors][:3]}
    if t["expect"] == "valid":
        out["exact"] = bool(r.ok and specs_equal(r.spec, ExperimentSpec.model_validate(t["gold"])))
    return out


if sys.argv[1] == "record":
    for model in MODELS:
        f = OUT / f"first_{model}.json"
        data = json.loads(f.read_text()) if f.exists() else {}
        with LlamaCppProvider(model, temperature=0.2) as live:
            for t in tasks:
                for seed in SEEDS:
                    key = f"{t['id']}|{seed}"
                    if key in data:
                        continue
                    rec = Recorder(live)
                    interpret_request(t["text"], rec, seed=seed, ground=True)
                    data[key] = rec.first or "{}"
                    f.write_text(json.dumps(data))
                print(model, t["id"], flush=True)
    print("record complete")
elif sys.argv[1] == "score":
    label = sys.argv[2]
    commit = subprocess.run(["git", "rev-parse", "--short", "HEAD"], capture_output=True, text=True, cwd=ROOT).stdout.strip()
    res = {"label": label, "commit": commit, "rows": []}
    for model in MODELS:
        first = json.loads((OUT / f"first_{model}.json").read_text())
        for t in tasks:
            for seed in SEEDS:
                txt = first[f"{t['id']}|{seed}"]
                for arm, kw in (("default", {}), ("prune", {"stray": "prune"})):
                    r = interpret_request(t["text"], ScriptedProvider(txt), seed=seed, ground=True, **kw)
                    res["rows"].append({"model": model, "seed": seed, "arm": arm, **rec_of(t, r)})
    (OUT / f"scores_{label}.json").write_text(json.dumps(res))
    print("scored", label, commit, len(res["rows"]))
else:
    A = json.loads((OUT / "scores_v0.json").read_text())
    B = json.loads((OUT / "scores_v1.json").read_text())
    print(f"v0 = {A['commit']} (before guard change)   v1 = {B['commit']} (after)")
    key = lambda r: (r["model"], r["id"], r["seed"], r["arm"])   # noqa: E731
    a, b = {key(r): r for r in A["rows"]}, {key(r): r for r in B["rows"]}
    for model in MODELS:
        print(f"\n===== {model}")
        for arm in ("default", "prune"):
            for lab, S in (("v0", a), ("v1", b)):
                R = [r for k, r in S.items() if k[0] == model and k[3] == arm]
                con = [r for r in R if r["cat"] == "contra_fixed_swept"]
                un = [r for r in R if r["cat"] == "unstated_analysis"]
                va = [r for r in R if r["expect"] == "valid"]
                print(f"{arm:7s} {lab}: contradictions accepted {sum(r['ok'] for r in con)}/{len(con)}   unstated-analysis accepted {sum(r['ok'] for r in un)}/{len(un)}   "
                      f"valid exact {sum(r['exact'] for r in va)}/{len(va)}")
            lost = [k for k, r in a.items() if k[0] == model and k[3] == arm and r["expect"] == "valid" and r["exact"] and not b[k]["exact"]]
            print(f"{arm:7s} correct extractions LOST by the change: {len(lost)} {lost[:5]}")
