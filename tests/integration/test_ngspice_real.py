"""Real ngspice runs. Auto-skipped when ngspice or the SKY130 files are not installed in ./.tools."""
import numpy as np
import pytest

from tinyspice.schemas import ExperimentSpec
from tinyspice.simulator import NgspiceSimulator, find_tools

pytestmark = pytest.mark.ngspice
TOOLS = find_tools()
needs_ngspice = pytest.mark.skipif(TOOLS.ngspice_exe is None, reason="ngspice not installed (scripts/setup_tools.py)")
has_pm3 = TOOLS.sky130_root is not None and (
    TOOLS.sky130_root / "cells/nfet_01v8/sky130_fd_pr__nfet_01v8__tt.pm3.spice").exists()
needs_sky = pytest.mark.skipif(not has_pm3, reason="SKY130 model files not installed")


def mk(spec_dict, **over):
    d = dict(spec_dict)
    d.update(over)
    return ExperimentSpec.model_validate(d)


@needs_ngspice
def test_version_is_47():
    assert NgspiceSimulator().version() == "ngspice-47"


@needs_ngspice
def test_builtin_level1_idvg_real_run(spec_dict, tmp_path):
    s = mk(spec_dict, model_name="builtin_level1_nmos", width_um=2.0, length_um=1.0)
    r = NgspiceSimulator().run(s, tmp_path / "run")
    assert r.ok, (r.error_code, r.error_detail, r.stderr[-300:])
    assert len(r.x) == s.sweep.n_points == 91
    assert r.y[0] < 1e-9 and r.y[-1] > 1e-5 and (np.diff(r.y) >= -1e-12).all()
    assert r.meta["educational_model"] is True and (tmp_path / "run" / "netlist.cir").exists()


@needs_ngspice
@needs_sky
def test_sky130_idvg_real_run(spec_dict, tmp_path):
    s = mk(spec_dict)  # sky130_fd_pr__nfet_01v8, W=1 L=0.18 T=27
    r = NgspiceSimulator().run(s, tmp_path / "run")
    assert r.ok, (r.error_code, r.error_detail, r.stderr[-300:])
    assert len(r.x) == 91 and r.simulator_version == "ngspice-47"
    assert r.meta["educational_model"] is False and len(r.meta["model_files_sha256"]) == 3
    assert 0 < r.y[0] < 1e-13       # off-state leakage must sit BELOW the old 1.8 pA gmin*VDS artefact
    assert 1e-4 < r.y[-1] < 2e-3    # plausibility only: ~hundreds of uA for W=1um at 1.8 V
    assert (np.diff(r.y) > 0).all()  # strictly increasing with VGS at VDS=1.8


@needs_ngspice
def test_bad_model_include_is_reported_not_hidden(spec_dict, tmp_path):
    from tinyspice.simulator import models as M
    prof = M.get_profile("builtin_level1_nmos", TOOLS)
    bad = M.ModelProfile(**{**prof.__dict__, "preamble": ('.include "C:/definitely/not/here.spice"', *prof.preamble)})
    r = NgspiceSimulator().run(mk(spec_dict, model_name="builtin_level1_nmos"), tmp_path / "run", profile=bad)
    assert not r.ok and r.error_code == "MISSING_INCLUDE"


# ---- physics sanity (regression guards found during Stage 1 hardening; bounds are deliberately loose) ----
def _at(r, v):
    return float(np.interp(v, r.x, r.y))


@needs_ngspice
@needs_sky
def test_sky130_physical_trends(spec_dict, tmp_path):
    sim = NgspiceSimulator()
    runs = {}
    for tag, over in {"base": {}, "w2": {"width_um": 2.0}, "l036": {"length_um": 0.36},
                      "cold": {"temperature_c": -40.0}, "hot": {"temperature_c": 125.0}}.items():
        r = sim.run(mk(spec_dict, **over), tmp_path / tag)
        assert r.ok, (tag, r.error_code, r.error_detail)
        runs[tag] = r
    assert 1.8 < _at(runs["w2"], 1.8) / _at(runs["base"], 1.8) < 2.6      # ~2x (SKY130 is binned, so not exact)
    assert _at(runs["l036"], 1.8) < _at(runs["base"], 1.8)               # longer channel -> less current
    assert _at(runs["hot"], 0.45) > 5 * _at(runs["base"], 0.45) > 25 * _at(runs["cold"], 0.45)  # subthreshold rises with T
    assert _at(runs["hot"], 1.8) < _at(runs["base"], 1.8) < _at(runs["cold"], 1.8)  # on-current falls with T (mobility)
    assert runs["cold"].y[0] < 5e-14                                      # cold leakage is not a solver floor


@needs_ngspice
@needs_sky
def test_sky130_idvd_real_run_saturates(spec_dict, tmp_path):
    s = mk(spec_dict, analysis="idvd", vds_v=None, vgs_v=1.2, measurements=["GDS"], ion_vgs_v=None, ioff_vgs_v=None)
    r = NgspiceSimulator().run(s, tmp_path / "idvd")
    assert r.ok, (r.error_code, r.error_detail)
    assert len(r.x) == 91 and abs(r.y[0]) < 1e-12 and (np.diff(r.y) > 0).all()
    slope_lin = (_at(r, 0.12) - _at(r, 0.08)) / 0.04
    slope_sat = (_at(r, 1.76) - _at(r, 1.64)) / 0.12
    assert slope_sat < 0.2 * slope_lin                                    # output conductance collapses in saturation


