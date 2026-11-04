"""Typed errors. Each carries a machine-readable code and the experiment status it maps to."""
from __future__ import annotations

from tinyspice.schemas.status import ExperimentStatus


class TinySPICEError(Exception):
    code: str = "TINYSPICE_ERROR"
    status: ExperimentStatus = ExperimentStatus.FAILED

    def __init__(self, message: str):
        super().__init__(message)
        self.message = message


class PlanRejected(TinySPICEError):
    """Deterministic pre-execution validation refused the experiment."""

    def __init__(self, code: str, message: str, status: ExperimentStatus):
        super().__init__(message)
        self.code = code
        self.status = status
