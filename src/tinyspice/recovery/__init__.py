"""Recovery catalog: named fault -> (recoverable?, action). Anything not in the catalog is unrecognised and is NEVER recovered.

Solver ladder rule: only iteration limits and the integration method may change. gmin / abstol are NEVER touched: raising them
re-creates the Stage-1 IOFF artefact (a ~pA floor measured as leakage).
"""
from __future__ import annotations

from dataclasses import dataclass

SS_REFUSAL_CODES = {"WINDOW_TOO_NARROW", "INSUFFICIENT_POINTS"}   # fixable by sampling; other refusals (e.g. NOT_CROSSED) are not
ALLOWED_SOLVER_OPTIONS = {"itl1", "itl2", "itl4", "method"}
ALLOWED_METHODS = {"gear", "trap"}
SOLVER_LADDER: list[dict] = [
    {"itl1": 400, "itl2": 200, "itl4": 100},
    {"itl1": 400, "itl2": 200, "itl4": 100, "method": "gear"},
]


@dataclass(frozen=True)
class Rule:
    code: str
    recognised: bool
    recoverable: bool
    action: str


_CATALOG = {
    "MISSING_INCLUDE": Rule("MISSING_INCLUDE", True, False, "none: configuration fault"),
    "MODEL_NOT_FOUND": Rule("MODEL_NOT_FOUND", True, False, "none: configuration fault"),
    "NETLIST_SYNTAX": Rule("NETLIST_SYNTAX", True, False, "none: configuration fault"),
    "TIMEOUT": Rule("TIMEOUT", True, True, "retry_longer"),
    "ROW_COUNT_MISMATCH": Rule("ROW_COUNT_MISMATCH", True, True, "rerun"),
    "NO_OUTPUT": Rule("NO_OUTPUT", True, True, "rerun"),
    "NONFINITE_VALUES": Rule("NONFINITE_VALUES", True, True, "rerun"),
    "NONCONVERGENCE": Rule("NONCONVERGENCE", True, True, "solver_ladder"),
}


def classify(code: str | None) -> Rule:
    if code in _CATALOG:
        return _CATALOG[code]
    return Rule(code or "UNKNOWN", False, False, "none: unrecognised fault, never guessed")


def validate_solver_overrides(overrides: dict | None) -> dict:
    """Refuse anything that is not a whitelisted option with a sane value (in particular gmin/abstol)."""
    out = {}
    for k, v in (overrides or {}).items():
        if k not in ALLOWED_SOLVER_OPTIONS:
            raise ValueError(f"solver option {k!r} may not be changed by recovery (allowed: {sorted(ALLOWED_SOLVER_OPTIONS)})")
        if k == "method":
            if v not in ALLOWED_METHODS:
                raise ValueError(f"unknown integration method {v!r}")
        elif not (isinstance(v, int) and 1 <= v <= 100000):
            raise ValueError(f"{k} must be an int in [1, 100000], got {v!r}")
        out[k] = v
    return out


def solver_options_line(overrides: dict | None) -> str | None:
    ov = validate_solver_overrides(overrides)
    return (".options " + " ".join(f"{k}={v}" for k, v in sorted(ov.items()))) if ov else None