@needs_ngspice
def test_real_timeout_kills_process(spec_dict, tmp_path):
    s = mk(spec_dict, budget={"max_points": 200, "max_runtime_s": 0.01})
    r = NgspiceSimulator().run(s, tmp_path / "t")
    assert not r.ok and r.error_code == "TIMEOUT"


# ---- E2: real SKY130 data, measurements cross-checked by an INDEPENDENT scipy computation ----
@needs_ngspice
@needs_sky
def test_e2_sky130_measurements_vs_independent_scipy(spec_dict, tmp_path):
    from scipy.interpolate import CubicSpline
    from scipy.optimize import brentq

    from tinyspice.measurements import extract_all
    s = mk(spec_dict, measurements=["VTH", "GM", "SS", "ION", "IOFF"])  # W=1, L=0.18, T=27, VDS=1.8
    r = NgspiceSimulator().run(s, tmp_path / "e2")
    assert r.ok
    m = extract_all(s, r.x, r.y, floor_a=1e-18 * 1.8)
    assert all(v.ok for v in m.values()), {k: (v.error_code, v.error_detail) for k, v in m.items()}

    target = 1e-7 * 1.0 / 0.18
    ls = CubicSpline(r.x, np.log10(r.y))                                  # independent: cubic spline in log domain
    vth_ref = brentq(lambda v: float(ls(v)) - np.log10(target), 0.2, 1.0)
    assert m["VTH"].value == pytest.approx(vth_ref, abs=3e-3)

    fine = np.linspace(0, 1.8, 18001)
    gm_ref = float(CubicSpline(r.x, r.y).derivative()(fine).max())       # independent: spline derivative
    assert m["GM"].value == pytest.approx(gm_ref, rel=0.03)

    lo, hi = m["SS"].diagnostics["window_vgs_v"]
    w = np.linspace(lo, hi, 400)
    ss_ref = 1000.0 / float(np.polyfit(w, ls(w), 1)[0])                  # independent: fit on the spline over same window
    assert m["SS"].value == pytest.approx(ss_ref, rel=0.02)

    assert 0.3 < m["VTH"].value < 0.8 and 60 < m["SS"].value < 130        # physical plausibility, not verification
    assert m["ION"].value == pytest.approx(r.y[-1], rel=1e-9) and m["IOFF"].value == pytest.approx(r.y[0], rel=1e-9)
    assert m["IOFF"].diagnostics["near_solver_floor"] is False and m["IOFF"].value < 1e-13


@needs_ngspice
@needs_sky
def test_curvature_strategy_real_sky130_end_to_end(spec_dict, limits, tmp_path):
    """Two real ngspice processes (pilot + refine): exactly N points, forced bias points present, honest measurements
    that agree with a dense uniform reference on the same device."""
    from tinyspice.executor import execute

    N = 28
    d = dict(spec_dict, measurements=["VTH", "SS", "ION", "IOFF"], ion_vgs_v=1.8, ioff_vgs_v=0.0)
    d["sweep"] = {"start": 0.0, "stop": 1.8, "points": N}
    d["budget"] = {"max_points": 400}
    rec = execute(mk(d), limits, NgspiceSimulator(), tmp_path / "cur", strategy="curvature")
    assert rec.sim.ok, (rec.error_code, rec.message)
    x = rec.sim.x
    assert len(x) == N and (np.diff(x) > 0).all() and abs(x[0]) < 1e-9 and abs(x[-1] - 1.8) < 1e-9
    assert [p["phase"] for p in rec.sim.meta["phases"]] == ["pilot", "refine"]
    assert (tmp_path / "cur" / rec.run_id / "sim_pilot" / "netlist.cir").exists() and (tmp_path / "cur" / rec.run_id / "sim_refine" / "netlist.cir").exists()
    dense = dict(d)
    dense["sweep"] = {"start": 0.0, "stop": 1.8, "step": 0.002}
    dense["budget"] = {"max_points": 1000}
    ref = execute(mk(dense), limits, NgspiceSimulator(), tmp_path / "ref")
    assert ref.status.value == "successful", ref.message
    for key, tol in (("ION", 0.02), ("VTH", 0.01)):
        a, b = rec.measurements[key], ref.measurements[key]
        if a.ok:
            assert abs(a.value - b.value) <= tol * (abs(b.value) if key == "ION" else 1.0), (key, a.value, b.value)
    # ION and IOFF are read at the exact forced bias points, so they must match the dense reference closely
    assert rec.measurements["ION"].ok and rec.measurements["IOFF"].ok


@needs_ngspice
@needs_sky
@pytest.mark.parametrize("n", [50, 37, 91, 17])
def test_uniform_points_sweep_returns_exactly_n_rows(spec_dict, n, tmp_path):
    """Regression (found in Stage 5): a `points`-based sweep with a non-representable step (1.8/49) returned 49 rows for 50."""
    d = dict(spec_dict)
    d["sweep"] = {"start": 0.0, "stop": 1.8, "points": n}
    d["budget"] = {"max_points": 200}
    r = NgspiceSimulator().run(mk(d), tmp_path / "r")
    assert r.ok, (r.error_code, r.error_detail)
    assert len(r.x) == n and abs(r.x[-1] - 1.8) < 1e-6
