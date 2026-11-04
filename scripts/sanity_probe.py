"""One-off sanity probe: do W, L, T, and the Id-Vd sweep behave physically in REAL ngspice runs?"""
import json, shutil, sys, time
from pathlib import Path
import numpy as np
from tinyspice.schemas import ExperimentSpec
from tinyspice.simulator import NgspiceSimulator

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "experiments" / "runs" / "_sanity"
if OUT.exists():
    shutil.rmtree(OUT)
base = json.loads((ROOT / "configs/experiments/example_idvg.json").read_text())
sim = NgspiceSimulator()
n = 0


def run(**over):
    global n
    n += 1
    d = {**base, **over}
    s = ExperimentSpec.model_validate(d)
    r = sim.run(s, OUT / f"r{n:02d}")
    assert r.ok, (over, r.error_code, r.error_detail)
    return r


def at(r, v):
    return float(np.interp(v, r.x, r.y))

print("== width scaling (L=0.18, T=27, VDS=1.8)")
for W in (1.0, 2.0, 4.0):
    r = run(width_um=W)
    print(f"W={W}: Ioff(VGS=0)={at(r,0):.3e}  Ion(VGS=1.8)={at(r,1.8):.3e}")
r1, r2, r4 = run(width_um=1.0), run(width_um=2.0), run(width_um=4.0)
print("Ion ratio W2/W1 =", round(at(r2, 1.8) / at(r1, 1.8), 3), " W4/W1 =", round(at(r4, 1.8) / at(r1, 1.8), 3))

print("== length scaling (W=1, T=27)")
for L in (0.18, 0.36, 1.0):
    r = run(length_um=L)
    print(f"L={L}: Ion={at(r,1.8):.3e}")

print("== temperature (W=1, L=0.18)")
for T in (-40.0, 27.0, 125.0):
    r = run(temperature_c=T)
    print(f"T={T}: Ioff={at(r,0):.3e}  Ion={at(r,1.8):.3e}  Id(0.45V)={at(r,0.45):.3e}")

print("== Id-Vd (VGS=1.2, W=1, L=0.18)")
d = {**base, "analysis": "idvd", "vds_v": None, "vgs_v": 1.2, "measurements": ["GDS"], "ion_vgs_v": None, "ioff_vgs_v": None}
s = ExperimentSpec.model_validate(d)
r = sim.run(s, OUT / "idvd")
assert r.ok, (r.error_code, r.error_detail)
print("rows", len(r.x), " Id(VDS=0)=", f"{r.y[0]:.3e}", " Id(0.1)=", f"{at(r,0.1):.3e}", " Id(0.6)=", f"{at(r,0.6):.3e}", " Id(1.8)=", f"{r.y[-1]:.3e}")
print("monotonic increasing:", bool((np.diff(r.y) > 0).all()), " slope@0.1 =", f"{(at(r,0.12)-at(r,0.08))/0.04:.3e}", " slope@1.7 =", f"{(at(r,1.76)-at(r,1.64))/0.12:.3e}")

print("== real timeout")
d = {**base, "budget": {"max_points": 200, "max_runtime_s": 0.01}}
t0 = time.monotonic()
r = sim.run(ExperimentSpec.model_validate(d), OUT / "timeout")
print("ok:", r.ok, "code:", r.error_code, "detail:", r.error_detail, f"elapsed {time.monotonic()-t0:.2f}s")
