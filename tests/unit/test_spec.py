import pytest
from pydantic import ValidationError

from tinyspice.schemas import ExperimentSpec, Sweep


def test_example_spec_is_valid(spec_dict):
    s = ExperimentSpec.model_validate(spec_dict)
    assert s.sweep.n_points == 91  # 0..1.8 step 0.02 inclusive


def test_missing_temperature_rejected(spec_dict):
    del spec_dict["temperature_c"]
    with pytest.raises(ValidationError, match="temperature_c"):
        ExperimentSpec.model_validate(spec_dict)


def test_missing_width_rejected(spec_dict):
    del spec_dict["width_um"]  # the project's own NL example omits W; it must not be invented
    with pytest.raises(ValidationError, match="width_um"):
        ExperimentSpec.model_validate(spec_dict)


def test_missing_budget_points_rejected(spec_dict):
    spec_dict["budget"] = {}
    with pytest.raises(ValidationError, match="max_points"):
        ExperimentSpec.model_validate(spec_dict)


def test_unknown_field_rejected(spec_dict):
    spec_dict["secret_knob"] = 1
    with pytest.raises(ValidationError):
        ExperimentSpec.model_validate(spec_dict)


def test_idvg_requires_vds(spec_dict):
    del spec_dict["vds_v"]
    with pytest.raises(ValidationError, match="requires fixed `vds_v`"):
        ExperimentSpec.model_validate(spec_dict)


def test_idvg_with_vgs_is_contradictory(spec_dict):
    spec_dict["vgs_v"] = 0.9
    with pytest.raises(ValidationError, match="must not be set"):
        ExperimentSpec.model_validate(spec_dict)


def test_gds_not_extractable_from_idvg(spec_dict):
    spec_dict["measurements"] = ["GDS"]
    spec_dict["ion_vgs_v"] = spec_dict["ioff_vgs_v"] = None
    with pytest.raises(ValidationError, match="cannot be extracted"):
        ExperimentSpec.model_validate(spec_dict)


def test_gm_not_extractable_from_idvd(spec_dict):
    spec_dict.update(analysis="idvd", vds_v=None, vgs_v=1.0, measurements=["GM"], ion_vgs_v=None, ioff_vgs_v=None)
    with pytest.raises(ValidationError, match="cannot be extracted"):
        ExperimentSpec.model_validate(spec_dict)


def test_ion_requires_explicit_bias(spec_dict):
    spec_dict["ion_vgs_v"] = None
    with pytest.raises(ValidationError, match="ion_vgs_v"):
        ExperimentSpec.model_validate(spec_dict)


def test_unused_ion_bias_rejected(spec_dict):
    spec_dict["measurements"] = ["VTH", "GM", "SS", "IOFF"]
    with pytest.raises(ValidationError, match="ION not requested"):
        ExperimentSpec.model_validate(spec_dict)


def test_ion_bias_outside_sweep_rejected(spec_dict):
    spec_dict["ion_vgs_v"] = 2.5
    with pytest.raises(ValidationError, match="outside the sweep"):
        ExperimentSpec.model_validate(spec_dict)


def test_ion_not_above_ioff_rejected(spec_dict):
    spec_dict["ion_vgs_v"], spec_dict["ioff_vgs_v"] = 0.2, 0.5
    with pytest.raises(ValidationError, match="greater than"):
        ExperimentSpec.model_validate(spec_dict)


def test_duplicate_measurements_rejected(spec_dict):
    spec_dict["measurements"] = ["VTH", "VTH", "ION", "IOFF"]
    with pytest.raises(ValidationError, match="duplicate"):
        ExperimentSpec.model_validate(spec_dict)


def test_empty_measurements_rejected(spec_dict):
    spec_dict.update(measurements=[], ion_vgs_v=None, ioff_vgs_v=None)
    with pytest.raises(ValidationError):
        ExperimentSpec.model_validate(spec_dict)


@pytest.mark.parametrize("kw", [dict(start=1.0, stop=0.5, step=0.1), dict(start=0, stop=1, step=0.3),
                                dict(start=0, stop=1), dict(start=0, stop=1, step=0.1, points=11)])
def test_bad_sweeps_rejected(kw):
    with pytest.raises(ValidationError):
        Sweep(**kw)


def test_sweep_points_float_safe():
    assert Sweep(start=0, stop=1.8, step=0.05).n_points == 37  # classic float-accumulation trap
    assert Sweep(start=0, stop=1, points=5).n_points == 5
