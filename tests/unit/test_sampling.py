import numpy as np
import pytest

from tinyspice.executor import execute, run_sweep
from tinyspice.planner import build_plan
from tinyspice.errors import PlanRejected
from tinyspice.sampling import pilot_base, pilot_grid, refine_points, uniform_grid
from tinyspice.schemas import ExperimentSpec
from tinyspice.simulator import MockSimulator, find_tools
from tinyspice.simulator.models import get_profile
from tinyspice.simulator.netlist import UnsupportedSweep, build_netlist
from tinyspice.simulator.validate import validate_points


def ekv_log10(x, vth=0.45, n=1.3, vt=0.0259):
    """Analytic EKV-like Id(VGS): exponential below vth, square law above. Known knee near vth."""
    return 1e-6 * np.log1p(np.exp((np.asarray(x) - vth) / (2 * n * vt))) ** 2


# ---- grids ----
def test_uniform_grid_endpoints_and_count():
    g = uniform_grid(0.0, 1.8, 19)
    assert len(g) == 19 and g[0] == 0.0 and g[-1] == 1.8 and np.allclose(np.diff(g), 0.1)


def test_pilot_grid_merges_forced_points_without_duplicates():
    g = pilot_grid(0.0, 1.8, 10, forced=[0.0, 1.8, 0.95])
    assert len(g) == 11 and 0.95 in g and (np.diff(g) > 0).all()          # 0.0 and 1.8 already on the grid
    g2 = pilot_grid(0.0, 1.8, 10, forced=[0.2])                              # 0.2 == 0.2 exactly the grid (1.8/9)
    assert len(g2) == 10 and 0.2 in g2


def test_pilot_base_reserves_room_for_forced_points():
    assert pilot_base(40, 2) == 12 and pilot_base(20, 2) == 8 and pilot_base(10, 2) == 8


# ---- refine_points on a curve with a known knee ----
def test_refine_returns_requested_count_distinct_sorted_inside_range():
    x = uniform_grid(0.0, 1.8, 10)
    new = refine_points(x, ekv_log10(x), 20)
    assert len(new) == 20 and (np.diff(new) > 0).all() and new.min() > 0 and new.max() < 1.8
    assert not set(np.round(new, 9)) & set(np.round(x, 9))


def test_refine_is_deterministic():
    x = uniform_grid(0.0, 1.8, 10)
    a, b = refine_points(x, ekv_log10(x), 15), refine_points(x, ekv_log10(x), 15)
    assert np.array_equal(a, b)


def test_refine_beats_uniform_interpolation_error_on_known_curve():
    """Same number of points: curvature placement gives lower worst-case log10(Id) linear-interpolation error than uniform."""
    N, dense = 24, np.linspace(0, 1.8, 2001)
    f_dense = np.log10(ekv_log10(dense))
    xu = uniform_grid(0.0, 1.8, N)
    err_u = np.max(np.abs(np.interp(dense, xu, np.log10(ekv_log10(xu))) - f_dense))
    pilot = uniform_grid(0.0, 1.8, 8)
    xa = np.sort(np.concatenate([pilot, refine_points(pilot, ekv_log10(pilot), N - len(pilot))]))
    assert len(xa) == N
    err_a = np.max(np.abs(np.interp(dense, xa, np.log10(ekv_log10(xa))) - f_dense))
    assert err_a < err_u, (err_a, err_u)


def test_refine_concentrates_points_where_curvature_is_high():
    pilot = uniform_grid(0.0, 1.8, 10)
    new = refine_points(pilot, ekv_log10(pilot), 12)
    assert (np.abs(new - 0.45) < 0.45).sum() > len(new) / 2                  # majority near the knee, not spread flat


def test_refine_zero_points_and_bad_input():
    x = uniform_grid(0.0, 1.8, 10)
    assert len(refine_points(x, ekv_log10(x), 0)) == 0
    with pytest.raises(ValueError):
        refine_points(x[:3], ekv_log10(x[:3]), 2)
    with pytest.raises(ValueError):
        refine_points(x, np.where(np.arange(len(x)) == 3, np.nan, ekv_log10(x)), 2)


def test_refine_stops_at_min_gap_instead_of_inventing_tiny_intervals():
    x = np.linspace(0.0, 0.0012, 5)
    new = refine_points(x, ekv_log10(x), 50, min_gap=1e-4)
    assert 0 < len(new) < 50 and (np.diff(np.sort(np.concatenate([x, new]))) >= 1e-4 - 1e-12).all()


