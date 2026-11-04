"""E3: uniform (PWL) vs curvature vs window sampling against a dense reference. See docs/STAGE4_PREREG.md (frozen before running).
  python scripts/run_e3.py tune            # fits pilot_frac (arm C) on the TUNING conditions only
  python scripts/run_e3.py tune_window     # fits window_target (arm W) on the TUNING conditions only
  python scripts/run_e3.py heldout         # ONE run on the held-out conditions with the tuned values
A phase argument is REQUIRED and unknown phases are refused (a typo must never fall through to the one-shot held-out run).
Outputs go to results/stage4/. Needs ngspice + SKY130 in ./.tools."""
import itertools
import json
import shutil
import sys
import time
from pathlib import Path

PHASES = ("tune", "tune_window", "heldout")
if __name__ == "__main__" and (len(sys.argv) != 2 or sys.argv[1] not in PHASES):   # checked BEFORE any heavy import or work
    sys.exit(f"usage: run_e3.py <{'|'.join(PHASES)}>  (got {sys.argv[1:]!r})")

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
WTARGETS = [5, 6, 8]
MEAS = ["VTH", "SS", "GM", "ION", "IOFF"]
INFORMATIVE = ["VTH", "SS", "GM"]
ARMS = ("uniform_pwl", "curvature", "window")
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


def run_cell(c, n, strategy, frac, wt, tag):
    spec = spec_for(c, n)
    d = RUNS / f"{tag}_{strategy}_{c[0]}_{c[1]}_{c[2]}_{n}_{frac}_{wt}"
    if d.exists():
        shutil.rmtree(d)
    d.mkdir(parents=True)
    sim = run_sweep(spec, SIM, d, strategy, pilot_frac=frac, window_target=wt)
    if not sim.ok:
        return {k: None for k in MEAS}, sim.error_code, 0.0
    return measure(spec, sim), None, sim.runtime_s


def table(conds, frac, wt, tag, arms=ARMS):
    rows = []
    for c in conds:
        ref = reference(c)
        for n in NS:
            for strat in arms:
                vals, code, rt = run_cell(c, n, strat, frac, wt, tag)
                rows.append({"cond": list(c), "n": n, "strategy": strat, "frac": frac, "window_target": wt, "sim_error": code,
                             "runtime_s": rt, "values": vals, "err": {k: err(k, vals[k], ref[k]) for k in MEAS}, "ref": ref})
    return rows


def score(e, k):  # normalised error with the pre-registered failure penalty
    return PENALTY if e is None else e / TOL[k]


def main(phase):
    assert phase in PHASES
    OUT.mkdir(parents=True, exist_ok=True)
    t0 = time.monotonic()
    if phase == "tune":
        best = {}
        for fr in FRACS:
            rows = table(TUNE, fr, 6, f"tune{fr}", arms=("curvature",))
            best[fr] = float(np.mean([score(r["err"][k], k) for r in rows for k in MEAS]))
            print(f"pilot_frac={fr}: mean normalised error {best[fr]:.4f} (tuning conditions only)")
        pick = min(best, key=lambda f: (best[f], f))
        (OUT / "tune.json").write_text(json.dumps({"pilot_frac": pick, "scores": best, "tuning_conditions": TUNE, "heldout_conditions": HELD}, indent=1))
        print("CHOSEN pilot_frac =", pick, f"({time.monotonic() - t0:.0f}s)")
        return
    frac = json.loads((OUT / "tune.json").read_text())["pilot_frac"]
    if phase == "tune_window":
        best = {}
        for wt in WTARGETS:
            rows = table(TUNE, frac, wt, f"tunew{wt}", arms=("window",))
            best[wt] = float(np.mean([score(r["err"][k], k) for r in rows for k in MEAS]))
            print(f"window_target={wt}: mean normalised error {best[wt]:.4f} (tuning conditions only, pilot_frac={frac})")
        pick = min(best, key=lambda w: (best[w], w))
        (OUT / "tune_window.json").write_text(json.dumps({"window_target": pick, "scores": best, "pilot_frac": frac}, indent=1))
        print("CHOSEN window_target =", pick, f"({time.monotonic() - t0:.0f}s)")
        return
    # phase == "heldout"
    if (OUT / "heldout.json").exists():
        sys.exit("held-out results already exist: the held-out run is executed ONCE (see STAGE4_PREREG.md). Refusing.")
    if not (OUT / "tune_window.json").exists():
        sys.exit("run `tune_window` first (window_target must be fit on the tuning conditions before the held-out run).")
    wt = json.loads((OUT / "tune_window.json").read_text())["window_target"]
    rows = table(HELD, frac, wt, "held")
    (OUT / "heldout.json").write_text(json.dumps({"pilot_frac": frac, "window_target": wt, "rows": rows}, indent=1))
    analyse(rows)
    print(f"done in {time.monotonic() - t0:.0f}s")


