"""Fault injection for the Stage-5 failure suite (E4). Wraps a REAL simulator; faults are either real ngspice failures provoked by a
netlist edit (missing include, syntax, voltage-source loop -> genuine NONCONVERGENCE, tiny process timeout) or deterministic
post-processing of a real result (truncation, NaN) or a fabricated unknown code.

Modes: "transient" = first simulator call only; "persistent" = every call.
HONEST LIMIT: for `nonconvergence` + transient, the fault is withdrawn once a solver override is applied - the classification,
accounting and status path are real, but whether the solver ladder cures a PHYSICAL convergence failure is NOT tested here
(no natural one exists for this device).
"""
from __future__ import annotations

import numpy as np

from tinyspice.simulator.base import SimResult, wrap_arrays

KINDS = {"missing_include", "netlist_syntax", "nonconvergence", "timeout", "truncated", "nan", "unknown_code"}
_LINES = {
    "missing_include": (".include C:/definitely/not/here/model.spice",),
    "netlist_syntax": ("this is ((( not a spice card",),
    "nonconvergence": ("VBAD d 0 3.3",),            # parallel voltage sources: ngspice reports a genuine DC convergence failure
}


class InjectingSimulator:
    name = "injecting"

    def __init__(self, inner, kind: str, mode: str = "transient"):
        if kind not in KINDS or mode not in ("transient", "persistent"):
            raise ValueError(f"bad injection {kind!r}/{mode!r}")
        self.inner, self.kind, self.mode, self.calls = inner, kind, mode, 0

    def version(self) -> str:
        return self.inner.version()

    def run(self, spec, run_dir, points=None, timeout_s=None, solver_overrides=None, **_):
        self.calls += 1
        active = self.mode == "persistent" or self.calls == 1
        kw = {k: v for k, v in (("points", points), ("timeout_s", timeout_s), ("solver_overrides", solver_overrides)) if v is not None}
        if active:
            if self.kind in _LINES and not (self.kind == "nonconvergence" and self.mode == "transient" and solver_overrides):
                kw["extra_lines"] = _LINES[self.kind]
            if self.kind == "timeout":
                kw["timeout_s"] = 0.01
            if self.kind == "unknown_code":
                return SimResult(ok=False, error_code="WEIRD_FAULT", error_detail="injected unrecognised fault")
        r = self.inner.run(spec, run_dir, **kw)
        if r.ok and active and self.kind in ("truncated", "nan"):
            x, y = np.array(r.x), np.array(r.y)
            if self.kind == "truncated":
                x, y = x[:-5], y[:-5]
            else:
                y[len(y) // 2] = np.nan
            return wrap_arrays(spec, x, y, points=points, simulator_version=r.simulator_version, netlist_path=r.netlist_path,
                               raw_path=r.raw_path, meta=r.meta, runtime_s=r.runtime_s)
        return r