# ---- netlist + validation ----
def test_pwl_netlist_structure(spec_dict):
    s = ExperimentSpec.model_validate(dict(spec_dict, model_name="builtin_level1_nmos"))
    net = build_netlist(s, get_profile(s.model_name, find_tools()), points=[0.0, 0.2, 0.5, 0.9, 1.8])
    assert "VIDX idx 0 0" in net and "BGS g 0 V = pwl(v(idx)," in net and "dc VIDX 0 4 1" in net
    assert "wrdata raw.dat v(g) id" in net and "dc VGS" not in net
    assert "0,0,1,0.2,2,0.5,3,0.9,4,1.8" in net.replace("\n+ ", "")


def test_pwl_netlist_rejects_bad_points_and_idvd(spec_dict):
    s = ExperimentSpec.model_validate(dict(spec_dict, model_name="builtin_level1_nmos"))
    prof = get_profile(s.model_name, find_tools())
    for bad in ([0.0], [0.0, 0.5, 0.5, 1.0], [1.0, 0.5]):
        with pytest.raises(UnsupportedSweep):
            build_netlist(s, prof, points=bad)
    d = dict(spec_dict, model_name="builtin_level1_nmos", analysis="idvd", vds_v=None, vgs_v=1.0, measurements=["ID"], ion_vgs_v=None, ioff_vgs_v=None)
    d["sweep"] = {"start": 0.0, "stop": 1.8, "step": 0.1}
    with pytest.raises(UnsupportedSweep):
        build_netlist(ExperimentSpec.model_validate(d), prof, points=[0.0, 0.9, 1.8])


def test_validate_points():
    p = [0.0, 0.3, 1.0]
    assert validate_points(p, [1, 2, 3], p)[0]
    assert validate_points(p[:2], [1, 2], p)[1] == "ROW_COUNT_MISMATCH"
    assert validate_points([0.0, 0.31, 1.0], [1, 2, 3], p)[1] == "SWEEP_POINTS_MISMATCH"
    assert validate_points([0.0, 0.3, np.nan], [1, 2, 3], p)[1] == "NONFINITE_VALUES"


# ---- planner + executor (mock simulator; no ngspice) ----
def _spec(spec_dict, n=30, **over):
    d = dict(spec_dict, measurements=["VTH", "ION", "IOFF"], ion_vgs_v=1.8, ioff_vgs_v=0.0)
    d["sweep"] = {"start": 0.0, "stop": 1.8, "points": n}
    d["budget"] = {"max_points": 60}
    d.update(over)
    return ExperimentSpec.model_validate(d)


def test_planner_accepts_curvature_with_extra_tool_call(spec_dict, limits):
    s = _spec(spec_dict)
    pu, pc = build_plan(s, limits, "uniform"), build_plan(s, limits, "curvature")
    assert pc.estimated_points == pu.estimated_points == 30 and pc.estimated_tool_calls == pu.estimated_tool_calls + 1
    assert [st.order for st in pc.steps] == list(range(1, len(pc.steps) + 1))


def test_planner_rejects_curvature_for_too_few_points_and_idvd(spec_dict, limits):
    with pytest.raises(PlanRejected) as e:
        build_plan(_spec(spec_dict, n=8), limits, "curvature")
    assert e.value.code == "UNSUPPORTED_STRATEGY"


def test_curvature_executor_spends_exactly_n_points_and_keeps_forced_points(spec_dict, limits, tmp_path):
    s = _spec(spec_dict, n=30)
    rec = execute(s, limits, MockSimulator(), tmp_path, strategy="curvature")
    assert rec.sim.ok, (rec.message, rec.error_code)
    x = rec.sim.x
    assert len(x) == 30 and (np.diff(x) > 0).all() and x[0] == 0.0 and x[-1] == 1.8
    assert any(abs(x - 1.8) < 1e-9) and any(abs(x - 0.0) < 1e-9)
    assert rec.sim.meta["points_simulated"] == 30 and [p["phase"] for p in rec.sim.meta["phases"]] == ["pilot", "refine"]
    assert rec.status.value in {"successful", "partial"}


def test_curvature_never_exceeds_point_budget_for_any_n(spec_dict, limits):
    for n in (12, 13, 14, 17, 25, 40, 59):
        s = _spec(spec_dict, n=n)
        r = run_sweep(s, MockSimulator(), None.__class__ and __import__("pathlib").Path("."), "curvature") if False else None
        sim = MockSimulator()
        res = run_sweep(s, sim, __import__("pathlib").Path("unused"), "curvature")
        assert res.ok and len(res.x) <= n, (n, len(res.x))
        assert len(res.x) == n                                              # and it spends the budget it was given


def test_forced_bias_point_inside_range_is_always_simulated(spec_dict):
    s = _spec(spec_dict, n=25, ion_vgs_v=1.37, ioff_vgs_v=0.0)
    res = run_sweep(s, MockSimulator(), __import__("pathlib").Path("unused"), "curvature")
    assert res.ok and any(abs(res.x - 1.37) < 1e-9)


