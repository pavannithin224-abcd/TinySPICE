"""Supported-operating-range registry. Limits live in configs/devices/*.json so they are data, not code."""
from __future__ import annotations

import json
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from tinyspice.schemas.spec import DeviceType


class DeviceLimits(BaseModel):
    model_config = ConfigDict(extra="forbid")

    model_name: str
    device_type: DeviceType
    w_min_um: float
    w_max_um: float
    l_min_um: float
    l_max_um: float
    v_min: float  # lowest permitted |bias| endpoint (signed, NMOS convention)
    v_max: float
    temp_min_c: float
    temp_max_c: float
    limits_verified: bool  # False until checked against the actual model-card bin table
    source_note: str


def load_device_limits(path: str | Path) -> DeviceLimits:
    return DeviceLimits.model_validate(json.loads(Path(path).read_text(encoding="utf-8")))
