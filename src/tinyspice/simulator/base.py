"""Simulator abstraction: the rest of TinySPICE only sees `Simulator` and `SimResult`."""
from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Protocol

import numpy as np

from tinyspice.schemas.spec import ExperimentSpec
from tinyspice.simulator.validate import validate_output, validate_points


@dataclass(frozen=True)
class SimResult:
    """Outcome of one simulator invocation. `ok` is True ONLY if the process succeeded AND the
    output passed validation. x = swept voltage (V); y = drain current INTO the drain (A)."""

    ok: bool
    x: np.ndarray | None = None
    y: np.ndarray | None = None
    error_code: str | None = None
    error_detail: str | None = None
    exit_code: int | None = None
    stdout: str = ""
    stderr: str = ""
    runtime_s: float = 0.0
    simulator_version: str | None = None
    netlist_path: Path | None = None
    raw_path: Path | None = None
    meta: dict = field(default_factory=dict)


class Simulator(Protocol):
    name: str

    def version(self) -> str: ...

    def run(self, spec: ExperimentSpec, run_dir: Path, points=None) -> SimResult: ...


def wrap_arrays(spec: ExperimentSpec, x, y, points=None, **kw) -> SimResult:
    """Validate arrays against the spec's sweep (or an explicit point list) and wrap into a SimResult."""
    if points is not None:
        ok, code, detail = validate_points(x, y, points)
    else:
        ok, code, detail = validate_output(x, y, spec.sweep.n_points, spec.sweep.start, spec.sweep.stop)
    if ok:
        return SimResult(ok=True, x=np.asarray(x, float), y=np.asarray(y, float), **kw)
    return SimResult(ok=False, error_code=code, error_detail=detail, **kw)
