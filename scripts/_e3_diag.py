"""Harness sanity check on the TUNING conditions only (never the held-out set)."""
import importlib.util
import sys
from pathlib import Path

import numpy as np

spec = importlib.util.spec_from_file_location("e3", Path(__file__).parent / "run_e3.py")
e3 = importlib.util.module_from_spec(spec)
sys.modules["e3"] = e3
spec.loader.exec_module(e3)

rows = e3.table(e3.TUNE, 0.4, "diag")
print("tuning conditions:", len(e3.TUNE), "rows:", len(rows))
print("\nextraction failures (None) per strategy x measurement, out of", len(e3.TUNE) * len(e3.NS), "cells each")
for s in ("uniform_pwl", "curvature"):
    print(f"  {s:12s}", {k: sum(r['err'][k] is None for r in rows if r['strategy'] == s) for k in e3.MEAS})
print("\nmedian error / tolerance by N (None counted as 10):  U | C")
for k in e3.MEAS:
    line = []
    for n in e3.NS:
        u = np.median([e3.score(r["err"][k], k) for r in rows if r["strategy"] == "uniform_pwl" and r["n"] == n])
        c = np.median([e3.score(r["err"][k], k) for r in rows if r["strategy"] == "curvature" and r["n"] == n])
        line.append(f"N{n}:{u:.2f}|{c:.2f}")
    print(f"  {k:5s}", "  ".join(line))
r0 = [r for r in rows if r["n"] == 20 and tuple(r["cond"]) == e3.TUNE[1]]
for r in r0:
    print("\nexample", r["strategy"], r["cond"], "N=20 values", {k: (None if v is None else float(f"{v:.4g}")) for k, v in r["values"].items()}, "ref", {k: float(f"{v:.4g}") for k, v in r["ref"].items() if v is not None})
