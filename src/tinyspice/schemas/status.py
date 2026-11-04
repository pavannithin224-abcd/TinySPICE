from enum import Enum


class ExperimentStatus(str, Enum):
    """Mutually exclusive terminal states. A run is SUCCESSFUL only with validated
    simulator output AND successful measurement extraction."""

    SUCCESSFUL = "successful"
    FAILED = "failed"
    PARTIAL = "partially_completed"
    RECOVERED = "recovered_after_failure"
    REJECTED_INVALID = "rejected_invalid_input"
    STOPPED_BUDGET = "stopped_budget_limit"
