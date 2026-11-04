import json
from pathlib import Path

import pytest

from tinyspice.agent import interpret_request
from tinyspice.agent.raw import RAW_FIELDS, raw_json_schema, raw_to_spec_dict
from tinyspice.benchmark import evaluate, load_tasks
from tinyspice.providers import RuleBasedProvider, ScriptedProvider
from tinyspice.schemas import ExperimentSpec, ExperimentStatus

DEV = Path(__file__).resolve().parents[1] / "benchmark" / "group1_dev.json"

GOOD_RAW = {k: None for k in RAW_FIELDS} | {
    "device_type": "nmos", "model_name": "sky130_fd_pr__nfet_01v8", "width_um": 1.0, "length_um": 0.18, "temperature_c": 27.0,
    "analysis": "idvg", "sweep_start": 0.0, "sweep_stop": 1.8, "sweep_step": 0.02, "vds_v": 1.8, "measurements": ["VTH"],
    "max_points": 200}


def j(**over):
    return json.dumps(GOOD_RAW | over)


def test_raw_schema_matches_spec_fields():
    spec_fields = set(ExperimentSpec.model_fields)
    mapped = set(raw_to_spec_dict({k: 1 for k in RAW_FIELDS}))
    assert mapped <= spec_fields | set()                       # every raw key lands on a real ExperimentSpec field
    assert {"sweep", "budget"} <= mapped
    s = raw_json_schema()
    assert set(s["required"]) == set(RAW_FIELDS) and s["additionalProperties"] is False


def test_raw_to_spec_dict_drops_nulls_and_nests():
    d = raw_to_spec_dict(GOOD_RAW)
    assert "vgs_v" not in d and d["sweep"] == {"start": 0.0, "stop": 1.8, "step": 0.02} and d["budget"] == {"max_points": 200}


def test_valid_extraction_yields_spec_no_repair():
    r = interpret_request("x", ScriptedProvider(j()))
    assert r.ok and r.status is None and r.llm_calls == 1 and not r.repaired and r.spec.width_um == 1.0


def test_missing_value_is_rejected_and_never_repaired():
    p = ScriptedProvider(j(width_um=None), j())                # a 2nd (valid) answer exists; it must NOT be requested
    r = interpret_request("x", p)
    assert not r.ok and r.status is ExperimentStatus.REJECTED_INVALID and p.calls == 1 and not r.repaired
    assert any("width_um" in e["loc"] for e in r.errors)


def test_contradiction_is_rejected_and_never_repaired():
    p = ScriptedProvider(j(vgs_v=0.9), j())
    r = interpret_request("x", p)
    assert not r.ok and p.calls == 1 and "must not be set" in json.dumps(r.errors)


def test_malformed_json_gets_exactly_one_repair():
    p = ScriptedProvider("{not json", j())
    r = interpret_request("x", p)
    assert r.ok and r.repaired and p.calls == 2 and "FORMAT reasons only" in p.users[1]


def test_malformed_twice_is_rejected_after_bounded_repair():
    p = ScriptedProvider("garbage", "still garbage", j())
    r = interpret_request("x", p)
    assert not r.ok and p.calls == 2 and r.errors[0]["type"] == "json_invalid"


def test_bad_enum_is_repairable_once():
    p = ScriptedProvider(j(analysis="transfer"), j())
    r = interpret_request("x", p)
    assert r.ok and r.repaired and p.calls == 2


def test_repair_prompt_forbids_invention():
    p = ScriptedProvider("{broken", j())
    interpret_request("x", p)
    assert "Do NOT add any value the request does not state" in p.users[1]


def test_all_null_is_rejected():
    r = interpret_request("x", ScriptedProvider(json.dumps({k: None for k in RAW_FIELDS})))
    assert not r.ok and r.llm_calls == 1


def test_provider_error_surfaces():
    class Dead:
        name = "dead"

        def complete_json(self, *a, **k):
            from tinyspice.providers import LLMResponse
            return LLMResponse(text="", model="dead", latency_s=0.0, error="ConnectionError: refused")
    r = interpret_request("x", Dead())
    assert not r.ok and r.errors[0]["type"] == "provider_error"


def test_non_object_json_rejected():
    r = interpret_request("x", ScriptedProvider("[1,2,3]", "[1]"))
    assert not r.ok and r.llm_calls == 2


# ---- rule-based floor on the DEV set ----
def test_rules_floor_on_dev_set():
    res = evaluate(RuleBasedProvider(), load_tasks(DEV))
    m = res["metrics"]
    bad = [(t["id"], t.get("diff"), t["errors"]) for t in res["tasks"]
           if (t["expect"] == "valid" and not t["exact"]) or (t["expect"] == "reject" and not t["rejected"])]
    assert not bad, bad
    assert m["exact_match_rate"] == 1.0 and m["correct_rejection"] == 1.0 and m["false_accept_rate"] == 0.0
    miss = [(t["id"], t["errors"]) for t in res["tasks"] if t["expect"] == "reject" and t["rejected"] and not t["reason_match"]]
    assert m["reason_match_rate"] == 1.0, miss
    assert m["mean_llm_calls"] == 1.0
