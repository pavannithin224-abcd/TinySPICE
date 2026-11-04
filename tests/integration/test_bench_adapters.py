"""Adapter MECHANICS for TinySPICEBench (oracle parser, real ngspice): the configurations behave as defined in docs/BENCH_PREREG.md.
These check the definitions, not the benchmark outcome (that is the frozen run)."""
import json
from pathlib import Path

import pytest

from tinyspice.benchmark.baselines import run_config_a, run_config_b
from tinyspice.benchmark.bench import full_raw, load_tasks, oracle_provider, run_config_c
from tinyspice.benchmark.scoring import score
from tinyspice.simulator import find_tools

TOOLS = find_tools()
pytestmark = pytest.mark.ngspice
needs_all = pytest.mark.skipif(
    TOOLS.ngspice_exe is None or TOOLS.sky130_root is None
    or not (TOOLS.sky130_root / "cells/nfet_01v8/sky130_fd_pr__nfet_01v8__tt.pm3.spice").exists(), reason="ngspice + SKY130 not installed")
TASKS = {t["id"]: t for t in load_tasks()}


def texts(t):
    return [json.dumps(full_raw(t["gold_raw"]))]


def all_three(tid, limits, tmp_path):
    t = TASKS[tid]
    a = run_config_a(t, texts(t), tmp_path / "A")
    b = run_config_b(t, oracle_provider(t), limits, tmp_path / "B")
    c = run_config_c(t, oracle_provider(t), limits, tmp_path / "C")
    sc = {o.config: score(t, o, limits, tmp_path / "work") for o in (a, b, c)}
    return {"A": a, "B": b, "C": c}, sc


@needs_all
def test_valid_request_all_three_reach_a_true_success(limits, tmp_path):
    out, sc = all_three("T01", limits, tmp_path)
    assert {k: v.status for k, v in out.items()} == {"A": "successful", "B": "successful", "C": "successful"}
    assert all(s["truth_achieved"] and not s["false_success"] for s in sc.values()), sc


@needs_all
def test_missing_parameter_a_invents_it_b_and_c_refuse(limits, tmp_path):
    out, sc = all_three("T02", limits, tmp_path)
    assert out["A"].status == "successful" and out["A"].spec["length_um"] == 0.18          # the invented default
    assert sc["A"]["false_success"] and sc["A"]["invented"]
    assert out["B"].status == out["C"].status == "rejected_invalid_input"
    assert not sc["B"]["false_success"] and not sc["C"]["false_success"] and sc["C"]["completion"]


@needs_all
def test_physically_invalid_temperature_only_the_planner_refuses(limits, tmp_path):
    out, sc = all_three("T10", limits, tmp_path)
    assert out["A"].status == "successful" and out["A"].spec["temperature_c"] == 300.0     # ngspice happily simulates 300 C
    assert sc["A"]["false_success"]
    assert out["B"].status == out["C"].status == "rejected_invalid_input"


@needs_all
def test_stated_time_limit_is_ignored_by_a_enforced_by_c(limits, tmp_path):
    out, sc = all_three("T22", limits, tmp_path)
    assert out["A"].status == "successful" and sc["A"]["budget_violation"] and sc["A"]["false_success"]
    assert out["C"].status == "stopped_budget_limit" and sc["C"]["completion"] and not sc["C"]["false_success"]
    assert out["B"].status != "successful"                                                 # per-process timeout kills the run


@needs_all
def test_partial_result_is_reported_as_success_by_a_only(limits, tmp_path):
    out, sc = all_three("T15", limits, tmp_path)
    assert out["A"].status == "successful" and not out["A"].values["VTH"]["ok"] and sc["A"]["false_success"]
    assert out["B"].status == out["C"].status == "partially_completed"


@needs_all
def test_recoverable_fault_only_c_recovers(limits, tmp_path):
    out, sc = all_three("T19", limits, tmp_path)
    assert out["A"].status == "failed" and out["B"].status == "failed"
    assert out["C"].status == "recovered_after_failure" and sc["C"]["completion"] and sc["C"]["truth_achieved"]


@needs_all
def test_point_limit_a_overruns_b_and_c_stop(limits, tmp_path):
    out, sc = all_three("T09", limits, tmp_path)
    assert out["A"].points == 181 and sc["A"]["budget_violation"] and sc["A"]["false_success"]
    assert out["B"].status == out["C"].status == "stopped_budget_limit"
