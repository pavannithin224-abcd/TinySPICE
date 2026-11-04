"""Natural-language request -> validated ExperimentSpec.

The LLM only extracts; pydantic decides. Hard rules:
- Not-stated => null => field missing => REJECT (never invent, never "repair" a missing value).
- Contradictions / unsupported combinations are rejected by ExperimentSpec's validators.
- At most `max_repairs` (default 1) repair call(s), and ONLY for malformed JSON or type/enum errors, never for
  missing or contradictory values (a repair prompt would only invite the model to make something up).
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field

from pydantic import ValidationError

from tinyspice.agent.grounding import uncovered_measurements, ungrounded_fields
from tinyspice.agent.raw import raw_json_schema, raw_to_spec_dict
from tinyspice.providers.base import LLMProvider
from tinyspice.schemas import ExperimentSpec, ExperimentStatus

KNOWN_MODELS = ["sky130_fd_pr__nfet_01v8", "builtin_level1_nmos"]

SYSTEM_PROMPT = f"""You extract a MOSFET characterization request into one JSON object. Output JSON only.

STRICT RULES
1. Use ONLY values the request states. Anything not stated MUST be null. Never guess, never fill defaults.
2. Convert units: nm -> um (180 nm = 0.18), mV -> V, K -> C only if stated in kelvin. Currents in A. Voltages in V.
3. "room temperature" = 27 (degrees C). Do not infer any other temperature.
4. analysis: "Id-Vg"/"transfer curve"/"sweep gate voltage" = "idvg"; "Id-Vd"/"output curve"/"sweep drain voltage" = "idvd".
5. measurements (only those requested): threshold voltage=VTH, transconductance=GM, output conductance=GDS,
   subthreshold swing=SS, on-current=ION, off-current=IOFF, drain current curve=ID.
6. model_name must be one of {KNOWN_MODELS} when the request clearly names that device ("SKY130 1.8 V NFET" -> sky130_fd_pr__nfet_01v8); otherwise null.
7. sweep_start/sweep_stop/sweep_step (or sweep_points) describe the swept voltage. vds_v is the FIXED drain bias for Id-Vg; vgs_v is the FIXED gate bias for Id-Vd.
8. ion_vgs_v / ioff_vgs_v: the gate voltage at which on-/off-current is evaluated, only if stated.
9. max_points: a stated limit on simulation points. max_runtime_s, max_tool_calls, max_retries: only if stated.
10. Ignore irrelevant text. If the request is contradictory, still copy what it states; do not fix it.
11. NEVER copy one number into several fields. max_points, max_runtime_s, max_tool_calls and max_retries are four different limits; each is null unless the request names THAT limit.
12. For Id-Vg only vds_v is a fixed bias; vgs_v is null unless the request fixes it. For Id-Vd only vgs_v is a fixed bias; vds_v is null. vbs_v is null unless stated. vth_ic_a is null unless a threshold current is stated.
13. A step ("in 0.02 V steps") fills sweep_step; a count ("with 37 points") fills sweep_points. Never fill both; if neither is stated, both are null.
14. Lengths: "W = 2000 nm" -> width_um 2.0 ; "L = 150 nm" -> length_um 0.15. Width and length are in micrometres.

