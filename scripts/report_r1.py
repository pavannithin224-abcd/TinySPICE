"""Analysis for Stage 6b, exactly per docs/STAGE6B_PREREG.md. Safe to repeat."""
import json
from pathlib import Path
from scipy.stats import binomtest
d = json.loads((Path(__file__).resolve().parents[1] / "results" / "r1" / "result.json").read_text())["rows"]
def sign(a, b):  # one-sided: a better than b
    n = a + b
    return 1.0 if n == 0 else binomtest(a, n, 0.5, alternative="greater").pvalue
out = {}
for m, rows in d.items():
    print(f"\n===== {m}")
    by = {}
    for r in rows:
        by.setdefault(r["arm"], {})[(r["task"], r["seed"])] = r
    M = {}
    for arm in ("R0", "R1", "R2"):
        R = list(by[arm].values())
        v = [r for r in R if r["expect"] == "valid"]; b = [r for r in R if r["expect"] == "reject"]
        M[arm] = dict(recall=sum(r["exact"] for r in v) / len(v), wrong=sum(r["wrong"] for r in v), wrongn=len(v),
                      badacc=sum(r["accepted"] for r in b), badn=len(b), reask=sum(r["reasked"] for r in R),
                      pruned=sum(bool(r["pruned"]) for r in R), calls=sum(r["llm_calls"] for r in R))
        x = M[arm]
        print(f"{arm}: exact {sum(r['exact'] for r in v)}/{len(v)}={x['recall']:.3f}  silent-wrong {x['wrong']}  bad-accepted {x['badacc']}/{x['badn']}  re-asked {x['reask']}  pruned {x['pruned']}  llm calls {x['calls']}")
    def pair(a, b):
        ka = [k for k, r in by[a].items() if r["expect"] == "valid"]
        w = sum(by[a][k]["exact"] and not by[b][k]["exact"] for k in ka)
        l = sum(by[b][k]["exact"] and not by[a][k]["exact"] for k in ka)
        return w, l, sign(w, l)
    for a, b in (("R2", "R0"), ("R1", "R0"), ("R2", "R1")):
        w, l, p = pair(a, b)
        print(f"{a} vs {b}: {a}-only exact {w}, {b}-only exact {l}, one-sided sign p = {p:.4f}")
    if m == "qwen3.5-2b":
        gain = M["R2"]["recall"] - M["R0"]["recall"]; p = pair("R2", "R0")[2]
        safe = M["R2"]["wrong"] <= M["R0"]["wrong"] and M["R2"]["badacc"] <= M["R0"]["badacc"]
        dom = abs(M["R1"]["recall"] - M["R2"]["recall"]) <= 0.02 or M["R1"]["recall"] > M["R2"]["recall"]
        print(f"PRIMARY: gain(R2-R0) = {gain:+.3f} (need >= 0.05); p = {p:.4f} (need < 0.05); safety held = {safe}; R1 matches/beats R2 (within 0.02) = {dom}")
        ok = gain >= 0.05 and p < 0.05 and safe and not dom
        print("DECISION:", "R2 SUPPORTED" if ok else ("NOT supported: deterministic prune suffices (R1 matches R2 without an LLM call)" if (gain >= 0.05 and p < 0.05 and safe and dom) else "R2 NOT supported"))
