"""Result type shared by all extractors. A failed extraction has value=None and an error code: never a guess."""
from __future__ import annotations

from dataclasses import asdict, dataclass, field


class MeasurementError(Exception):
    def __init__(self, code: str, detail: str):
        super().__init__(f"{code}: {detail}")
        self.code, self.detail = code, detail


@dataclass(frozen=True)
class MeasurementResult:
    name: str
    ok: bool
    value: float | None
    unit: str
    method: str
    conditions: dict = field(default_factory=dict)
    diagnostics: dict = field(default_factory=dict)
    error_code: str | None = None
    error_detail: str | None = None
    series: dict | None = None  # only for curve-valued measurements (ID)

    def to_dict(self) -> dict:
        return asdict(self)
