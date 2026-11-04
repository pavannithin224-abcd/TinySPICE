"""Spike: does real ngspice accept a non-uniform sweep via `dc <src> LIST v1 v2 ...`, and do the values match a uniform sweep?
Throwaway probe (kept for the record). Runs real ngspice inside the project; nothing outside it is touched."""
import re
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
OUT = Path(__file__).resolve().parents[1] / "experiments" / "runs" / "_sanity" / "dclist"
if OUT.exists():
    shutil.rmtree(OUT)
OUT.mkdir(parents=True)

spec = ExperimentSpec.model_validate({
    "device_type": "nmos", "model_name": "sky130_fd_pr__nfet_01v8", "width_um": 1.0, "length_um": 0.18, "temperature_c": 27.0,
    "analysis": "idvg", "sweep": {"start": 0.0, "stop": 1.8, "step": 0.02}, "vds_v": 1.8, "measurements": ["VTH"], "budget": {"max_points": 200}})
net = build_netlist(spec, get_profile(spec.model_name, tools))
dc_line = next(l for l in net.splitlines() if l.startswith("dc "))


def run(tag, line):
    d = OUT / tag
    d.mkdir()
    (d / "n.cir").write_text(net.replace(dc_line, line), encoding="utf-8", newline="\n")
    t0 = time.monotonic()
    p = subprocess.run([str(exe), "-b", "n.cir"], cwd=d, capture_output=True, text=True, timeout=120, stdin=subprocess.DEVNULL)
    dt = time.monotonic() - t0
    raw = d / "raw.dat"
    if p.returncode != 0 or not raw.exists():
        print(tag, "FAILED rc", p.returncode, (p.stdout + p.stderr)[-400:].replace("\n", " | "))
        return None, dt
    a = np.loadtxt(raw, ndmin=2)
    return a, dt


uni, t_uni = run("uniform", dc_line)
print(f"uniform: rows={len(uni)} runtime={t_uni:.2f}s")

pts = [0.0, 0.1, 0.2, 0.3, 0.4, 0.45, 0.5, 0.55, 0.6, 0.65, 0.7, 0.8, 1.0, 1.4, 1.8]
lst, t_lst = run("list", "dc VGS LIST " + " ".join(f"{v:g}" for v in pts))
if lst is not None:
    print(f"LIST: rows={len(lst)} (asked {len(pts)}) runtime={t_lst:.2f}s")
    print("x column equals requested points:", np.allclose(lst[:, 0], pts, atol=1e-12))
    ref = {round(x, 6): y for x, y in zip(uni[:, 0], uni[:, 1])}
    rel = []
    for x, y in zip(lst[:, 0], lst[:, 1]):
        r = ref.get(round(x, 6))
        if r is not None:
            rel.append(abs(y - r) / max(abs(r), 1e-30))
    print(f"points shared with the uniform grid: {len(rel)}; max relative difference in Id there: {max(rel):.2e}")

# edge cases the executor will rely on
for tag, vals in (("unsorted", [0.0, 1.8, 0.9]), ("dupe", [0.0, 0.9, 0.9, 1.8]), ("single", [0.9])):
    a, _ = run(tag, "dc VGS LIST " + " ".join(f"{v:g}" for v in vals))
    print(tag, "->", None if a is None else f"rows={len(a)} x={a[:, 0].tolist()}")

# a long list (the largest budget we plan to allow) and a command-line length sanity check
big = np.round(np.linspace(0, 1.8, 200), 6).tolist()
a, dt = run("long200", "dc VGS LIST " + " ".join(f"{v:g}" for v in big))
print("long200 ->", None if a is None else f"rows={len(a)} runtime={dt:.2f}s")
