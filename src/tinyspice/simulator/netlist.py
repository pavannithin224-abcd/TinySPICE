"""Deterministic netlist generation from a validated ExperimentSpec + ModelProfile."""
from __future__ import annotations

from tinyspice.planner.planner import spec_hash
from tinyspice.schemas.spec import AnalysisType, DeviceType, ExperimentSpec
from tinyspice.simulator.models import ModelProfile, _n

RAW_NAME = "raw.dat"


class UnsupportedDevice(Exception):
    pass


def build_netlist(spec: ExperimentSpec, profile: ModelProfile) -> str:
    if spec.device_type is not DeviceType.NMOS or profile.device_type is not DeviceType.NMOS:
        raise UnsupportedDevice("only NMOS is implemented")
    sw = spec.sweep
    step = sw.step if sw.step is not None else (sw.stop - sw.start) / (sw.points - 1)  # type: ignore[operator]
    if spec.analysis is AnalysisType.IDVG:
        vds, vgs, sweep_src = _n(spec.vds_v), "0", "VGS"  # type: ignore[arg-type]
    else:
        vds, vgs, sweep_src = "0", _n(spec.vgs_v), "VDS"  # type: ignore[arg-type]
    lines = [
        f"* TinySPICE generated netlist (spec {spec_hash(spec)[:12]}); do not edit",
        *profile.preamble,
        f"VDS d 0 {vds}",
        f"VGS g 0 {vgs}",
        f"VB b 0 {_n(spec.vbs_v)}",
        profile.instance(spec.width_um, spec.length_um),
        profile.solver_options,
        f".temp {_n(spec.temperature_c)}",
        ".control",
        *profile.control_lines,
        f"dc {sweep_src} {_n(sw.start)} {_n(sw.stop)} {_n(step)}",
        "let id = -i(VDS)",
        f"wrdata {RAW_NAME} id",
        "quit",
        ".endc",
        ".end",
    ]
    return "\n".join(lines) + "\n"