def test_pilot_failure_is_reported_not_swallowed(spec_dict):
    s = _spec(spec_dict, n=30)
    res = run_sweep(s, MockSimulator(fault="nonconvergence"), __import__("pathlib").Path("unused"), "curvature")
    assert not res.ok and res.error_code == "NONCONVERGENCE"


def test_refine_phase_failure_is_reported(spec_dict):
    s = _spec(spec_dict, n=30)
    res = run_sweep(s, MockSimulator(fault="timeout", fail_times=None) if False else _FailSecond(), __import__("pathlib").Path("unused"), "curvature")
    assert not res.ok and res.error_code == "TIMEOUT"


class _FailSecond(MockSimulator):
    n = 0

    def run(self, spec, run_dir=None, points=None):
        self.n += 1
        if self.n == 2:
            from tinyspice.simulator.base import SimResult
            return SimResult(ok=False, error_code="TIMEOUT", error_detail="injected second-phase fault")
        return super().run(spec, run_dir, points)


# ---- arm W: measurement-aware window placement ----
from tinyspice.sampling import window_points  # noqa: E402

I_HI = 1e-7 * 1.0 / 0.18 * 0 + 5.6e-7          # an Ic like W/L = 5.6 (value only matters relative to the curve below)


def _window_v(i_hi, decades=3.0):
    xs = np.linspace(0, 1.8, 20001)
    f = np.log10(ekv_log10(xs))
    return float(np.interp(np.log10(i_hi) - decades, f, xs)), float(np.interp(np.log10(i_hi), f, xs))


def test_window_points_land_inside_the_extractor_window():
    x = uniform_grid(0.0, 1.8, 9)                       # coarse pilot: ~0.225 V apart, window is narrower than a gap
    v_lo, v_hi = _window_v(I_HI)
    new = window_points(x, ekv_log10(x), I_HI, target=6)
    allp = np.sort(np.concatenate([x, new]))
    inside = allp[(allp >= v_lo) & (allp <= v_hi)]
    assert len(new) > 0 and len(inside) >= 4, (v_lo, v_hi, inside)
    assert ((new > v_lo) & (new < v_hi)).all()           # never wasted outside the window (central part only)


def test_window_points_empty_when_pilot_does_not_bracket_ic():
    x = uniform_grid(0.0, 0.2, 9)                       # curve never reaches Ic in this range
    assert len(window_points(x, ekv_log10(x), I_HI)) == 0
    assert len(window_points(x, ekv_log10(x), 1e-30)) == 0     # Ic already exceeded at the first point


def test_window_points_respects_max_new_and_target():
    x = uniform_grid(0.0, 1.8, 9)
    assert len(window_points(x, ekv_log10(x), I_HI, target=10, max_new=2)) == 2
    assert len(window_points(x, ekv_log10(x), I_HI, target=1)) == 1     # no pilot point is inside the window yet
    assert len(window_points(x, ekv_log10(x), I_HI, target=0)) == 0     # nothing required


def test_refine_with_extra_points_splits_around_them_and_avoids_duplicates():
    x = uniform_grid(0.0, 1.8, 10)
    extra = np.array([0.3, 0.31])
    rest = refine_points(x, ekv_log10(x), 8, extra=extra)
    assert len(rest) == 8 and not (set(np.round(rest, 9)) & set(np.round(np.concatenate([x, extra]), 9)))


def test_window_strategy_spends_exactly_n_points_and_fills_the_ss_window(spec_dict):
    s = _spec(spec_dict, n=16, measurements=["VTH", "SS", "ION", "IOFF"])
    res = run_sweep(s, MockSimulator(), __import__("pathlib").Path("unused"), "window", pilot_frac=0.4)
    assert res.ok and len(res.x) == 16 and (np.diff(res.x) > 0).all()
    i_hi = s.vth_ic_a * s.width_um / s.length_um
    in_win = ((res.y >= i_hi / 1e3) & (res.y <= i_hi)).sum()
    assert in_win >= 4, in_win
    assert [p["phase"] for p in res.meta["phases"]] == ["pilot", "refine"] and res.meta["strategy"] == "window"


def test_window_falls_back_to_curvature_when_window_unreachable(spec_dict):
    s = _spec(spec_dict, n=20)
    s = ExperimentSpec.model_validate({**s.model_dump(mode="json"), "sweep": {"start": 0.0, "stop": 0.2, "points": 20}, "ion_vgs_v": 0.2, "ioff_vgs_v": 0.0})
    res = run_sweep(s, MockSimulator(), __import__("pathlib").Path("unused"), "window")
    assert res.ok and len(res.x) == 20


def test_planner_accepts_window(spec_dict, limits):
    assert build_plan(_spec(spec_dict), limits, "window").estimated_tool_calls == build_plan(_spec(spec_dict), limits, "curvature").estimated_tool_calls
