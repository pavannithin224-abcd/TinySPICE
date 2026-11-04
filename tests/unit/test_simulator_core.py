import subprocess
from pathlib import Path

import numpy as np
import pytest

from tinyspice.schemas import ExperimentSpec
from tinyspice.simulator import (MockSimulator, NgspiceSimulator, UnsupportedDevice, build_netlist,
                                 classify_ngspice_error, find_tools, get_profile, validate_output)
from tinyspice.simulator import models as M


def spec_from(d, **over):
    d = dict(d)
    d.update(over)
    return ExperimentSpec.model_validate(d)


@pytest.fixture
def builtin_spec(spec_dict):
    return spec_from(spec_dict, model_name="builtin_level1_nmos")


@pytest.fixture
def tools():
    return find_tools()


# ---------- netlist ----------
def test_netlist_idvg_cards(builtin_spec, tools):
    n = build_netlist(builtin_spec, get_profile("builtin_level1_nmos", tools))
    assert "VDS d 0 1.8" in n and "VGS g 0 0" in n
    assert "dc VGS 0 1.8 0.02" in n
    assert "let id = -i(VDS)" in n and "wrdata raw.dat id" in n
    assert ".temp 27" in n and n.rstrip().endswith(".end")


def test_netlist_idvd_sweeps_vds(spec_dict, tools):
    s = spec_from(spec_dict, model_name="builtin_level1_nmos", analysis="idvd", vds_v=None, vgs_v=1.2,
                  measurements=["GDS"], ion_vgs_v=None, ioff_vgs_v=None)
    n = build_netlist(s, get_profile("builtin_level1_nmos", tools))
    assert "VDS d 0 0" in n and "VGS g 0 1.2" in n and "dc VDS 0 1.8 0.02" in n


def test_netlist_points_converted_to_step(spec_dict, tools):
    s = spec_from(spec_dict, model_name="builtin_level1_nmos", sweep={"start": 0.0, "stop": 1.8, "points": 19})
    assert "dc VGS 0 1.8 0.1" in build_netlist(s, get_profile("builtin_level1_nmos", tools))


def test_netlist_is_deterministic(builtin_spec, tools):
    p = get_profile("builtin_level1_nmos", tools)
    assert build_netlist(builtin_spec, p) == build_netlist(builtin_spec, p)


def test_pmos_unsupported(spec_dict, tools):
    s = spec_from(spec_dict, model_name="builtin_level1_nmos", device_type="pmos")
    with pytest.raises(UnsupportedDevice):
        build_netlist(s, get_profile("builtin_level1_nmos", tools))


def test_unsafe_path_rejected():
    with pytest.raises(ValueError):
        M._q(Path('C:/x/evil".spice'))


def test_unknown_model(tools):
    with pytest.raises(M.UnknownModel):
        get_profile("nope", tools)


# ---------- validation / classification ----------
def good(n=5):
    x = np.linspace(0, 1, n)
    return x, x * 1e-3


def test_validate_ok():
    x, y = good()
    assert validate_output(x, y, 5, 0, 1) == (True, None, None)


@pytest.mark.parametrize("mut,code", [
    (lambda x, y: (x[:-1], y[:-1]), "ROW_COUNT_MISMATCH"),
    (lambda x, y: (x, np.where(np.arange(5) == 2, np.nan, y)), "NONFINITE_VALUES"),
    (lambda x, y: (x[::-1].copy(), y), "NON_MONOTONIC_SWEEP"),
    (lambda x, y: (x + 0.1, y), "SWEEP_ENDPOINT_MISMATCH"),
])
def test_validate_failures(mut, code):
    x, y = mut(*good())
    ok, c, _ = validate_output(x, y, 5, 0, 1)
    assert not ok and c == code


@pytest.mark.parametrize("text,code", [
    ("Error: Could not find include file foo.spice", "MISSING_INCLUDE"),
    ("doAnalyses: Timestep too small", "NONCONVERGENCE"),
    ("Error: unknown subckt: x1 d g 0 0 nfoo", "MODEL_NOT_FOUND"),
    ("all fine", None),
])
def test_classify(text, code):
    assert classify_ngspice_error(text) == code


