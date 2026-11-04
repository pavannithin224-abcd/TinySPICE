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
    assert 0 < r.y[0] < 1e-9        # off-state leakage is tiny but positive
    assert 1e-4 < r.y[-1] < 2e-3    # plausibility only: ~hundreds of uA for W=1um at 1.8 V
    assert (np.diff(r.y) > 0).all()  # strictly increasing with VGS at VDS=1.8


@needs_ngspice
def test_bad_model_include_is_reported_not_hidden(spec_dict, tmp_path):
    from tinyspice.simulator import models as M
    prof = M.get_profile("builtin_level1_nmos", TOOLS)
    bad = M.ModelProfile(**{**prof.__dict__, "preamble": ('.include "C:/definitely/not/here.spice"', *prof.preamble)})
    r = NgspiceSimulator().run(mk(spec_dict, model_name="builtin_level1_nmos"), tmp_path / "run", profile=bad)
    assert not r.ok and r.error_code == "MISSING_INCLUDE"