def _diffs(by, k, arm):
    d = {}
    for key, group in by.items():
        eu, ea = group["uniform_pwl"]["err"][k], group[arm]["err"][k]
        if eu is None and ea is None:
            d[key] = 0.0
        else:
            d[key] = (PENALTY * TOL[k] if eu is None else eu) - (PENALTY * TOL[k] if ea is None else ea)
    return d


def analyse(rows):
    by = {}
    for r in rows:
        by.setdefault((tuple(r["cond"]), r["n"]), {})[r["strategy"]] = r
    conds = sorted({k[0] for k in by})

    def fail_rate(arm, ms):
        cells = [r["err"][k] for r in rows if r["strategy"] == arm for k in ms]
        return sum(e is None for e in cells) / len(cells)

    out = {"arms": {}}
    for arm in ("curvature", "window"):
        rng = np.random.default_rng(20261104)
        per, wins = {}, {}
        for k in MEAS:
            d = _diffs(by, k, arm)
            med = float(np.median(list(d.values())))
            boots = [np.median([d[(c, n)] for c in [conds[i] for i in rng.integers(0, len(conds), len(conds))] for n in NS]) for _ in range(2000)]
            lo, hi = np.percentile(boots, [2.5, 97.5])
            wins[k] = bool(med > 0 and lo > 0)
            nstar = {}
            for s in ("uniform_pwl", arm):
                vals = []
                for c in conds:
                    ok_n = [n for n in NS if by[(c, n)][s]["err"][k] is not None and by[(c, n)][s]["err"][k] <= TOL[k]]
                    vals.append(min(ok_n) if ok_n else 99)
                nstar[s] = float(np.median(vals))
            per[k] = {"median_diff_(U-arm)": med, "ci95": [float(lo), float(hi)], "arm_wins": wins[k],
                      "per_N_median_diff": {n: float(np.median([d[(c, n)] for c in conds])) for n in NS}, "N_star_median": nstar}
        ss_ok = {s: {n: float(np.mean([by[(c, n)][s]["err"]["SS"] is not None for c in conds])) for n in NS} for s in ("uniform_pwl", arm)}
        fr_inf = {"uniform_pwl": fail_rate("uniform_pwl", INFORMATIVE), arm: fail_rate(arm, INFORMATIVE)}
        fr_all = {"uniform_pwl": fail_rate("uniform_pwl", MEAS), arm: fail_rate(arm, MEAS)}
        amended = sum(wins[k] for k in INFORMATIVE) >= 2 and fr_inf[arm] <= fr_inf["uniform_pwl"]
        original = sum(wins.values()) >= 3 and fr_all[arm] <= fr_all["uniform_pwl"]
        out["arms"][arm] = {"per_measurement": per, "ss_extraction_success_by_N": ss_ok, "failure_rate_informative": fr_inf,
                            "failure_rate_all": fr_all, "H4_supported_amended": bool(amended), "H4_supported_original": bool(original)}
    (OUT / "heldout_summary.json").write_text(json.dumps(out, indent=1))
    print(json.dumps(out, indent=1))
    for arm, a in out["arms"].items():
        print(f"{arm}: amended criterion {'SUPPORTED' if a['H4_supported_amended'] else 'NOT supported'}; original criterion {'SUPPORTED' if a['H4_supported_original'] else 'NOT supported'}")


if __name__ == "__main__":
    main(sys.argv[1])
