"""E1: extractors must recover KNOWN answers from analytic curves, and refuse (never guess) on bad data."""
import numpy as np
import pytest
from scipy.optimize import brentq

from tinyspice.measurements import extract_all
from tinyspice.measurements import extractors as ex
from tinyspice.measurements.result import MeasurementError
from tinyspice.schemas import ExperimentSpec

VT = 0.025852  # kT/q at 300 K


def grid(stop=1.8, step=0.02):
    return np.linspace(0.0, stop, int(round(stop / step)) + 1)


def ekv(v, i_s=1e-4, v0=0.45, n=1.4):
    return i_s * np.log1p(np.exp((v - v0) / (2 * n * VT))) ** 2


def code(fn, *a, **k):
    with pytest.raises(MeasurementError) as e:
        fn(*a, **k)
    return e.value.code


# ---------------- SS ----------------
def test_ss_pure_exponential_exact():
    n = 1.4
    x = grid()
    y = 1e-15 * np.exp(x / (n * VT))                     # SS = n*Vt*ln10 exactly
    # shift so the VTH-current window lies inside the sweep
    y = y * (1e-7 / np.interp(0.6, x, y))
    val, d = ex.ss_fit(x, y, 1.0, 1.0)
    assert val == pytest.approx(1000 * n * VT * np.log(10), rel=2e-3)
    assert d["r2"] > 0.99999 and d["span_decades"] >= 2.5


def test_ss_ekv_deep_subthreshold_matches_theory():
    x = grid()
    val, d = ex.ss_fit(x, ekv(x), 1.0, 1.0)
    assert val == pytest.approx(1000 * 1.4 * VT * np.log(10), rel=0.01)


def test_ss_with_1pct_noise_stays_close():
    x = grid()
    rng = np.random.default_rng(0)
    y = ekv(x) * (1 + 0.01 * rng.standard_normal(len(x)))
    val, d = ex.ss_fit(x, y, 1.0, 1.0)
    assert val == pytest.approx(1000 * 1.4 * VT * np.log(10), rel=0.04) and d["r2"] > 0.995


def test_ss_refuses_non_exponential():
    x = grid()
    y = 1e-7 * 10 ** (-3 + 3 * (x / 1.8) ** 12)          # decades packed at the end: not a straight line in log
    assert code(ex.ss_fit, x, y, 1.0, 1.0) in {"POOR_FIT", "INSUFFICIENT_POINTS", "WINDOW_TOO_NARROW"}


def test_ss_refuses_too_few_points():
    x = np.linspace(0, 1.8, 7)
    assert code(ex.ss_fit, x, ekv(x), 1.0, 1.0) == "INSUFFICIENT_POINTS"


def test_ss_refuses_flat_curve():
    x = grid()
    assert code(ex.ss_fit, x, np.full_like(x, 1e-9), 1.0, 1.0) in {"INSUFFICIENT_POINTS", "WINDOW_TOO_NARROW"}


# ---------------- VTH ----------------
def test_vth_matches_independent_root_find():
    x = grid()
    ref = brentq(lambda v: ekv(v) - 1e-7, 0.0, 1.8)      # independent solve of the same analytic function
    val, d = ex.vth_constant_current(x, ekv(x), 1.0, 1.0)
    assert val == pytest.approx(ref, abs=5e-4)
    assert d["recrosses_below_target"] is False


def test_vth_scales_with_wl():
    x = grid()
    v1, _ = ex.vth_constant_current(x, ekv(x), 1.0, 1.0)
    v2, _ = ex.vth_constant_current(x, ekv(x), 10.0, 1.0)   # 10x current criterion -> higher VTH
    assert v2 > v1


def test_vth_not_crossed():
    x = grid()
    assert code(ex.vth_constant_current, x, np.full_like(x, 1e-12), 1.0, 1.0) == "NOT_CROSSED"


def test_vth_already_above():
    x = grid()
    assert code(ex.vth_constant_current, x, np.full_like(x, 1e-3), 1.0, 1.0) == "ALREADY_ABOVE"


def test_vth_flags_recrossing():
    x = grid()
    y = ekv(x).copy()
    y[-10:] = 1e-9                                            # current collapses after crossing
    _, d = ex.vth_constant_current(x, y, 1.0, 1.0)
    assert d["recrosses_below_target"] is True


# ---------------- GM / GDS ----------------
def test_gm_square_law_exact():
    x = grid()
    k, vt = 1e-3, 0.5
    y = 0.5 * k * np.clip(x - vt, 0, None) ** 2
    val, d = ex.gm_max(x, y)
    assert val == pytest.approx(k * (1.8 - vt), rel=1e-9)
    assert d["max_on_sweep_edge"] is True and d["vgs_at_max_v"] == pytest.approx(1.8)


def test_gm_peak_not_on_edge_is_reported():
    x = grid()
    y = np.sin(x * np.pi / 1.8) * 1e-3                         # gm peaks at the start; falls after
    val, d = ex.gm_max(x, y)
    assert val > 0 and d["vgs_at_max_v"] <= 0.2


def test_gm_nonuniform_grid():
    x = np.unique(np.concatenate([np.linspace(0, 1.8, 40), [0.5, 0.511, 0.9, 0.903]]))
    y = 3e-4 * x**2                                            # gm = 6e-4*x -> 1.08e-3 at 1.8
    val, _ = ex.gm_max(x, y)
    assert val == pytest.approx(6e-4 * 1.8, rel=1e-9)


