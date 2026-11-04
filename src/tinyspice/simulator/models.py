"""Model profiles: how to include a model and instantiate a device. Netlists are built from these fixed
templates plus validated numbers only; no free text from users or LLMs ever reaches the netlist."""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from tinyspice.schemas.spec import DeviceType
from tinyspice.simulator.tools import ToolPaths


class UnknownModel(Exception):
    pass


def _n(v: float) -> str:
    return f"{v:.12g}"


def _q(path: Path) -> str:
    s = str(path).replace("\\", "/")
    if any(c in s for c in ('"', "\n", "\r")):
        raise ValueError(f"unsafe character in path: {s!r}")
    return f'"{s}"'


@dataclass(frozen=True)
class ModelProfile:
    name: str
    device_type: DeviceType
    preamble: tuple[str, ...]
    instance: Callable[[float, float], str]  # (width_um, length_um) -> element line
    control_lines: tuple[str, ...]
    model_files: tuple[Path, ...]
    educational: bool
    corner: str
    note: str


def _builtin() -> ModelProfile:
    return ModelProfile(
        name="builtin_level1_nmos", device_type=DeviceType.NMOS,
        preamble=(".model NMOD NMOS (LEVEL=1 VTO=0.5 KP=2e-4 LAMBDA=0.02 GAMMA=0.4 PHI=0.7)",),
        instance=lambda w, l: f"M1 d g 0 b NMOD W={_n(w * 1e-6)} L={_n(l * 1e-6)}",
        control_lines=(), model_files=(), educational=True, corner="n/a",
        note="Educational SPICE Level-1 model for runner smoke tests ONLY. No subthreshold conduction; "
             "never use for SS/VTH claims or any accuracy claim.",
    )


def _sky130_nfet(tools: ToolPaths, corner: str = "tt") -> ModelProfile:
    if tools.sky130_root is None:
        raise UnknownModel("SKY130 files not installed; run scripts/setup_tools.py")
    inv = tools.sky130_root / "parameters" / "invariant.spice"
    cor = tools.sky130_root / "cells" / "nfet_01v8" / f"sky130_fd_pr__nfet_01v8__{corner}.corner.spice"
    pm3 = cor.with_name(f"sky130_fd_pr__nfet_01v8__{corner}.pm3.spice")
    for f in (inv, cor, pm3):
        if not f.exists():
            raise UnknownModel(f"missing model file: {f}")
    return ModelProfile(
        name="sky130_fd_pr__nfet_01v8", device_type=DeviceType.NMOS,
        preamble=(".option scale=1e-6", f".include {_q(inv)}", ".param mc_mm_switch=0 mc_pr_switch=0",
                  f".include {_q(cor)}"),
        instance=lambda w, l: f"X1 d g 0 b sky130_fd_pr__nfet_01v8 W={_n(w)} L={_n(l)}",
        control_lines=("set ngbehavior=hsa", "set skywaterpdk", "set ng_nomodcheck"),
        model_files=(inv, cor, pm3), educational=False, corner=corner,
        note="SkyWater SKY130 open PDK model (simulator-generated; not measured silicon).",
    )


def get_profile(model_name: str, tools: ToolPaths) -> ModelProfile:
    if model_name == "builtin_level1_nmos":
        return _builtin()
    if model_name == "sky130_fd_pr__nfet_01v8":
        return _sky130_nfet(tools)
    raise UnknownModel(f"no profile for model '{model_name}'")
