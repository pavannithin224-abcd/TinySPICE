"""Deterministic grounding check: every value the LLM extracted must be traceable to the request text.

No model involved. A numeric field is grounded if some number in the request, optionally scaled by an attached or
nearby unit (nm/um/mV/V/degC/s/...), equals it (rel 1e-6). Enumerated fields are grounded by keyword. 'room temperature'
grounds 27. Ungrounded => the spec is REJECTED with type 'ungrounded_value' (never repaired: a repair prompt would only
invite another guess).

Known limits (documented, not hidden): cross-field mix-ups (a real number placed in the wrong field) are NOT caught here;
the number 0 is grounded by any '0' in the text; a request with an unusual unit word may be falsely rejected (safe direction).
"""
from __future__ import annotations

import math
import re

_NUM = re.compile(r"(?<![\w.])(-?\d+(?:\.\d+)?(?:e-?\d+)?)\s*(nm|um|µm|μm|mv|v|k|°\s?c|c|s|ms|a|ua|µa|μa|na|pa)?\b", re.I)
_SCALE = {None: [1.0], "nm": [1e-3, 1.0], "um": [1.0], "µm": [1.0], "μm": [1.0], "mv": [1e-3], "v": [1.0], "k": [1.0],
          "°c": [1.0], "c": [1.0], "s": [1.0], "ms": [1e-3], "a": [1.0], "ua": [1e-6], "µa": [1e-6], "μa": [1e-6],
          "na": [1e-9], "pa": [1e-12]}

NUMERIC_FIELDS = ["width_um", "length_um", "temperature_c", "sweep_start", "sweep_stop", "sweep_step", "sweep_points",
                  "vds_v", "vgs_v", "vbs_v", "ion_vgs_v", "ioff_vgs_v", "vth_ic_a", "max_points", "max_runtime_s",
                  "max_tool_calls", "max_retries"]

_MEAS = {"ID": r"drain current|\bid\b(?!\s*-?\s*v)|current curve", "GM": r"transconductance|\bgm\b",
         "GDS": r"output conductance|\bgds\b", "VTH": r"(?<!sub)(?<!sub-)(?<!sub )threshold|\bvth\b|\bvt\b",
         "SS": r"subthreshold swing|\bss\b|sub-threshold swing", "ION": r"on-?\s?current|\bion\b|\bi_on\b",
         "IOFF": r"off-?\s?current|leakage|\bioff\b|\bi_off\b"}


_BUDGET_KW = {"max_points": r"point", "max_runtime_s": r"runtime|run time|timeout|time limit|\bseconds?\b|\d\s?s\b|\bsec\b",
              "max_tool_calls": r"tool call|tool-call|\bcalls?\b", "max_retries": r"retr(?:y|ies)|attempt"}


def _candidates(text: str) -> list[float]:
    t = text.replace("\u2212", "-")
    out: list[float] = []
    for m in _NUM.finditer(t):
        base = float(m.group(1))
        unit = (m.group(2) or "").lower().replace(" ", "") or None
        for s in _SCALE.get(unit, [1.0]):
            out.append(base * s)
        out.append(base)                                   # raw number is always allowed
    if re.search(r"room temp", t, re.I):
        out.append(27.0)
    return out


def _isin(v: float, cands: list[float]) -> bool:
    return any(math.isclose(v, c, rel_tol=1e-6, abs_tol=1e-12) for c in cands)


def _anchored(text: str, value: float, before: str, after: str) -> bool:
    """True if some number in `text` equals `value` (after unit scaling) AND sits next to its field's own anchor word."""
    t = text.replace("\u2212", "-")
    for m in _NUM.finditer(t):
        unit = (m.group(2) or "").lower().replace(" ", "") or None
        vals = [float(m.group(1)) * s for s in _SCALE.get(unit, [1.0])] + [float(m.group(1))]
        if not any(math.isclose(value, v, rel_tol=1e-6, abs_tol=1e-12) for v in vals):
            continue
        pre = t[max(0, m.start() - 40):m.start()].lower()
        post = t[m.end():m.end() + 14].lower()
        if re.search(before, pre) or re.search(after, post):
            return True
    return False


_ANCHORS = {"width_um": (r"(?:\bw\b|width)[^\d\n]{0,25}$", r"^\W*(?:wide|width)"),
            "length_um": (r"(?:\bl\b|length)[^\d\n]{0,25}$", r"^\W*(?:long|length)")}


def uncovered_measurements(raw: dict, request: str) -> list[str]:
    """Measurement codes the request names that the extraction omits (converse of grounding: catches incomplete specs)."""
    low = request.lower()
    have = set(raw.get("measurements") or [])
    return [c for c, pat in _MEAS.items() if c not in have and re.search(pat, low)]


def ungrounded_fields(raw: dict, request: str) -> list[str]:
    low = request.lower()
    cands = _candidates(request)
    bad: list[str] = []
    for k in NUMERIC_FIELDS:
        v = raw.get(k)
        if v is None or isinstance(v, bool):
            continue
        try:
            fv = float(v)
        except (TypeError, ValueError):
            bad.append(k)
            continue
        if not _isin(fv, cands):
            bad.append(k)
        elif k in _ANCHORS and not _anchored(request, fv, *_ANCHORS[k]):
            bad.append(k)                                   # real number, wrong field (e.g. VDS 1.8 V read as width)
    for k, kw in _BUDGET_KW.items():                       # a limit needs its own keyword, not just a matching number
        if raw.get(k) is not None and k not in bad and not re.search(kw, low):
            bad.append(k)
    for code in raw.get("measurements") or []:
        if code in _MEAS and not re.search(_MEAS[code], low):
            bad.append(f"measurements[{code}]")
    d = raw.get("device_type")
    if d == "nmos" and not re.search(r"\bnmos\b|\bnfet\b|n-?channel", low):
        bad.append("device_type")
    if d == "pmos" and not re.search(r"\bpmos\b|\bpfet\b|p-?channel", low):
        bad.append("device_type")
    a = raw.get("analysis")
    if a == "idvg" and not re.search(r"id\s*-?\s*vg|transfer|gate (?:voltage )?(?:sweep|ramp|swept)|sweep(?:ing)? (?:the )?gate|ramp the gate|gate from|gate swept|vgs\s*(?:from|0|sweep)|swept? vgs", low):
        bad.append("analysis")
    if a == "idvd" and not re.search(r"id\s*-?\s*vd|output|drain (?:voltage )?(?:sweep|ramp|swept)|sweep(?:ing)? (?:the )?drain|drain from|drain swept|vds\s*(?:from|0|sweep)|swept? vds", low):
        bad.append("analysis")
    mn = raw.get("model_name")
    if mn == "sky130_fd_pr__nfet_01v8" and "sky130" not in low:
        bad.append("model_name")
    if mn == "builtin_level1_nmos" and not re.search(r"level[- ]?1|builtin|built-in", low):
        bad.append("model_name")
    return bad