def test_gds_end_exact_for_linear_saturation():
    x = grid()
    y = 1e-4 * (1 + 0.05 * x) * np.tanh(x / 0.1)
    val, d = ex.gds_end(x, y)
    assert val == pytest.approx(1e-4 * 0.05, rel=1e-4) and d["vds_v"] == pytest.approx(1.8)


# ---------------- ION / IOFF ----------------
def test_id_at_grid_point_exact_and_between():
    x = grid()
    y = ekv(x)
    v, _ = ex.id_at(x, y, 1.8)
    assert v == pytest.approx(y[-1], rel=1e-12)
    mid, d = ex.id_at(x, y, 0.5)                               # on grid
    assert mid == pytest.approx(ekv(0.5), rel=1e-12) and d["interpolation"] == "log-linear"
    between, _ = ex.id_at(x, y, 0.51)
    assert min(ekv(0.50), ekv(0.52)) < between < max(ekv(0.50), ekv(0.52))


def test_id_at_linear_when_zero_present():
    x = grid()
    v, d = ex.id_at(x, 2e-3 * x, 0.9)
    assert v == pytest.approx(1.8e-3, rel=1e-12) and d["interpolation"] == "linear"


def test_id_at_out_of_range():
    x = grid()
    assert code(ex.id_at, x, ekv(x), 2.5) == "OUT_OF_RANGE"
    assert code(ex.id_at, x, ekv(x), -0.1) == "OUT_OF_RANGE"


# ---------------- data hygiene: refuse, never fabricate ----------------
@pytest.mark.parametrize("x,y", [
    (np.linspace(0, 1, 2), np.array([1.0, 2.0])),                                  # too short
    (np.linspace(0, 1, 5), np.array([1, 2, np.nan, 4, 5.0])),                      # NaN
    (np.linspace(0, 1, 5), np.array([1, 2, np.inf, 4, 5.0])),                      # Inf
    (np.array([0, 0.5, 0.4, 0.8, 1.0]), np.arange(5.0)),                           # non-monotonic x
    (np.linspace(0, 1, 5), np.arange(4.0)),                                        # shape mismatch
])
def test_invalid_data_rejected_by_every_extractor(x, y):
    for fn in (ex.gm_max, ex.gds_end):
        assert code(fn, x, y) == "INVALID_DATA"
    assert code(ex.vth_constant_current, x, y, 1.0, 1.0) == "INVALID_DATA"
    assert code(ex.ss_fit, x, y, 1.0, 1.0) == "INVALID_DATA"
    assert code(ex.id_at, x, y, 0.5) == "INVALID_DATA"


# ---------------- engine on a spec ----------------
def test_engine_full_set_on_analytic_curve(spec_dict):
    spec = ExperimentSpec.model_validate({**spec_dict, "width_um": 1.0, "length_um": 1.0})
    x = grid()
    res = extract_all(spec, x, ekv(x), floor_a=1.8e-18)
    assert set(res) == {"VTH", "GM", "SS", "ION", "IOFF"} and all(r.ok for r in res.values())
    assert res["ION"].value == pytest.approx(ekv(1.8), rel=1e-9)
    assert res["IOFF"].diagnostics["near_solver_floor"] is False
    assert res["VTH"].conditions["vds_v"] == 1.8 and "Ic" in res["VTH"].method


def test_engine_failures_are_independent_and_valueless(spec_dict):
    spec = ExperimentSpec.model_validate({**spec_dict, "width_um": 1.0, "length_um": 1.0})
    x = grid()
    res = extract_all(spec, x, np.full_like(x, 1e-12))         # nothing crosses, nothing is exponential
    assert not res["VTH"].ok and res["VTH"].value is None and res["VTH"].error_code == "NOT_CROSSED"
    assert not res["SS"].ok and res["SS"].value is None
    assert res["ION"].ok and res["IOFF"].ok                     # explicit-bias reads still succeed
    assert res["IOFF"].diagnostics is not None


def test_engine_flags_ioff_at_solver_floor(spec_dict):
    spec = ExperimentSpec.model_validate({**spec_dict, "width_um": 1.0, "length_um": 1.0})
    x = grid()
    y = 1.8e-12 + 1e-9 * ekv(x)                                # off-state sits ON the old gmin*VDS floor
    res = extract_all(spec, x, y, floor_a=1.8e-12)
    assert res["IOFF"].diagnostics["near_solver_floor"] is True
    assert res["IOFF"].value == pytest.approx(1.8e-12, rel=1e-3)


def test_engine_id_curve_and_gds(spec_dict):
    d = {**spec_dict, "analysis": "idvd", "vds_v": None, "vgs_v": 1.2, "measurements": ["ID", "GDS"],
         "ion_vgs_v": None, "ioff_vgs_v": None}
    spec = ExperimentSpec.model_validate(d)
    x = grid()
    y = 1e-4 * (1 + 0.05 * x) * np.tanh(x / 0.1)
    res = extract_all(spec, x, y)
    assert res["ID"].ok and res["ID"].series is not None and len(res["ID"].series["id_a"]) == len(x)
    assert res["GDS"].value == pytest.approx(5e-6, rel=1e-3)
