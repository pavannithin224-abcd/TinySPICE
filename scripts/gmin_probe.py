"""Is Ioff a gmin/abstol artefact? Re-run the same netlist with different solver options."""
import re, shutil, subprocess
from pathlib import Path
import numpy as np

ROOT = Path(__file__).resolve().parents[1]
EXE = next((ROOT / ".tools/ngspice").rglob("ngspice_con.exe"))
SRC = (ROOT / "experiments/runs/_sanity/r01/netlist.cir").read_text()   # W=1 L=0.18 T=27 VDS=1.8
OUT = ROOT / "experiments/runs/_sanity/gmin"
if OUT.exists():
    shutil.rmtree(OUT)


def probe(tag, opts, temp=None):
    d = OUT / tag
    d.mkdir(parents=True)
    net = SRC.replace(".control", (opts + "\n" if opts else "") + ".control", 1) if False else SRC
    if opts:
        net = net.replace(".temp", opts + "\n.temp", 1)
    if temp is not None:
        net = re.sub(r"\.temp \S+", f".temp {temp}", net)
    (d / "n.cir").write_text(net)
    p = subprocess.run([str(EXE), "-b", "n.cir"], cwd=d, capture_output=True, text=True, timeout=120, stdin=subprocess.DEVNULL)
    if p.returncode != 0 or not (d / "raw.dat").exists():
        return tag, "FAILED", p.stderr[-200:]
    a = np.loadtxt(d / "raw.dat", ndmin=2)
    x, y = a[:, 0], a[:, 1]
    return tag, f"Id(0)={np.interp(0, x, y):.3e}", f"Id(0.2)={np.interp(0.2, x, y):.3e} Id(0.45)={np.interp(0.45, x, y):.3e} Ion={y[-1]:.4e} min={y.min():.2e}"


for tag, opts, temp in [("default", "", None),
                        ("gmin1e-15", ".option gmin=1e-15", None),
                        ("gmin1e-18", ".option gmin=1e-18", None),
                        ("gmin1e-18_abstol1e-18", ".option gmin=1e-18 abstol=1e-18", None),
                        ("gmin1e-20_abstol1e-20_reltol1e-6", ".option gmin=1e-20 abstol=1e-20 reltol=1e-6", None),
                        ("default_T-40", "", -40),
                        ("tight_T-40", ".option gmin=1e-18 abstol=1e-18", -40)]:
    print(*probe(tag, opts, temp), sep=" | ")
