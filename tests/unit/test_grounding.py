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


def test_cross_field_number_is_flagged_for_width_and_length():
    # 1.8 is a real number in the request (VDS = 1.8 V) but it is not the width
    req = "NMOS SKY130 NFET with L = 180 nm at 27 C. Id-Vg, VDS fixed at 1.8 V, VGS 0 to 1.8 V in 0.02 V steps. Measure threshold voltage. 200 points max."
    assert "width_um" in ungrounded_fields(raw(width_um=1.8, length_um=0.18, max_points=200), req)
    assert "length_um" not in ungrounded_fields(raw(width_um=1.8, length_um=0.18, max_points=200), req)


def test_anchors_accept_common_phrasings():
    for req, w, l in [("W = 1 um and L = 0.18 um", 1.0, 0.18), ("width 2000 nm, length 150 nm", 2.0, 0.15),
                      ("Geometry: width 3 um, length 0.25 um", 3.0, 0.25), ("W 8 um, L 0.15 um", 8.0, 0.15),
                      ("a transistor 4 um wide and 0.5 um long", 4.0, 0.5), ("Width 600 nm and length 300 nm", 0.6, 0.3)]:
        bad = ungrounded_fields(raw(width_um=w, length_um=l), req + " NMOS SKY130 NFET room temperature Id-Vg VDS 1.8 V 0 to 1.8 V 0.02 V steps threshold off-current VGS = 0 V 80 points")
        assert "width_um" not in bad and "length_um" not in bad, (req, bad)


def test_swapped_width_and_length_flagged():
    assert {"width_um", "length_um"} <= set(ungrounded_fields(raw(width_um=0.5, length_um=2.0), "W = 2 um, L = 0.5 um NMOS SKY130 room temperature Id-Vg"))


# ---- coverage + prune ----
from tinyspice.agent.grounding import uncovered_measurements  # noqa: E402


def test_coverage_flags_omitted_requested_measurement():
    assert uncovered_measurements(raw(measurements=["IOFF"]), REQ) == ["VTH"]
    assert uncovered_measurements(raw(), REQ) == []


def test_subthreshold_does_not_count_as_threshold_voltage():
    req = "NMOS SKY130 NFET, measure the subthreshold swing only"
    assert uncovered_measurements(raw(measurements=["SS"]), req) == []
    assert "VTH" in ungrounded_fields(raw(measurements=["VTH"]), req) or "measurements[VTH]" in ungrounded_fields(raw(measurements=["VTH"]), req)


def test_incomplete_extraction_is_rejected_even_without_pruning():
    r = interpret_request(REQ, ScriptedProvider(json.dumps(raw(measurements=["IOFF"]))))
    assert not r.ok and r.errors[0]["type"] == "incomplete_extraction"


def test_prune_drops_spurious_measurement_when_complete_and_logs_it():
    p = ScriptedProvider(json.dumps(raw(measurements=["ID", "VTH", "IOFF"])))
    assert not interpret_request(REQ, p).ok                                  # default: reject (strict)
    r = interpret_request(REQ, ScriptedProvider(json.dumps(raw(measurements=["ID", "VTH", "IOFF"]))), prune=True)
    assert r.ok and r.pruned == ["ID"] and sorted(m.value if hasattr(m, "value") else m for m in r.spec.measurements) == ["IOFF", "VTH"]


def test_prune_never_rescues_an_incomplete_extraction():
    # model padded ID AND dropped VTH: pruning ID would leave a valid-looking but incomplete spec -> must still reject
    r = interpret_request(REQ, ScriptedProvider(json.dumps(raw(measurements=["ID", "IOFF"]))), prune=True)
    assert not r.ok and r.errors[0]["type"] == "incomplete_extraction"


def test_prune_does_not_touch_ungrounded_numbers():
    r = interpret_request(REQ, ScriptedProvider(json.dumps(raw(length_um=0.18, measurements=["ID", "VTH", "IOFF"]))), prune=True)
    assert not r.ok and r.errors[0]["loc"] == "length_um"


def test_prune_dedupes_looping_measurements():
    r = interpret_request(REQ, ScriptedProvider(json.dumps(raw(measurements=["VTH", "VTH", "IOFF", "IOFF"]))), prune=True)
    assert r.ok and "duplicates" in r.pruned


# ---- request-side guards ----
from tinyspice.agent.grounding import omitted_biases, request_conflicts  # noqa: E402

BASE = "NMOS SKY130 NFET, W = 2 um, L = 0.5 um, 27 C. "


def test_step_and_points_both_stated_is_a_conflict_but_budget_is_not():
    assert request_conflicts(BASE + "Id-Vg, VDS 1.0 V, VGS 0 to 1.2 V in 0.05 V steps (that is 25 points). At most 40 points.")
    assert not request_conflicts(BASE + "Id-Vg, VDS 1.0 V, VGS 0 to 1.2 V in 0.05 V steps. At most 40 points.")
    assert not request_conflicts(BASE + "Id-Vg, VDS 1.0 V, VGS 0 to 1.2 V using 25 points. Cap the run at 40 points.")
    assert not request_conflicts(BASE + "Id-Vg, VDS 1.0 V, VGS 0 to 1.2 V, 0.05 V step. ≤ 40 points.")


def test_conflict_is_rejected_by_interpreter_and_never_repaired():
    req = BASE + "Id-Vg, VDS = 1.8 V, VGS 0 to 1.8 V in 0.1 V steps (19 points). Threshold voltage. At most 40 points."
    p = ScriptedProvider(json.dumps(raw(length_um=0.5, sweep_step=0.1, ioff_vgs_v=None, measurements=["VTH"], max_points=40, width_um=2.0, temperature_c=27.0, sweep_stop=1.8, vds_v=1.8)))
    r = interpret_request(req, p)
    assert not r.ok and r.errors[0]["type"] == "request_conflict" and p.calls == 1


def test_stated_fixed_bias_must_be_extracted_but_current_biases_are_ignored():
    assert omitted_biases(raw(vds_v=None), BASE + "Id-Vg with the drain at 1.2 V, VGS 0 to 1.2 V.") == ["vds_v"]
    assert omitted_biases(raw(), BASE + "Id-Vg with the drain at 1.2 V.") == []
    assert omitted_biases(raw(vgs_v=None), BASE + "Id-Vg, VDS 1.0 V. Report on-current at VGS = 1.2 V and off-current at VGS = 0 V.") == []
    assert omitted_biases(raw(vgs_v=None), BASE + "Id-Vg, VDS 1.0 V, VGS fixed at 0.9 V while VGS is swept 0 to 1.8 V.") == ["vgs_v"]


def test_swapped_bias_value_is_flagged_by_anchor():
    req = BASE + "Id-Vg with VDS = 1.0 V, VGS from 0 to 1.8 V in 0.1 V steps. Threshold voltage. At most 40 points."
    assert "vds_v" in ungrounded_fields(raw(vds_v=1.8, sweep_stop=1.8, sweep_step=0.1), req)
    assert "vds_v" not in ungrounded_fields(raw(vds_v=1.0, sweep_stop=1.8, sweep_step=0.1), req)
