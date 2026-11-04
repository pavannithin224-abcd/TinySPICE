"""Spike: how does real ngspice-47 report each netlist-level injected fault, and does the solver ladder fix NONCONVERGENCE?"""
import shutil
from pathlib import Path

from tinyspice.recovery import SOLVER_LADDER
from tinyspice.schemas import ExperimentSpec
from tinyspice.simulator import NgspiceSimulator

OUT = Path(__file__).resolve().parents[1] / "experiments" / "runs" / "_sanity" / "inject"
if OUT.exists():
    shutil.rmtree(OUT)
spec = ExperimentSpec.model_validate({
    "device_type": "nmos", "model_name": "sky130_fd_pr__nfet_01v8", "width_um": 1.0, "length_um": 0.18, "temperature_c": 27.0,
    "analysis": "idvg", "sweep": {"start": 0.0, "stop": 1.8, "points": 50}, "vds_v": 1.8, "measurements": ["VTH"],
    "budget": {"max_points": 60}})
sim = NgspiceSimulator()


def show(tag, **kw):
    r = sim.run(spec, OUT / tag, **kw)
    print(f"{tag:28s} ok={r.ok} code={r.error_code} detail={(r.error_detail or '')[:70]!r} rows={None if r.x is None else len(r.x)}")
    if not r.ok:
        txt = (r.stdout + r.stderr).replace("\n", " | ")
        print("      text:", txt[-260:])


show("clean")
show("missing_include", extra_lines=(".include C:/definitely/not/here/model.spice",))
show("syntax_garbage", extra_lines=("this is ((( not a spice card",))
show("syntax_bad_card", extra_lines=(".bogus_card 1 2 3",))
show("voltage_source_loop", extra_lines=("VBAD d 0 3.3",))
show("floating_gate_resistor0", extra_lines=("RZERO d g 0",))
show("tiny_timeout", timeout_s=0.01)
