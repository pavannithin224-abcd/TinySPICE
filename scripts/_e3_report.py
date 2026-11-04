import json
from pathlib import Path

S = json.loads((Path(__file__).resolve().parents[1] / "results/stage4/heldout_summary.json").read_text())
H = json.loads((Path(__file__).resolve().parents[1] / "results/stage4/heldout.json").read_text())
print("tuned values used:", {k: H[k] for k in ("pilot_frac", "window_target")}, "| rows:", len(H["rows"]))
for arm, a in S["arms"].items():
    print(f"\n===== {arm} vs uniform (13 held-out conditions)")
    print("failure rate (VTH,SS,GM):", {k: round(v, 3) for k, v in a["failure_rate_informative"].items()})
    for k in ("VTH", "SS", "GM", "ION", "IOFF"):
        m = a["per_measurement"][k]
        pn = "  ".join(f"N{n}:{v:+.3g}" for n, v in m["per_N_median_diff"].items())
        print(f"{k:5s} median(U-arm)={m['median_diff_(U-arm)']:+.3g} CI95=[{m['ci95'][0]:+.3g},{m['ci95'][1]:+.3g}] wins={m['arm_wins']} N*={m['N_star_median']}\n       per-N median diff (>0 favours arm; units mV / % / decades): {pn}")
    print("SS extraction success by N:", {s: {n: round(v, 2) for n, v in d.items()} for s, d in a["ss_extraction_success_by_N"].items()})
    print("verdicts: amended", a["H4_supported_amended"], "| original", a["H4_supported_original"])
# paired win/loss counts at the cell level (descriptive)
by = {}
for r in H["rows"]:
    by.setdefault((tuple(r["cond"]), r["n"]), {})[r["strategy"]] = r
print("\ncell-level paired counts over 13 conditions x 5 N = 65 cells (arm better / tie / uniform better), error with failure=10xtol:")
TOL = {"VTH": 5.0, "SS": 5.0, "GM": 5.0}
for arm in ("curvature", "window"):
    for k in ("VTH", "SS", "GM"):
        b = t = w = 0
        for g in by.values():
            eu, ea = g["uniform_pwl"]["err"][k], g[arm]["err"][k]
            eu = 10 * TOL[k] if eu is None else eu
            ea = 10 * TOL[k] if ea is None else ea
            if abs(eu - ea) < 1e-12:
                t += 1
            elif ea < eu:
                b += 1
            else:
                w += 1
        print(f"  {arm:9s} {k:4s}: better {b:2d} | tie {t:2d} | worse {w:2d}")