EXAMPLE
REQUEST: Look at an NMOS with width 500 nm and length 2 um at 40 degrees C. Id-Vd, gate fixed at 0.7 V, drain from 0 to 1.5 V with 31 points. Measure the drain current. No more than 45 points.
JSON: {{"device_type": "nmos", "model_name": null, "width_um": 0.5, "length_um": 2.0, "temperature_c": 40, "analysis": "idvd", "sweep_start": 0, "sweep_stop": 1.5, "sweep_step": null, "sweep_points": 31, "vds_v": null, "vgs_v": 0.7, "vbs_v": null, "measurements": ["ID"], "ion_vgs_v": null, "ioff_vgs_v": null, "vth_ic_a": null, "max_points": 45, "max_runtime_s": null, "max_tool_calls": null, "max_retries": null}}"""


def build_user_prompt(request: str, error_note: str | None = None) -> str:
    base = f"REQUEST:\n{request.strip()}\n\nReturn the JSON object now."
    if error_note:
        base += (f"\n\nYour previous output was rejected for FORMAT reasons only: {error_note}\n"
                 "Fix the format. Do NOT add any value the request does not state; keep null for unstated fields.")
    return base


@dataclass
class InterpretResult:
    spec: ExperimentSpec | None
    status: ExperimentStatus | None  # None when a valid spec was produced; REJECTED_INVALID otherwise
    errors: list[dict] = field(default_factory=list)
    raw: dict | None = None
    llm_calls: int = 0
    repaired: bool = False
    latency_s: float = 0.0
    model: str = ""
    raw_text: str = ""
    pruned: list = field(default_factory=list)      # measurement codes dropped because the request never asked for them
    @property
    def ok(self) -> bool:
        return self.spec is not None


def _errors(e: ValidationError) -> list[dict]:
    return [{"type": x["type"], "loc": ".".join(str(p) for p in x["loc"]), "msg": x["msg"]} for x in e.errors()]


# error types a repair call may address; everything else (missing values, contradictions) is final
_REPAIRABLE = {"json_invalid", "extra_forbidden", "enum", "literal_error", "float_parsing", "int_parsing",
               "float_type", "int_type", "string_type", "list_type", "dict_type", "model_type", "greater_than",
               "greater_than_equal", "too_short"}


def interpret_request(request: str, provider: LLMProvider, max_repairs: int = 1, seed: int = 0, max_tokens: int = 450,
                      ground: bool = True, prune: bool = False) -> InterpretResult:
    schema = raw_json_schema()
    res = InterpretResult(spec=None, status=ExperimentStatus.REJECTED_INVALID, model=getattr(provider, "name", "?"))
    note: str | None = None
    t0 = time.monotonic()
    for attempt in range(max_repairs + 1):
        resp = provider.complete_json(SYSTEM_PROMPT, build_user_prompt(request, note), schema, max_tokens=max_tokens, seed=seed)
        res.llm_calls += 1
        res.raw_text, res.model = resp.text, resp.model
        if resp.error:
            res.errors = [{"type": "provider_error", "loc": "", "msg": resp.error}]
            break
        try:
            raw = json.loads(resp.text)
            if not isinstance(raw, dict):
                raise ValueError("top-level JSON is not an object")
        except ValueError as e:
            res.errors = [{"type": "json_invalid", "loc": "", "msg": str(e)}]
            note = "output was not a valid JSON object"
            if attempt < max_repairs:
                res.repaired = True
                continue
            break
        res.raw = raw
        if prune and isinstance(raw.get("measurements"), list):
            seen = list(dict.fromkeys(raw["measurements"]))      # order-preserving dedupe (tiny models loop)
            if len(seen) != len(raw["measurements"]):
                res.pruned.append("duplicates")
                raw = dict(raw, measurements=seen)
                res.raw = raw
        if ground:
            ug = ungrounded_fields(raw, request)
            soft = [f for f in ug if f.startswith("measurements[")]
            hard = [f for f in ug if f not in soft]
            if hard or (soft and not prune):
                res.errors = [{"type": "ungrounded_value", "loc": f, "msg": f"value of `{f}` is not stated in the request"} for f in ug]
                break                                   # final: never repaired
            if soft:                                    # spurious measurement codes: drop (and log), never invent
                drop = {f[len("measurements["):-1] for f in soft}
                kept = [m for m in (raw.get("measurements") or []) if m not in drop]
                res.pruned = sorted(set(res.pruned) | drop)
                raw = dict(raw, measurements=kept or None)
                res.raw = raw
            miss = uncovered_measurements(raw, request)
            if miss:                                    # named in the request but absent from the extraction => incomplete
                res.errors = [{"type": "incomplete_extraction", "loc": f"measurements[{c}]",
                               "msg": f"request names {c} but the extraction omits it"} for c in miss]
                break
        try:
            spec = ExperimentSpec.model_validate(raw_to_spec_dict(raw))
        except ValidationError as e:
            res.errors = _errors(e)
            repairable = all(x["type"] in _REPAIRABLE for x in res.errors)
            if repairable and attempt < max_repairs:
                note = "; ".join(f"{x['loc']}: {x['msg']}" for x in res.errors)[:400]
                res.repaired = True
                continue
            break
        res.spec, res.status, res.errors = spec, None, []
        break
    res.latency_s = time.monotonic() - t0
    return res
