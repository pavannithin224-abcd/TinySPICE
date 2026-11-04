import pytest

from tinyspice.errors import PlanRejected
from tinyspice.planner import build_plan
from tinyspice.planner.planner import spec_hash
from tinyspice.schemas import ExperimentSpec, ExperimentStatus


def make(spec_dict, **over):
    spec_dict.update(over)
    return ExperimentSpec.model_validate(spec_dict)


def test_valid_plan(spec_dict, limits):
    p = build_plan(make(spec_dict), limits)
    assert p.estimated_points == 91 <= p.budget_max_points == 200
    assert [s.action for s in p.steps][0] == "generate_netlist"
    assert p.estimated_tool_calls == 3
    assert any("NOT yet verified" in r for r in p.rationale)  # honesty flag must surface
    assert p.resolved_conditions["vth_ic_a_at_unit_wl"] == 1e-7


def test_plan_is_deterministic(spec_dict, limits):
    a, b = build_plan(make(spec_dict), limits), build_plan(make(spec_dict), limits)
    assert a == b and len(a.spec_sha256) == 64


def test_hash_changes_with_spec(spec_dict, limits):
    h1 = spec_hash(make(spec_dict))
    h2 = spec_hash(make(dict(spec_dict), temperature_c=85.0))
    assert h1 != h2


def test_budget_exceeded_is_not_silently_coarsened(spec_dict, limits):
    with pytest.raises(PlanRejected) as e:
        build_plan(make(spec_dict, budget={"max_points": 50}), limits)
    assert e.value.code == "BUDGET_EXCEEDED_POINTS"
    assert e.value.status is ExperimentStatus.STOPPED_BUDGET


def test_tool_call_budget(spec_dict, limits):
    with pytest.raises(PlanRejected) as e:
        build_plan(make(spec_dict, budget={"max_points": 200, "max_tool_calls": 2}), limits)
    assert e.value.code == "BUDGET_EXCEEDED_TOOL_CALLS"


@pytest.mark.parametrize("over,code", [
    (dict(length_um=0.10), "GEOMETRY_OUT_OF_RANGE"),
    (dict(width_um=50.0), "GEOMETRY_OUT_OF_RANGE"),
    (dict(temperature_c=200.0), "TEMPERATURE_OUT_OF_RANGE"),
    (dict(vds_v=3.3), "VOLTAGE_OUT_OF_RANGE"),
    (dict(model_name="other_model"), "DEVICE_MODEL_MISMATCH"),
])
def test_device_limit_violations(spec_dict, limits, over, code):
    with pytest.raises(PlanRejected) as e:
        build_plan(make(spec_dict, **over), limits)
    assert e.value.code == code
    assert e.value.status is ExperimentStatus.REJECTED_INVALID


def test_sweep_beyond_supported_voltage(spec_dict, limits):
    with pytest.raises(PlanRejected) as e:
        build_plan(make(spec_dict, sweep={"start": 0.0, "stop": 2.4, "step": 0.02}, ion_vgs_v=1.8), limits)
    assert e.value.code == "VOLTAGE_OUT_OF_RANGE"


def test_unimplemented_strategy_refused(spec_dict, limits):
    with pytest.raises(PlanRejected) as e:
        build_plan(make(spec_dict), limits, strategy="curvature")
    assert e.value.code == "UNSUPPORTED_STRATEGY"
