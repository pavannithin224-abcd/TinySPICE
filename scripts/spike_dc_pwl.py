"""Spike 2: arbitrary non-uniform sweep points in ONE ngspice process.
 (C) integer-index dc sweep + behavioral gate source  B g 0 V = pwl(v(idx), 0,v0, 1,v1, ...)   (knots land exactly on integers)
 (A) several uniform `dc` sub-sweeps with separate wrdata files in one control block.
Compared against a uniform sweep of the same device at shared points. Throwaway probe, kept for the record."""
import shutil
import subprocess
import time
from pathlib import Path

import numpy as np

from tinyspice.schemas import ExperimentSpec
from tinyspice.simulator.models import get_profile
from tinyspice.simulator.netlist import build_netlist
from tinyspice.simulator.tools import find_tools

tools = find_tools()
exe = tools.ngspice_exe
OUT = Path(__file__).resolve().parents[1] / "experiments" / "runs" / "_sanity" / "dclist2"
if OUT.exists():
    shutil.rmtree(OUT)
OUT.mkdir(parents=True)
spec = ExperimentSpec.model_validate({
    "device_type": "nmos", "model_name": "sky130_fd_pr__nfet_01v8", "width_um": 1.0, "length_um": 0.18, "temperature_c": 27.0,
    "analysis": "idvg", "sweep": {"start": 0.0, "stop": 1.8, "step": 0.02}, "vds_v": 1.8, "measurements": ["VTH"], "budget": {"max_points": 200}})
net = build_netlist(spec, get_profile(spec.model_name, tools))
lines = net.splitlines()
dc_line = next(l for l in lines if l.startswith("dc "))
vgs_line = next(l for l in lines if l.startswith("VGS "))
wr_line = next(l for l in lines if l.startswith("wrdata"))


def run(tag, text):
    d = OUT / tag
    d.mkdir()
    (d / "n.cir").write_text(text, encoding="utf-8", newline="\n")
    t0 = time.monotonic()
    p = subprocess.run([str(exe), "-b", "n.cir"], cwd=d, capture_output=True, text=True, timeout=120, stdin=subprocess.DEVNULL)
    return d, p, time.monotonic() - t0


def pwl_netlist(pts):
    toks = [f"{i},{v:.9g}" for i, v in enumerate(pts)]
    chunks = [",".join(toks[k:k + 6]) for k in range(0, len(toks), 6)]
    bsrc = "BGS g 0 V = pwl(v(idx), " + (",\n+ ".join(chunks)) + ")"
    out = []
    for l in lines:
        if l == vgs_line:
            out += ["VIDX idx 0 0", bsrc]
        elif l == dc_line:
            out.append(f"dc VIDX 0 {len(pts) - 1} 1")
        elif l == wr_line:
            out.append("wrdata raw.dat v(g) id")
        else:
            out.append(l)
    return "\n".join(out) + "\n"


d, p, t_uni = run("uniform", net)
uni = np.loadtxt(d / "raw.dat", ndmin=2)
ref = {round(x, 6): y for x, y in uni[:, :2]}
print(f"uniform rows={len(uni)} {t_uni:.2f}s")


def compare(tag, pts):
    d, p, dt = run(tag, pwl_netlist(pts))
    raw = d / "raw.dat"
    if p.returncode != 0 or not raw.exists():
        print(tag, "FAILED rc", p.returncode, (p.stdout + p.stderr)[-500:].replace("\n", " | "))
        return
    a = np.loadtxt(raw, ndmin=2)
    vg, idv = a[:, 1], a[:, -1]
    ok_x = np.allclose(vg, pts, atol=1e-9)
    rel = [abs(i - ref[round(v, 6)]) / max(abs(ref[round(v, 6)]), 1e-30) for v, i in zip(vg, idv) if round(v, 6) in ref]
    print(f"{tag}: rows={len(a)}/{len(pts)} gate values exact={ok_x} {dt:.2f}s shared-with-uniform={len(rel)} max rel dId={max(rel) if rel else float('nan'):.2e}")


compare("pwl15", [0.0, 0.1, 0.2, 0.3, 0.4, 0.44, 0.5, 0.56, 0.6, 0.64, 0.7, 0.8, 1.0, 1.4, 1.8])
compare("pwl200", np.round(np.linspace(0, 1.8, 200), 6).tolist())
compare("pwl5", [0.0, 0.5, 0.6, 1.2, 1.8])
compare("pwl2", [0.0, 1.8])
# A: sub-sweeps
seg = [(0.0, 0.3, 0.1), (0.3, 0.7, 0.05), (0.7, 1.8, 0.275)]
body = []
for l in lines:
    if l == dc_line:
        for k, (a0, a1, s) in enumerate(seg):
            body += [f"dc VGS {a0} {a1} {s}", "let id = -i(VDS)", f"wrdata raw{k}.dat id"]
    elif l.startswith("let id") or l == wr_line:
        continue
    else:
        body.append(l)
d, p, dt = run("segments", "\n".join(body) + "\n")
n = [len(np.loadtxt(d / f"raw{k}.dat", ndmin=2)) for k in range(3) if (d / f"raw{k}.dat").exists()]
print(f"segments: files rows={n} rc={p.returncode} {dt:.2f}s")
