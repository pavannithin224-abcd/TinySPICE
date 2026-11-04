"""Deterministic netlist generation from a validated ExperimentSpec + ModelProfile."""
from __future__ import annotations

from tinyspice.planner.planner import spec_hash
from tinyspice.recovery import solver_options_line
from tinyspice.schemas.spec import AnalysisType, DeviceType, ExperimentSpec
from tinyspice.simulator.models import ModelProfile, _n

RAW_NAME = "raw.dat"


class UnsupportedDevice(Exception):
    pass


class UnsupportedSweep(Exception):
    pass


def _pwl_gate(points) -> list[str]:
    """Index-swept gate: VIDX idx 0 0 (dc 0..N-1 step 1) + BGS g 0 V = pwl(v(idx), 0,v0, 1,v1, ...) (verified on ngspice-47)."""
    toks = [f"{i},{float(v):.9g}" for i, v in enumerate(points)]
    chunks = [",".join(toks[k:k + 6]) for k in range(0, len(toks), 6)]
    return ["VIDX idx 0 0", "BGS g 0 V = pwl(v(idx), " + ",\n+ ".join(chunks) + ")"]


def build_netlist(spec: ExperimentSpec, profile: ModelProfile, points=None, solver_overrides=None, extra_lines=()) -> str:
    """solver_overrides: recovery-ladder options (whitelisted; gmin/abstol can never be changed).
    extra_lines: raw lines appended before .control - ONLY for fault-injection tests; never set by production code paths."""
    if spec.device_type is not DeviceType.NMOS or profile.device_type is not DeviceType.NMOS:
        raise UnsupportedDevice("only NMOS is implemented")
    override_line = solver_options_line(solver_overrides)
    if points is not None and spec.analysis is not AnalysisType.IDVG:
        raise UnsupportedSweep("explicit sweep points are implemented for Id-Vg only (Id-Vd senses current through the swept source)")
    sw = spec.sweep
    step = sw.step if sw.step is not None else (sw.stop - sw.start) / (sw.points - 1)  # type: ignore[operator]
    if spec.analysis is AnalysisType.IDVG:
        vds, vgs, sweep_src = _n(spec.vds_v), "0", "VGS"  # type: ignore[arg-type]
    else:
        vds, vgs, sweep_src = "0", _n(spec.vgs_v), "VDS"  # type: ignore[arg-type]
    if points is not None:
        pts = [float(p) for p in points]
        if len(pts) < 2 or any(b <= a for a, b in zip(pts, pts[1:])):
            raise UnsupportedSweep("explicit points must be >= 2 and strictly increasing")
        gate_lines, dc_line, wr_line = [*_pwl_gate(pts)], f"dc VIDX 0 {len(pts) - 1} 1", f"wrdata {RAW_NAME} v(g) id"
    else:
        gate_lines, dc_line, wr_line = [f"VGS g 0 {vgs}"], f"dc {sweep_src} {_n(sw.start)} {_n(sw.stop + step * 1e-3)} {_n(step)}", f"wrdata {RAW_NAME} id"
        # stop is nudged up by 0.1 % of a step: for steps like 1.8/49 ngspice's accumulated arithmetic otherwise drops the
        # last point (found in Stage 5: 49 rows for 50 planned). An extra row cannot appear: the next point is a full step away.
    lines = [
        f"* TinySPICE generated netlist (spec {spec_hash(spec)[:12]}); do not edit",
        *profile.preamble,
        f"VDS d 0 {vds}",
        *gate_lines,
        f"VB b 0 {_n(spec.vbs_v)}",
        profile.instance(spec.width_um, spec.length_um),
        profile.solver_options,
        *([override_line] if override_line else []),
        f".temp {_n(spec.temperature_c)}",
        *extra_lines,
        ".control",
        *profile.control_lines,
        dc_line,
        "let id = -i(VDS)",
        wr_line,
        "quit",
        ".endc",
        ".end",
    ]
    return "\n".join(lines) + "\n"
