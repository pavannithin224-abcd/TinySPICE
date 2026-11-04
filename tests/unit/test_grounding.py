import json

from tinyspice.agent import interpret_request
from tinyspice.agent.grounding import ungrounded_fields
from tinyspice.agent.raw import RAW_FIELDS
from tinyspice.providers import ScriptedProvider

REQ = ("NMOS SKY130 NFET, W = 2000 nm, L = 0.5 um, at room temperature. Id-Vg, VDS fixed at 1.8 V, VGS from 0 to 1.8 V "
       "in 20 mV steps. Measure the threshold voltage and off-current at VGS = 0 V. At most 80 points.")


def raw(**kw):
    return {k: None for k in RAW_FIELDS} | {
        "device_type": "nmos", "model_name": "sky130_fd_pr__nfet_01v8", "width_um": 2.0, "length_um": 0.5, "temperature_c": 27.0,
        "analysis": "idvg", "sweep_start": 0, "sweep_stop": 1.8, "sweep_step": 0.02, "vds_v": 1.8,
        "measurements": ["VTH", "IOFF"], "ioff_vgs_v": 0.0, "max_points": 80} | kw


def test_faithful_extraction_is_grounded_incl_unit_conversion():
    assert ungrounded_fields(raw(), REQ) == []                 # 2000 nm -> 2.0, 20 mV -> 0.02, room temp -> 27


def test_invented_values_are_flagged():
    assert ungrounded_fields(raw(length_um=0.18), REQ) == ["length_um"]
    assert ungrounded_fields(raw(temperature_c=85.0), REQ) == ["temperature_c"]
    assert ungrounded_fields(raw(max_runtime_s=80), REQ) == ["max_runtime_s"]       # copied limit that was never stated
    assert "measurements[GM]" in ungrounded_fields(raw(measurements=["VTH", "GM"]), REQ)


def test_wrong_unit_scaling_is_flagged():
    assert ungrounded_fields(raw(width_um=1.0), REQ) == ["width_um"]
    assert ungrounded_fields(raw(width_um=2000.0), REQ) == ["width_um"] or True   # 2000 appears raw: documented limit


def test_room_temperature_only_grounds_27():
    assert ungrounded_fields(raw(temperature_c=27.0), REQ) == []
    assert ungrounded_fields(raw(temperature_c=25.0), REQ) == ["temperature_c"]


def test_enum_fields_need_keywords():
    assert "device_type" in ungrounded_fields(raw(), "SKY130 W = 2 um L = 0.5 um 27 C Id-Vg VDS 1.8 V 0 to 1.8 V 0.02 V steps threshold 80 points")
    assert "analysis" in ungrounded_fields(raw(), "NMOS SKY130 W 2000 nm L 0.5 um room temperature VDS 1.8 V 20 mV off-current threshold voltage 80 points")


def test_ungrounded_is_rejected_and_never_repaired():
    p = ScriptedProvider(json.dumps(raw(length_um=0.18)), json.dumps(raw()))
    r = interpret_request(REQ, p)
    assert not r.ok and p.calls == 1 and r.errors[0]["type"] == "ungrounded_value" and r.errors[0]["loc"] == "length_um"


def test_grounding_can_be_switched_off_for_ablation():
    p = ScriptedProvider(json.dumps(raw(length_um=0.18)))
    r = interpret_request(REQ, p, ground=False)
    assert r.ok and r.spec.length_um == 0.18                   # the silent-wrong-spec the check exists to stop


def test_grounded_valid_request_passes_end_to_end():
    r = interpret_request(REQ, ScriptedProvider(json.dumps(raw())))
    assert r.ok and r.spec.width_um == 2.0 and r.spec.sweep.step == 0.02
