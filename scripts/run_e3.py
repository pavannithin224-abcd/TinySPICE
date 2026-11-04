"""E3: uniform (PWL) vs curvature sampling against a dense reference. See docs/STAGE4_PREREG.md (frozen before running).
  python scripts/run_e3.py tune      # fits pilot_frac on the TUNING conditions only
  python scripts/run_e3.py heldout   # ONE run on the held-out conditions with the tuned pilot_frac
Outputs go to results/stage4/. Needs ngspice + SKY130 in ./.tools."""
import itertools
import json
import shutil
import sys
import time
from pathlib import Path

import numpy as np

from tinyspice.executor import _solver_floor, run_sweep
from tinyspice.measurements import extract_all
from tinyspice.schemas import ExperimentSpec
from tinyspice.simulator import NgspiceSimulator

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "stage4"
RUNS = OUT / "runs"
Ws, Ls, Ts = [0.42, 1.0, 5.0], [0.15, 0.5], [-40.0, 27.0, 125.0]
CONDS = list(itertools.product(Ws, Ls, Ts))
TUNE = [c for i, c in enumerate(CONDS) if i % 4 == 0]   # stride 4 (coprime to the 3-valued T axis; a stride of 3 would alias onto T)
HELD = [c for i, c in enumerate(CONDS) if i % 4 != 0]
NS = [12, 16, 20, 30, 50]
FRACS = [0.2, 0.3, 0.4]
MEAS = ["VTH", "SS", "GM", "ION", "IOFF"]
TOL = {"VTH": 5.0, "SS": 5.0, "GM": 5.0, "ION": 2.0, "IOFF": 0.05}
PENALTY = 10.0
SIM = NgspiceSimulator()


def spec_for(c, n, dense=False):
    w, l, t = c
    sweep = {"start": 0.0, "stop": 1.8, "step": 0.001} if dense else {"start": 0.0, "stop": 1.8, "points": n}
    return ExperimentSpec.model_validate({
        "device_type": "nmos", "model_name": "sky130_fd_pr__nfet_01v8", "width_um": w, "length_um": l, "temperature_c": t,
        "analysis": "idvg", "sweep": sweep, "vds_v": 1.8, "measurements": MEAS, "ion_vgs_v": 1.8, "ioff_vgs_v": 0.0,
        "budget": {"max_points": 2000, "max_runtime_s": 120.0}})


def measure(spec, sim):
    m = extract_all(spec, sim.x, sim.y, floor_a=_solver_floor(spec, sim))
    return {k: (m[k].value if m[k].ok else None) for k in MEAS}


def reference(c):
    f = OUT / "ref" / f"ref_{c[0]}_{c[1]}_{c[2]}.json"
    if f.exists():
        return json.loads(f.read_text())
    spec = spec_for(c, 0, dense=True)
    d = RUNS / f"ref_{c[0]}_{c[1]}_{c[2]}"
    if d.exists():
        shutil.rmtree(d)
    sim = SIM.run(spec, d / "sim")
    if not sim.ok:
        raise RuntimeError(f"reference failed for {c}: {sim.error_code} {sim.error_detail}")
    r = measure(spec, sim)
    f.parent.mkdir(parents=True, exist_ok=True)
    f.write_text(json.dumps(r))
    return r


def err(k, v, ref):
    """Error in the units of TOL[k]; None if the measurement failed to extract."""
    if v is None or ref is None:
        return None
    if k == "VTH":
        return abs(v - ref) * 1e3
    if k == "IOFF":
        return abs(np.log10(abs(v) / abs(ref))) if v != 0 and ref != 0 else None
    return abs(v - ref) / abs(ref) * 100.0


def run_cell(c, n, strategy, frac, tag):
    spec = spec_for(c, n)
    d = RUNS / f"{tag}_{strategy}_{c[0]}_{c[1]}_{c[2]}_{n}_{frac}"
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    sim = run_sweep(spec, SIM, d, strategy, pilot_frac=frac)
    if not sim.ok:
        return {k: None for k in MEAS}, sim.error_code, 0.0
    return measure(spec, sim), None, sim.runtime_s


