import json

import numpy as np
import pytest

from tinyspice.executor import execute
from tinyspice.schemas import ExperimentSpec, ExperimentStatus, load_device_limits
from tinyspice.simulator import MockSimulator, NgspiceSimulator, build_netlist, find_tools, get_profile

TOOLS = find_tools()


@pytest.fixture
def blimits(limits):
    from conftest import ROOT
    return load_device_limits(ROOT / "configs/devices/builtin_level1_nmos.json")


@pytest.fixture
def bspec(spec_dict):
    return ExperimentSpec.model_validate({**spec_dict, "model_name": "builtin_level1_nmos"})


def test_netlist_carries_explicit_solver_floor(bspec):
    n = build_netlist(bspec, get_profile("builtin_level1_nmos", TOOLS))
    assert ".option gmin=1e-18 abstol=1e-18" in n  # regression: default gmin put a 1.8 pA floor under IOFF


def test_executor_valid_sim_is_partial_never_successful(bspec, blimits, tmp_path):
    rec = execute(bspec, blimits, MockSimulator(), tmp_path)
    assert rec.status is ExperimentStatus.PARTIAL and "Stage 2" in rec.message
    for f in ("spec.json", "plan.json", "result.json"):
        assert (rec.run_dir / f).exists()
    assert json.loads((rec.run_dir / "result.json").read_text())["points"] == 91


def test_executor_sim_failure_is_failed(bspec, blimits, tmp_path):
    rec = execute(bspec, blimits, MockSimulator(fault="nonconvergence"), tmp_path)
    assert rec.status is ExperimentStatus.FAILED and rec.error_code == "NONCONVERGENCE"


def test_executor_budget_stop_creates_no_run_dir(spec_dict, blimits, tmp_path):
    s = ExperimentSpec.model_validate({**spec_dict, "model_name": "builtin_level1_nmos", "budget": {"max_points": 10}})
    rec = execute(s, blimits, MockSimulator(), tmp_path)
    assert rec.status is ExperimentStatus.STOPPED_BUDGET and rec.error_code == "BUDGET_EXCEEDED_POINTS"
    assert list(tmp_path.iterdir()) == []


def test_executor_invalid_geometry_is_rejected(spec_dict, blimits, tmp_path):
    s = ExperimentSpec.model_validate({**spec_dict, "model_name": "builtin_level1_nmos", "length_um": 0.05})
    rec = execute(s, blimits, MockSimulator(), tmp_path)
    assert rec.status is ExperimentStatus.REJECTED_INVALID and rec.sim is None


def test_executor_runs_never_collide(bspec, blimits, tmp_path):
    a = execute(bspec, blimits, MockSimulator(), tmp_path)
    b = execute(bspec, blimits, MockSimulator(), tmp_path)
    assert a.run_id != b.run_id and len(list(tmp_path.iterdir())) == 2


@pytest.mark.ngspice
@pytest.mark.skipif(TOOLS.ngspice_exe is None, reason="ngspice not installed")
def test_executor_real_ngspice_end_to_end(bspec, blimits, tmp_path):
    rec = execute(bspec, blimits, NgspiceSimulator(), tmp_path)
    assert rec.status is ExperimentStatus.PARTIAL, (rec.status, rec.message)
    assert rec.sim.simulator_version == "ngspice-47" and (rec.run_dir / "sim" / "netlist.cir").exists()
