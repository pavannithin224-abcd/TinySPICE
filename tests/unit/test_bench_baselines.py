import json

import pytest

from tinyspice.benchmark.baselines import lenient_spec, parse_first_json
from tinyspice.agent.raw import RAW_FIELDS


def R(**kw):
    return {k: None for k in RAW_FIELDS} | kw


def test_defaults_fill_every_unstated_value_silently():
    s = lenient_spec(R())
    assert (s.width_um, s.length_um, s.temperature_c) == (1.0, 0.18, 27.0)
    assert s.analysis.value == "idvg" and s.sweep.step == 0.02 and s.sweep.stop == 1.8 and s.vds_v == 1.8
    assert [m.value for m in s.measurements] == ["VTH"]


def test_fixed_bias_on_the_swept_variable_is_dropped_not_rejected():
    s = lenient_spec(R(analysis="idvg", sweep_start=0.0, sweep_stop=1.8, sweep_step=0.05, vds_v=1.8, vgs_v=0.9, measurements=["VTH"]))
    assert s is not None and s.vgs_v is None


def test_step_wins_over_points_and_nondividing_step_is_truncated():
    s = lenient_spec(R(sweep_start=0.0, sweep_stop=1.8, sweep_step=0.05, sweep_points=7))
    assert s.sweep.step == 0.05 and s.sweep.points is None
    t = lenient_spec(R(sweep_start=0.0, sweep_stop=1.8, sweep_step=0.07))
    assert t.sweep.stop == pytest.approx(1.75)                        # 25 x 0.07; the requested 1.8 V is silently lost


def test_measurements_the_analysis_cannot_provide_are_silently_dropped():
    s = lenient_spec(R(analysis="idvg", measurements=["GDS", "VTH"]))
    assert [m.value for m in s.measurements] == ["VTH"]
    assert [m.value for m in lenient_spec(R(analysis="idvg", measurements=["GDS"])).measurements] == ["VTH"]


def test_stated_budget_is_echoed_into_the_spec_but_the_point_count_is_not_limited_by_it():
    s = lenient_spec(R(sweep_start=0.0, sweep_stop=1.8, sweep_step=0.01, max_points=50, max_tool_calls=6, max_runtime_s=0.3))
    assert s.sweep.n_points == 181 and s.budget.max_points == 50 and s.budget.max_tool_calls == 6 and s.budget.max_runtime_s == 0.3


def test_an_unusable_stated_limit_is_dropped_not_fatal():
    s = lenient_spec(R(max_tool_calls=0))
    assert s is not None and s.budget.max_tool_calls == 20            # default, the bad echo was discarded


def test_ion_ioff_default_to_sweep_ends_and_unrequested_biases_are_ignored():
    s = lenient_spec(R(measurements=["ION", "IOFF"], sweep_start=0.0, sweep_stop=1.8, sweep_step=0.05))
    assert s.ion_vgs_v == 1.8 and s.ioff_vgs_v == 0.0
    assert lenient_spec(R(measurements=["VTH"], ion_vgs_v=1.2)).ion_vgs_v is None


def test_a_uses_only_the_first_response_and_malformed_means_failed():
    ok = json.dumps(R(width_um=2.0))
    assert parse_first_json([ok])["width_um"] == 2.0
    assert parse_first_json(["{bad", ok]) is None                     # no repair call in configuration A
    assert parse_first_json(["[1, 2]"]) is None and parse_first_json([]) is None
