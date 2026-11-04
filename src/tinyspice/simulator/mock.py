"""Deterministic mock simulator (no ngspice needed) with fault injection for tests and recovery development.

The curves are smooth analytic stand-ins, NOT a device model. Never use mock output as a result."""
from __future__ import annotations

from pathlib import Path

import numpy as np

from tinyspice.schemas.spec import AnalysisType, ExperimentSpec
from tinyspice.simulator.base import SimResult, wrap_arrays

FAULTS = {"timeout", "nonconvergence", "missing_include", "nonzero_exit", "truncated", "nan"}


class MockSimulator:
    name = "mock"

    def __init__(self, fault: str | None = None, fail_times: int | None = None):
        if fault is not None and fault not in FAULTS:
            raise ValueError(f"unknown fault '{fault}'; choose from {sorted(FAULTS)}")
        self.fault, self.fail_times, self.calls = fault, fail_times, 0

    def version(self) -> str:
        return "mock-1"

    def curve(self, spec: ExperimentSpec, points=None) -> tuple[np.ndarray, np.ndarray]:
        sw = spec.sweep
        x = np.asarray(points, float) if points is not None else np.linspace(sw.start, sw.stop, sw.n_points)
        wl, vt, vth, k = spec.width_um / spec.length_um, 0.0259, 0.45, 2e-4
        if spec.analysis is AnalysisType.IDVG:
            vds = spec.vds_v or 0.0
            y = 1e-6 * wl * np.log1p(np.exp((x - vth) / (2 * 1.3 * vt))) ** 2 * (1 + 0.05 * vds)
        else:
            vov = max((spec.vgs_v or 0.0) - vth, 1e-3)
            xe = np.minimum(x, vov)
            y = k * wl * (vov * xe - xe**2 / 2) * (1 + 0.05 * x)
        return x, y

    def run(self, spec: ExperimentSpec, run_dir: Path | None = None, points=None, timeout_s=None, solver_overrides=None, extra_lines=()) -> SimResult:
        self.calls += 1
        base = dict(simulator_version=self.version(), meta={"mock": True})
        active = self.fault and (self.fail_times is None or self.calls <= self.fail_times)
        if active and self.fault in {"timeout", "nonconvergence", "missing_include", "nonzero_exit"}:
            code = {"timeout": "TIMEOUT", "nonconvergence": "NONCONVERGENCE",
                    "missing_include": "MISSING_INCLUDE", "nonzero_exit": "NONZERO_EXIT"}[self.fault]
            return SimResult(ok=False, error_code=code, error_detail=f"injected fault: {self.fault}", **base)
        x, y = self.curve(spec, points)
        if active and self.fault == "truncated":
            x, y = x[:-5], y[:-5]
        if active and self.fault == "nan":
            y = y.copy(); y[len(y) // 2] = np.nan
        return wrap_arrays(spec, x, y, points=points, **base)
