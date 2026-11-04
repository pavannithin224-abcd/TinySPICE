"""Confirmatory run for the window-sampling SS finding. See docs/STAGE4_CONFIRM_PREREG.md (committed before running).
  python scripts/run_confirm.py confirm      # the ONE run; refuses to run twice
Argument is checked BEFORE any heavy work."""
import itertools
import json
import sys
from pathlib import Path

PHASES = ("confirm",)
if __name__ == "__main__" and (len(sys.argv) != 2 or sys.argv[1] not in PHASES):
    sys.exit(f"usage: run_confirm.py <{'|'.join(PHASES)}>  (got {sys.argv[1:]!r})")

import importlib.util

import numpy as np
from scipy.stats import binomtest

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "stage4_confirm"
RESULT = OUT / "confirm_result.json"

spec = importlib.util.spec_from_file_location("e3", ROOT / "scripts" / "run_e3.py")
e3 = importlib.util.module_from_spec(spec)
sys.modules["e3"] = e3
spec.loader.exec_module(e3)          # reuses the SAME helpers (spec, reference, extraction, error definitions) as the main experiment
e3.OUT, e3.RUNS = OUT, OUT / "runs"

CONDS = list(itertools.product([0.84, 2.0, 10.0], [0.25, 1.0], [0.0, 85.0]))
NS = [12, 16, 20, 30, 50]
PRIMARY_N = (16, 20)
FRAC, WT = 0.4, 5                    # frozen from the earlier tuning; nothing is tuned here
ARMS = ("uniform_pwl", "window")
TOL = e3.TOL


def main():
    if RESULT.exists():
        sys.exit("confirmatory result already exists: this run executes ONCE (see STAGE4_CONFIRM_PREREG.md). Refusing.")
    OUT.mkdir(parents=True, exist_ok=True)
    rows = []
    for c in CONDS:
        ref = e3.reference(c)
        for n in NS:
            for arm in ARMS:
                vals, code, rt = e3.run_cell(c, n, arm, FRAC, WT, "conf")
                rows.append({"cond": list(c), "n": n, "strategy": arm, "sim_error": code, "values": vals, "ref": ref,
                             "err": {k: e3.err(k, vals[k], ref[k]) for k in e3.MEAS}})
    by = {}
    for r in rows:
        by.setdefault((tuple(r["cond"]), r["n"]), {})[r["strategy"]] = r
    ok = lambda g, arm: g[arm]["err"]["SS"] is not None  # noqa: E731
    pairs = [(c, n) for (c, n) in by if n in PRIMARY_N]
    s_w = sum(ok(by[p], "window") for p in pairs)
    s_u = sum(ok(by[p], "uniform_pwl") for p in pairs)
    d_w = sum(ok(by[p], "window") and not ok(by[p], "uniform_pwl") for p in pairs)
    d_u = sum(ok(by[p], "uniform_pwl") and not ok(by[p], "window") for p in pairs)
    diff = (s_w - s_u) / len(pairs)
    p_val = binomtest(d_w, d_w + d_u, 0.5, alternative="greater").pvalue if (d_w + d_u) > 0 else 1.0
    confirmed = bool(diff >= 0.30 and p_val < 0.01)
    by_n = {n: {a: float(np.mean([ok(by[(c, n)], a) for c in CONDS])) for a in ARMS} for n in NS}
    both = [(c, n) for (c, n) in by if ok(by[(c, n)], "window") and ok(by[(c, n)], "uniform_pwl")]
    ss_acc = {a: float(np.median([by[p][a]["err"]["SS"] for p in both])) if both else None for a in ARMS}
    cost = {}
    for k in ("VTH", "GM"):
        per_n = {}
        for n in NS:
            d = [(by[(c, n)]["window"]["err"][k] if by[(c, n)]["window"]["err"][k] is not None else 10 * TOL[k])
                 - (by[(c, n)]["uniform_pwl"]["err"][k] if by[(c, n)]["uniform_pwl"]["err"][k] is not None else 10 * TOL[k]) for c in CONDS]
            per_n[n] = float(np.median(d))
        cost[k] = {"median_W_minus_U_by_N": per_n, "acceptable_limit": 0.5 * TOL[k]}
    fail = {a: float(np.mean([r["err"][k] is None for r in rows if r["strategy"] == a for k in ("VTH", "SS", "GM")])) for a in ARMS}
    out = {"conditions": [list(c) for c in CONDS], "primary_N": list(PRIMARY_N), "paired_cells": len(pairs),
           "ss_success": {"window": s_w, "uniform_pwl": s_u}, "success_rate_diff_W_minus_U": diff,
           "discordant": {"W_ok_U_fail": d_w, "U_ok_W_fail": d_u}, "sign_test_p_one_sided": p_val,
           "CONFIRMED": confirmed, "ss_success_by_N": by_n, "ss_median_abs_err_pct_when_both_ok": ss_acc,
           "cost_VTH_GM": cost, "failure_rate_VTH_SS_GM": fail}
    RESULT.write_text(json.dumps(out, indent=1))
    (OUT / "confirm_rows.json").write_text(json.dumps(rows, indent=1))
    print(json.dumps(out, indent=1))
    print("CONFIRMED" if confirmed else "NOT CONFIRMED (earlier finding stays exploratory / is withdrawn)")


if __name__ == "__main__":
    main()