# ---------- mock ----------
def test_mock_ok(builtin_spec):
    r = MockSimulator().run(builtin_spec)
    assert r.ok and len(r.x) == builtin_spec.sweep.n_points and (np.diff(r.y) >= 0).all()


@pytest.mark.parametrize("fault,code", [("timeout", "TIMEOUT"), ("nonconvergence", "NONCONVERGENCE"),
                                        ("missing_include", "MISSING_INCLUDE"), ("nonzero_exit", "NONZERO_EXIT"),
                                        ("truncated", "ROW_COUNT_MISMATCH"), ("nan", "NONFINITE_VALUES")])
def test_mock_faults_never_ok(builtin_spec, fault, code):
    r = MockSimulator(fault=fault).run(builtin_spec)
    assert not r.ok and r.error_code == code


def test_mock_fail_times_then_recovers(builtin_spec):
    m = MockSimulator(fault="nonconvergence", fail_times=2)
    assert [m.run(builtin_spec).ok for _ in range(3)] == [False, False, True]


def test_mock_unknown_fault():
    with pytest.raises(ValueError):
        MockSimulator(fault="bogus")


# ---------- ngspice runner with patched subprocess (no ngspice needed) ----------
@pytest.fixture
def fake_sim(tmp_path):
    exe = tmp_path / "fake.exe"
    exe.write_text("x")
    sim = NgspiceSimulator(exe=exe)
    sim._version = "ngspice-47"
    return sim


def _patch(monkeypatch, fn):
    monkeypatch.setattr(subprocess, "run", fn)


def test_runner_timeout(monkeypatch, fake_sim, builtin_spec, tmp_path):
    def boom(*a, **k):
        raise subprocess.TimeoutExpired(cmd="x", timeout=1, output=b"partial")
    _patch(monkeypatch, boom)
    r = fake_sim.run(builtin_spec, tmp_path / "r")
    assert not r.ok and r.error_code == "TIMEOUT"


def test_runner_nonzero_exit_is_classified(monkeypatch, fake_sim, builtin_spec, tmp_path):
    _patch(monkeypatch, lambda *a, **k: subprocess.CompletedProcess(a, 1, "", "Error: Could not find include file x"))
    r = fake_sim.run(builtin_spec, tmp_path / "r")
    assert not r.ok and r.error_code == "MISSING_INCLUDE" and r.exit_code == 1


def test_runner_exit0_with_error_text_is_failure(monkeypatch, fake_sim, builtin_spec, tmp_path):
    _patch(monkeypatch, lambda *a, **k: subprocess.CompletedProcess(a, 0, "", "Error: something bad"))
    r = fake_sim.run(builtin_spec, tmp_path / "r")
    assert not r.ok and r.error_code == "ERROR_IN_OUTPUT"


def test_runner_missing_output(monkeypatch, fake_sim, builtin_spec, tmp_path):
    _patch(monkeypatch, lambda *a, **k: subprocess.CompletedProcess(a, 0, "ok", ""))
    r = fake_sim.run(builtin_spec, tmp_path / "r")
    assert not r.ok and r.error_code == "NO_OUTPUT"


def test_runner_refuses_overwrite(monkeypatch, fake_sim, builtin_spec, tmp_path):
    _patch(monkeypatch, lambda *a, **k: subprocess.CompletedProcess(a, 0, "ok", ""))
    fake_sim.run(builtin_spec, tmp_path / "r")
    with pytest.raises(FileExistsError):
        fake_sim.run(builtin_spec, tmp_path / "r")


def test_runner_uses_argv_list_no_shell(monkeypatch, fake_sim, builtin_spec, tmp_path):
    seen = {}

    def cap(argv, **k):
        seen.update(argv=argv, **k)
        return subprocess.CompletedProcess(argv, 0, "ok", "")
    _patch(monkeypatch, cap)
    fake_sim.run(builtin_spec, tmp_path / "r")
    assert isinstance(seen["argv"], list) and seen["shell"] is False and seen["timeout"] == 300.0
