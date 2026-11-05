import json

from tinyspice.agent import interpret_request
from tinyspice.agent.interpret import stray_fields
from tinyspice.agent.raw import RAW_FIELDS
from tinyspice.providers import ScriptedProvider

REQ = ("NMOS SKY130 NFET, W = 2 um, L = 0.5 um, 27 C. Id-Vg with VDS = 1.8 V, VGS from 0 to 1.8 V in 0.05 V steps. "
       "Measure the threshold voltage. At most 50 points.")
GOOD = {k: None for k in RAW_FIELDS} | dict(device_type="nmos", model_name="sky130_fd_pr__nfet_01v8", width_um=2.0, length_um=0.5, temperature_c=27.0,
                                            analysis="idvg", sweep_start=0.0, sweep_stop=1.8, sweep_step=0.05, vds_v=1.8, measurements=["VTH"], max_points=50)
STRAY = GOOD | {"vgs_v": 1.8}                    # a number copied from the request into an inapplicable field
J = json.dumps


def test_detector_flags_only_inapplicable_fields():
    assert stray_fields(GOOD) == []
    assert [f for f, _ in stray_fields(STRAY)] == ["vgs_v"]
    assert [f for f, _ in stray_fields(GOOD | {"ion_vgs_v": 1.8})] == ["ion_vgs_v"]
    assert [f for f, _ in stray_fields(GOOD | {"analysis": "idvd", "vgs_v": 1.0, "vds_v": 1.8})] == ["vds_v"]
    assert stray_fields(GOOD | {"width_um": None}) == []          # a MISSING value is never a stray


def test_default_mode_rejects_the_stray_field_as_before():
    r = interpret_request(REQ, ScriptedProvider(J(STRAY)))
    assert not r.ok and r.llm_calls == 1 and not r.reasked


def test_prune_drops_and_logs_the_stray_field_without_a_second_call():
    r = interpret_request(REQ, ScriptedProvider(J(STRAY)), stray="prune")
    assert r.ok and r.llm_calls == 1 and r.pruned == ["stray:vgs_v"] and r.spec.vgs_v is None


def test_reask_calls_the_model_once_and_the_new_output_goes_through_every_check():
    seen = []
    inner = ScriptedProvider(J(STRAY), J(GOOD))

    class Spy:
        name = "spy"

        def complete_json(self, system, user, schema, **kw):
            seen.append(user)
            return inner.complete_json(system, user, schema, **kw)

    r = interpret_request(REQ, Spy(), stray="reask")
    assert r.ok and r.llm_calls == 2 and r.reasked
    assert "`vgs_v` must be null" in seen[1] and "`vgs_v` must be null" not in seen[0]


def test_reask_happens_at_most_once_and_a_second_stray_is_rejected():
    r = interpret_request(REQ, ScriptedProvider(J(STRAY), J(STRAY), J(GOOD)), stray="reask")
    assert not r.ok and r.llm_calls == 2


def test_reask_cannot_launder_an_invented_value():
    invented = GOOD | {"width_um": 7.0}                           # second answer invents a width the request never states
    r = interpret_request(REQ, ScriptedProvider(J(STRAY), J(invented)), stray="reask")
    assert not r.ok and r.errors[0]["type"] == "ungrounded_value"


def test_prune_cannot_hide_a_stated_contradiction():
    req = ("NMOS SKY130 NFET, W = 1 um, L = 0.18 um, 27 C. Id-Vg with VDS = 1.8 V and VGS held at 0.9 V while VGS is swept 0 to 1.8 V in 0.05 V steps. "
           "Measure the threshold voltage. At most 50 points.")
    raw = GOOD | {"width_um": 1.0, "length_um": 0.18, "vgs_v": 0.9}
    for mode in ("prune", "reask"):
        r = interpret_request(req, ScriptedProvider(J(raw), J(GOOD | {"width_um": 1.0, "length_um": 0.18})), stray=mode)
        assert not r.ok, mode                                      # the omitted-bias / conflict guards still fire after the field is removed
