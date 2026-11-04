"""Deterministic rule-based "provider": the no-LLM floor of the benchmark and the test fixture for the pipeline.

It is NOT a model. It pattern-matches canonical phrasings and emits the same flat JSON a real provider must emit
(null for anything not stated). Its limits are the point: it shows what the validation layer does with a literal parser,
and gives the LLM rows something to beat on free-form phrasing.
"""
from __future__ import annotations

import json
import re
import time

from tinyspice.agent.raw import RAW_FIELDS
from tinyspice.providers.base import LLMResponse

_UNIT = {"nm": 1e-3, "um": 1.0, "µm": 1.0, "μm": 1.0}
_NUM = r"(-?\d+(?:\.\d+)?(?:e-?\d+)?)"


def _len_um(m: re.Match) -> float:
    return round(float(m.group(1)) * _UNIT[m.group(2).lower()], 9)


def parse_request(text: str) -> dict:
    t = " ".join(text.replace("\u2212", "-").split())
    low = t.lower()
    out: dict = {k: None for k in RAW_FIELDS}

    if re.search(r"\bnmos\b|\bnfet\b", low):
        out["device_type"] = "nmos"
    elif re.search(r"\bpmos\b|\bpfet\b", low):
        out["device_type"] = "pmos"
    if "sky130" in low:
        out["model_name"] = "sky130_fd_pr__nfet_01v8"
    elif re.search(r"level[- ]?1|builtin", low):
        out["model_name"] = "builtin_level1_nmos"

    unit = r"(nm|um|µm|μm)\b"
    for key, pats in (("width_um", [rf"\bwidth\b[^0-9\n]{{0,25}}{_NUM}\s*{unit}", rf"\bw\s*=\s*{_NUM}\s*{unit}"]),
                      ("length_um", [rf"\b(?:channel )?length\b[^0-9\n]{{0,25}}{_NUM}\s*{unit}", rf"\bl\s*=\s*{_NUM}\s*{unit}"])):
        for p in pats:
            m = re.search(p, low)
            if m:
                out[key] = _len_um(m)
                break

    if "room temperature" in low:
        out["temperature_c"] = 27.0
    else:
        m = re.search(rf"{_NUM}\s*(?:°\s?c|deg(?:rees)?\s*c(?:elsius)?|celsius)", low)
        if m:
            out["temperature_c"] = float(m.group(1))

    a_vg = re.search(r"id\s*-?\s*vg|transfer (?:curve|characteristic)", low)
    a_vd = re.search(r"id\s*-?\s*vd|output (?:curve|characteristic)", low)
    if a_vg and not a_vd:
        out["analysis"] = "idvg"
    elif a_vd and not a_vg:
        out["analysis"] = "idvd"
    elif a_vg and a_vd:
        out["analysis"] = "idvg" if a_vg.start() < a_vd.start() else "idvd"

    budget = re.search(r"(?:max(?:imum)?|at most|up to|budget of|limit(?:ed)? to)\s*(?:of\s*)?(\d+)\s*(?:simulation\s*)?points", low)
    work = low
    if budget:
        out["max_points"] = int(budget.group(1))
        work = low[:budget.start()] + " " + low[budget.end():]

    m = re.search(rf"(?:from|between)\s*{_NUM}\s*v?\s*(?:to|and|-)\s*{_NUM}\s*v", work)
    if m:
        out["sweep_start"], out["sweep_stop"] = float(m.group(1)), float(m.group(2))
    m = re.search(rf"step(?:s)?(?: size)?\s*(?:of|=)?\s*{_NUM}\s*(mv|v)\b", work) or re.search(rf"{_NUM}\s*(mv|v)\s*steps?\b", work)
    if m:
        out["sweep_step"] = float(m.group(1)) * (1e-3 if m.group(2) == "mv" else 1.0)
    m = re.search(r"(\d+)\s*(?:sweep\s*)?points", work)
    if m and out["sweep_step"] is None:
        out["sweep_points"] = int(m.group(1))

    for key, name in (("vds_v", "vds"), ("vgs_v", "vgs"), ("vbs_v", "vbs")):
        m = re.search(rf"\b{name}\s*(?:is\s*)?(?:fixed\s*)?(?:at|=|of|to)\s*{_NUM}\s*v", work)
        if m:
            out[key] = float(m.group(1))
    m = re.search(rf"(?:on-?current|\bion\b)\s*(?:at|@|evaluated at)\s*(?:vgs\s*=?\s*)?{_NUM}\s*v", low)
    if m:
        out["ion_vgs_v"] = float(m.group(1))
    m = re.search(rf"(?:off-?current|\bioff\b)\s*(?:at|@|evaluated at)\s*(?:vgs\s*=?\s*)?{_NUM}\s*v", low)
    if m:
        out["ioff_vgs_v"] = float(m.group(1))
    m = re.search(r"(?:time(?:out)?|runtime)\s*(?:limit\s*)?(?:of|=)\s*(\d+(?:\.\d+)?)\s*(?:s|sec)", low)
    if m:
        out["max_runtime_s"] = float(m.group(1))

    meas = []
    for code, pat in (("ID", r"\bdrain current\b(?!\s*(?:at|@))(?<!on-current)(?<!off-current)"), ("GM", r"transconductance|\bgm\b"),
                      ("GDS", r"output conductance|\bgds\b"), ("VTH", r"threshold voltage|\bvth\b"),
                      ("SS", r"subthreshold swing|\bss\b"), ("ION", r"on-?current|\bion\b"),
                      ("IOFF", r"off-?current|leakage current|\bioff\b")):
        if re.search(pat, low):
            meas.append(code)
    out["measurements"] = meas or None
    return out


class RuleBasedProvider:
    name = "rules"

    def complete_json(self, system: str, user: str, schema: dict, max_tokens: int = 700, seed: int = 0) -> LLMResponse:
        t0 = time.monotonic()
        m = re.search(r"REQUEST:\n(.*?)\n\nReturn the JSON", user, re.S)
        req = m.group(1) if m else user
        return LLMResponse(text=json.dumps(parse_request(req)), model="rules-v1", latency_s=time.monotonic() - t0,
                           prompt_tokens=0, completion_tokens=0)


class ScriptedProvider:
    """Test double: returns canned texts in order (to exercise malformed-JSON / repair / invention paths)."""
    name = "scripted"

    def __init__(self, *texts: str):
        self.texts, self.calls, self.users = list(texts), 0, []

    def complete_json(self, system: str, user: str, schema: dict, max_tokens: int = 700, seed: int = 0) -> LLMResponse:
        self.users.append(user)
        text = self.texts[min(self.calls, len(self.texts) - 1)]
        self.calls += 1
        return LLMResponse(text=text, model="scripted", latency_s=0.0)
