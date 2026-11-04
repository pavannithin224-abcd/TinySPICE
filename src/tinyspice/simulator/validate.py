"""Output validation and ngspice error classification. A SimResult is only `ok` if validation passes."""
from __future__ import annotations

import re

import numpy as np

_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("MISSING_INCLUDE", re.compile(r"could not find include file", re.I)),
    ("MODEL_NOT_FOUND", re.compile(r"unknown subckt|unknown model|could not find a valid modelname|no such model", re.I)),
    ("NONCONVERGENCE", re.compile(r"singular matrix|no convergence|timestep too small|iteration limit|gmin stepping failed|source stepping failed", re.I)),
    ("NETLIST_SYNTAX", re.compile(r"syntax error|unknown (?:parameter|command)|unrecognized", re.I)),
]
_ERR_LINE = re.compile(r"^\s*(?:error|fatal)\b", re.I | re.M)


def classify_ngspice_error(text: str) -> str | None:
    """Return a recognised failure code, or None if the text shows no recognised fault."""
    for code, pat in _PATTERNS:
        if pat.search(text):
            return code
    return None


def has_error_lines(text: str) -> bool:
    return bool(_ERR_LINE.search(text))


def validate_points(x, y, points, atol: float = 1e-7) -> tuple[bool, str | None, str | None]:
    """Like validate_output, but for an explicit (possibly non-uniform) list of requested sweep points."""
    try:
        xa, ya = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
        pa = np.asarray(points, dtype=float)
    except (TypeError, ValueError) as e:
        return False, "PARSE_ERROR", str(e)
    if xa.ndim != 1 or ya.ndim != 1 or xa.shape != ya.shape:
        return False, "PARSE_ERROR", f"bad shapes x{xa.shape} y{ya.shape}"
    if len(xa) != len(pa):
        return False, "ROW_COUNT_MISMATCH", f"got {len(xa)} rows, plan expected {len(pa)}"
    if not (np.isfinite(xa).all() and np.isfinite(ya).all()):
        return False, "NONFINITE_VALUES", "NaN/Inf in simulator output"
    if len(xa) > 1 and not (np.diff(xa) > 0).all():
        return False, "NON_MONOTONIC_SWEEP", "sweep axis is not strictly increasing"
    if np.max(np.abs(xa - pa)) > atol:
        return False, "SWEEP_POINTS_MISMATCH", f"simulated axis differs from requested points by {np.max(np.abs(xa - pa)):.3g} V"
    return True, None, None


def validate_output(x, y, expected_points: int, start: float, stop: float,
                    endpoint_tol: float = 1e-6) -> tuple[bool, str | None, str | None]:
    """Return (ok, error_code, detail)."""
    try:
        xa, ya = np.asarray(x, dtype=float), np.asarray(y, dtype=float)
    except (TypeError, ValueError) as e:
        return False, "PARSE_ERROR", str(e)
    if xa.ndim != 1 or ya.ndim != 1 or xa.shape != ya.shape:
        return False, "PARSE_ERROR", f"bad shapes x{xa.shape} y{ya.shape}"
    if len(xa) != expected_points:
        return False, "ROW_COUNT_MISMATCH", f"got {len(xa)} rows, plan expected {expected_points}"
    if not (np.isfinite(xa).all() and np.isfinite(ya).all()):
        return False, "NONFINITE_VALUES", "NaN/Inf in simulator output"
    if len(xa) > 1 and not (np.diff(xa) > 0).all():
        return False, "NON_MONOTONIC_SWEEP", "sweep axis is not strictly increasing"
    if abs(xa[0] - start) > endpoint_tol or abs(xa[-1] - stop) > endpoint_tol:
        return False, "SWEEP_ENDPOINT_MISMATCH", f"sweep [{xa[0]}, {xa[-1]}] != requested [{start}, {stop}]"
    return True, None, None