def table(conds, frac, tag):
    rows = []
    for c in conds:
        ref = reference(c)
        for n in NS:
            for strat in ("uniform_pwl", "curvature"):
                vals, code, rt = run_cell(c, n, strat, frac, tag)
                rows.append({"cond": list(c), "n": n, "strategy": strat, "frac": frac, "sim_error": code, "runtime_s": rt,
                             "values": vals, "err": {k: err(k, vals[k], ref[k]) for k in MEAS}, "ref": ref})
    return rows


def score(e, k):  # normalised error with the pre-registered failure penalty
    return PENALTY if e is None else e / TOL[k]


def main(phase):
    OUT.mkdir(parents=True, exist_ok=True)
    t0 = time.monotonic()
    if phase == "tune":
        best = {}
        allrows = {}
        for fr in FRACS:
            rows = [r for r in table(TUNE, fr, f"tune{fr}") if r["strategy"] == "curvature"]
            allrows[fr] = rows
            best[fr] = float(np.mean([score(r["err"][k], k) for r in rows for k in MEAS]))
            print(f"pilot_frac={fr}: mean normalised error {best[fr]:.4f} (tuning conditions only)")
        pick = min(best, key=lambda f: (best[f], f))
        (OUT / "tune.json").write_text(json.dumps({"pilot_frac": pick, "scores": best, "tuning_conditions": TUNE, "heldout_conditions": HELD}, indent=1))
        print("CHOSEN pilot_frac =", pick, f"({time.monotonic() - t0:.0f}s)")
        return
    tune = json.loads((OUT / "tune.json").read_text())
    if (OUT / "heldout.json").exists():
        sys.exit("held-out results already exist: the held-out run is executed ONCE (see STAGE4_PREREG.md). Refusing.")
    frac = tune["pilot_frac"]
    rows = table(HELD, frac, "held")
    (OUT / "heldout.json").write_text(json.dumps({"pilot_frac": frac, "rows": rows}, indent=1))
    analyse(rows)
    print(f"done in {time.monotonic() - t0:.0f}s")


def analyse(rows):
    by = {}
    for r in rows:
        by.setdefault((tuple(r["cond"]), r["n"]), {})[r["strategy"]] = r
    conds = sorted({k[0] for k in by})
    rng = np.random.default_rng(20261104)
    wins, summary = 0, {}
    fail = {s: [0, 0] for s in ("uniform_pwl", "curvature")}
    for r in rows:
        for k in MEAS:
            fail[r["strategy"]][0] += r["err"][k] is None
            fail[r["strategy"]][1] += 1
    for k in MEAS:
        d = {}
        for (c, n), pair in by.items():
            eu, ec = pair["uniform_pwl"]["err"][k], pair["curvature"]["err"][k]
            if eu is None and ec is None:
                d[(c, n)] = 0.0
            else:
                d[(c, n)] = (PENALTY * TOL[k] if eu is None else eu) - (PENALTY * TOL[k] if ec is None else ec)
        med = float(np.median(list(d.values())))
        boots = []
        for _ in range(2000):
            sample = [conds[i] for i in rng.integers(0, len(conds), len(conds))]
            boots.append(np.median([d[(c, n)] for c in sample for n in NS]))
        lo, hi = np.percentile(boots, [2.5, 97.5])
        win = med > 0 and lo > 0
        wins += win
        per_n = {n: float(np.median([d[(c, n)] for c in conds])) for n in NS}
        nstar = {}
        for s in ("uniform_pwl", "curvature"):
            vals = []
            for c in conds:
                ok_n = [n for n in NS if by[(c, n)][s]["err"][k] is not None and by[(c, n)][s]["err"][k] <= TOL[k]]
                vals.append(min(ok_n) if ok_n else 99)
            nstar[s] = float(np.median(vals))
        summary[k] = {"median_diff_(U-C)": med, "ci95": [float(lo), float(hi)], "C_wins": bool(win), "per_N_median_diff": per_n, "N_star_median": nstar}
    fr = {s: a / b for s, (a, b) in fail.items()}
    supported = wins >= 3 and fr["curvature"] <= fr["uniform_pwl"]
    out = {"wins": int(wins), "failure_rate": fr, "H4_supported": bool(supported), "per_measurement": summary}
    (OUT / "heldout_summary.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))
    print("H4 SUPPORTED" if supported else "H4 NOT SUPPORTED (null/negative result, reported as such)")


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else "tune")
