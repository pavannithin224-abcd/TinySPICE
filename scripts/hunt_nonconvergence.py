"""Time-boxed hunt (30 min budget) for a NATURALLY non-converging SKY130 NFET run on ngspice-47, so the Stage-5 solver-ladder claim can
be tested on a physical convergence failure instead of an injected one. Bypasses the planner on purpose (hostile bias/geometry/temperature)."""
import shutil
import time
from pathlib import Path

from tinyspice.recovery import SOLVER_LADDER
from tinyspice.schemas import ExperimentSpec
from tinyspice.simulator import NgspiceSimulator

OUT = Path(__file__).resolve().parents[1] / "experiments" / "runs" / "_sanity" / "hunt"
if OUT.exists():
    shutil.rmtree(OUT)
sim = NgspiceSimulator()
T0 = time.monotonic()
found = []


def spec(W=1.0, L=0.18, T=27.0, vds=1.8, vgs_max=1.8, vbs=0.0, n=50):
    return ExperimentSpec.model_validate({
        "device_type": "nmos", "model_name": "sky130_fd_pr__nfet_01v8", "width_um": W, "length_um": L, "temperature_c": T,
        "analysis": "idvg", "sweep": {"start": 0.0, "stop": vgs_max, "points": n}, "vds_v": vds, "vbs_v": vbs, "measurements": ["VTH"],
        "budget": {"max_points": 500, "max_runtime_s": 60}})


cases = {}
for T in (-100, -40, 125, 200, 300, 400, 500):
    cases[f"T={T}"] = spec(T=T)
for vds in (3.0, 5.0, 8.0, 12.0, 20.0):
    cases[f"VDS={vds}"] = spec(vds=vds, vgs_max=vds)
for vbs in (-1.0, -3.0, -8.0, 1.0, 2.0):
    cases[f"VBS={vbs}"] = spec(vbs=vbs)
for W, L in ((100, 0.15), (100, 100), (0.36, 100), (1000, 0.15)):
    cases[f"W={W},L={L}"] = spec(W=W, L=L)
cases["vgs_max=10"] = spec(vgs_max=10.0, vds=10.0)
cases["T=400,VDS=5"] = spec(T=400, vds=5.0, vgs_max=5.0)
cases["T=-100,VDS=5"] = spec(T=-100, vds=5.0, vgs_max=5.0)

for tag, s in cases.items():
    if time.monotonic() - T0 > 25 * 60:
        print("time box reached")
        break
    r = sim.run(s, OUT / tag.replace("=", "_").replace(",", "_").replace(".", "p"), timeout_s=40)
    flag = "" if r.ok else f"   <-- {r.error_code}"
    print(f"{tag:16s} ok={r.ok} rows={None if r.x is None else len(r.x)} code={r.error_code}{flag}")
    if not r.ok and r.error_code == "NONCONVERGENCE":
        found.append((tag, s))

print("\nnatural NONCONVERGENCE cases:", [t for t, _ in found])
for tag, s in found:
    for i, step in enumerate(SOLVER_LADDER, 1):
        r = sim.run(s, OUT / (tag.replace("=", "_").replace(",", "_").replace(".", "p") + f"_ladder{i}"), timeout_s=40, solver_overrides=step)
        print(f"  {tag}: ladder step {i} {step} -> ok={r.ok} code={r.error_code} rows={None if r.x is None else len(r.x)}")
print(f"elapsed {time.monotonic() - T0:.0f}s")
