"""Flat extraction schema the LLM fills, and the conversion into a (strictly validated) ExperimentSpec dict.

Flat + every key required-but-nullable: the model must make an explicit stated/not-stated decision per field,
small models handle flat objects far better than nested ones, and grammar-constrained decoding stays simple.
Anything the user did not state must be null; null is DROPPED before validation, so required fields stay missing
and the spec is REJECTED instead of silently invented.
"""
from __future__ import annotations

NUM, STR = ["number", "null"], ["string", "null"]

RAW_FIELDS: dict[str, dict] = {
    "device_type": {"enum": ["nmos", "pmos", None]},
    "model_name": {"type": STR},
    "width_um": {"type": NUM},
    "length_um": {"type": NUM},
    "temperature_c": {"type": NUM},
    "analysis": {"enum": ["idvg", "idvd", None]},
    "sweep_start": {"type": NUM},
    "sweep_stop": {"type": NUM},
    "sweep_step": {"type": NUM},
    "sweep_points": {"type": ["integer", "null"]},
    "vds_v": {"type": NUM},
    "vgs_v": {"type": NUM},
    "vbs_v": {"type": NUM},
    "measurements": {"type": ["array", "null"], "items": {"enum": ["ID", "GM", "GDS", "VTH", "SS", "ION", "IOFF"]}, "maxItems": 7},
    "ion_vgs_v": {"type": NUM},
    "ioff_vgs_v": {"type": NUM},
    "vth_ic_a": {"type": NUM},
    "max_points": {"type": ["integer", "null"]},
    "max_runtime_s": {"type": NUM},
    "max_tool_calls": {"type": ["integer", "null"]},
    "max_retries": {"type": ["integer", "null"]},
}


def raw_json_schema() -> dict:
    """Step XOR points is enforced by the grammar itself: three full-object variants (step only / points only / neither).
    'Both stated' cannot be expressed, so a request that states both is silently reduced to one; documented limitation."""
    def variant(step: dict, points: dict) -> dict:
        return {"type": "object", "properties": {**RAW_FIELDS, "sweep_step": step, "sweep_points": points},
                "required": list(RAW_FIELDS), "additionalProperties": False}
    return {"anyOf": [
        variant({"type": "number"}, {"type": "null"}),
        variant({"type": "null"}, {"type": "integer"}),
        variant({"type": "null"}, {"type": "null"}),
    ]}


_SWEEP = {"sweep_start": "start", "sweep_stop": "stop", "sweep_step": "step", "sweep_points": "points"}
_BUDGET = {"max_points": "max_points", "max_runtime_s": "max_runtime_s", "max_tool_calls": "max_tool_calls",
           "max_retries": "max_retries"}


def raw_to_spec_dict(raw: dict) -> dict:
    """Nulls are dropped (never defaulted). Unknown keys are kept so ExperimentSpec(extra=forbid) can reject them."""
    out: dict = {}
    sweep: dict = {}
    budget: dict = {}
    for k, v in raw.items():
        if v is None:
            continue
        if k in _SWEEP:
            sweep[_SWEEP[k]] = v
        elif k in _BUDGET:
            budget[_BUDGET[k]] = v
        else:
            out[k] = v
    if sweep:
        out["sweep"] = sweep
    if budget:
        out["budget"] = budget
    return out
