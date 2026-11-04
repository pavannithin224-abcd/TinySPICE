"""Typed experiment specification (Pydantic v2).

Design rule: never invent a parameter. Anything required for a physically meaningful
experiment is a required field; the few documented defaults are recorded in docs/DECISIONS.md
and are echoed into the plan so they are visible, not hidden.
"""
from __future__ import annotations

import math
from enum import Enum

from pydantic import BaseModel, ConfigDict, Field, model_validator


class DeviceType(str, Enum):
    NMOS = "nmos"
    PMOS = "pmos"


class AnalysisType(str, Enum):
    IDVG = "idvg"  # transfer characteristic: sweep VGS at fixed VDS
    IDVD = "idvd"  # output characteristic: sweep VDS at fixed VGS


class Measurement(str, Enum):
    ID = "ID"
    GM = "GM"
    GDS = "GDS"
    VTH = "VTH"
    SS = "SS"
    ION = "ION"
    IOFF = "IOFF"


_NEEDS_IDVG = {Measurement.GM, Measurement.VTH, Measurement.SS, Measurement.ION, Measurement.IOFF}
_NEEDS_IDVD = {Measurement.GDS}


class Sweep(BaseModel):
    """Ascending voltage sweep. Exactly one of `step` / `points` must be given."""

    model_config = ConfigDict(extra="forbid")

    start: float
    stop: float
    step: float | None = Field(default=None, gt=0)
    points: int | None = Field(default=None, ge=2)

    @model_validator(mode="after")
    def _check(self) -> "Sweep":
        if (self.step is None) == (self.points is None):
            raise ValueError("give exactly one of `step` or `points`")
        if not self.stop > self.start:
            raise ValueError("`stop` must be greater than `start` (ascending sweeps only)")
        if self.step is not None:
            ratio = (self.stop - self.start) / self.step
            if abs(ratio - round(ratio)) > 1e-6:
                raise ValueError(
                    f"step={self.step} does not evenly divide the range "
                    f"[{self.start}, {self.stop}]; refusing to silently truncate"
                )
        return self

    @property
    def n_points(self) -> int:
        if self.points is not None:
            return self.points
        assert self.step is not None
        return int(round((self.stop - self.start) / self.step)) + 1


class Budget(BaseModel):
    """Hard limits. `max_points` is mandatory; the others have documented defaults."""

    model_config = ConfigDict(extra="forbid")

    max_points: int = Field(gt=0)
    max_runtime_s: float = Field(default=300.0, gt=0)
    max_tool_calls: int = Field(default=20, gt=0)
    max_retries: int = Field(default=2, ge=0)


class ExperimentSpec(BaseModel):
    model_config = ConfigDict(extra="forbid")

    device_type: DeviceType
    model_name: str = Field(min_length=1)
    width_um: float = Field(gt=0)
    length_um: float = Field(gt=0)
    temperature_c: float
    analysis: AnalysisType
    sweep: Sweep
    vds_v: float | None = None  # fixed drain bias (Id-Vg)
    vgs_v: float | None = None  # fixed gate bias (Id-Vd)
    vbs_v: float = 0.0  # documented default: bulk tied to source
    measurements: list[Measurement] = Field(min_length=1)
    ion_vgs_v: float | None = None
    ioff_vgs_v: float | None = None
    vth_ic_a: float = Field(default=1e-7, gt=0)  # constant-current VTH criterion at W/L = 1
    budget: Budget
    output_format: str = "csv"

    @model_validator(mode="after")
    def _consistency(self) -> "ExperimentSpec":
        ms = set(self.measurements)
        if len(ms) != len(self.measurements):
            raise ValueError("duplicate entries in `measurements`")

        if self.analysis is AnalysisType.IDVG:
            if self.vds_v is None:
                raise ValueError("Id-Vg requires fixed `vds_v`")
            if self.vgs_v is not None:
                raise ValueError("Id-Vg sweeps VGS; `vgs_v` must not be set")
        else:
            if self.vgs_v is None:
                raise ValueError("Id-Vd requires fixed `vgs_v`")
            if self.vds_v is not None:
                raise ValueError("Id-Vd sweeps VDS; `vds_v` must not be set")

        bad = (ms & _NEEDS_IDVG) if self.analysis is AnalysisType.IDVD else (ms & _NEEDS_IDVD)
        if bad:
            raise ValueError(
                f"measurement(s) {sorted(m.value for m in bad)} cannot be extracted from a "
                f"{self.analysis.value} sweep"
            )

        if Measurement.ION in ms and self.ion_vgs_v is None:
            raise ValueError("ION requested but `ion_vgs_v` (explicit on-state bias) not given")
        if Measurement.IOFF in ms and self.ioff_vgs_v is None:
            raise ValueError("IOFF requested but `ioff_vgs_v` (explicit off-state bias) not given")
        if Measurement.ION not in ms and self.ion_vgs_v is not None:
            raise ValueError("`ion_vgs_v` given but ION not requested")
        if Measurement.IOFF not in ms and self.ioff_vgs_v is not None:
            raise ValueError("`ioff_vgs_v` given but IOFF not requested")

        if self.analysis is AnalysisType.IDVG:
            for name, v in (("ion_vgs_v", self.ion_vgs_v), ("ioff_vgs_v", self.ioff_vgs_v)):
                if v is not None and not (self.sweep.start <= v <= self.sweep.stop):
                    raise ValueError(f"`{name}`={v} lies outside the sweep [{self.sweep.start}, {self.sweep.stop}]")
            if self.ion_vgs_v is not None and self.ioff_vgs_v is not None and not self.ion_vgs_v > self.ioff_vgs_v:
                raise ValueError("`ion_vgs_v` must be greater than `ioff_vgs_v`")

        if not math.isfinite(self.temperature_c):
            raise ValueError("`temperature_c` must be finite")
        return self
