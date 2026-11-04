import itertools

import pytest

from tinyspice.budget import BudgetExceeded, BudgetLedger
from tinyspice.recovery import SOLVER_LADDER, classify, solver_options_line, validate_solver_overrides
from tinyspice.schemas.status import ExperimentStatus as S
from tinyspice.status import check_evidence, final_status


class FakeClock:
    def __init__(self):
        self.t = 0.0

    def __call__(self):
        return self.t


def ledger(**kw):
    c = FakeClock()
    d = dict(max_points=40, max_runtime_s=10.0, max_tool_calls=10, max_retries=2)
    d.update(kw)
    return BudgetLedger(clock=c, **d), c


# ---------------- budget ----------------
def test_tool_calls_reserve_one_for_persistence_and_never_exceed():
    L, _ = ledger(max_tool_calls=5)
    L.charge_calls(2)
    L.charge_calls(2)                              # 4 = 5 - 1 reserved
    with pytest.raises(BudgetExceeded) as e:
        L.charge_calls(2)
    assert e.value.dimension == "tool_calls" and L.tool_calls == 4
    L.charge_persist()                             # reserved slot is always available
    assert L.tool_calls == 5 and L.within_limits()


def test_retry_limit_is_enforced_before_the_extra_retry():
    L, _ = ledger(max_retries=2)
    L.charge_retry(); L.charge_retry()
    with pytest.raises(BudgetExceeded) as e:
        L.charge_retry()
    assert e.value.dimension == "retries" and L.retries == 2


def test_point_limit_is_on_the_final_dataset():
    L, _ = ledger(max_points=40)
    L.set_points(40)
    assert L.points_left() == 0
    with pytest.raises(BudgetExceeded):
        L.set_points(41)
    assert L.points == 40


def test_wallclock_is_a_total_deadline_and_timeouts_grow_but_never_pass_it():
    L, c = ledger(max_runtime_s=10.0)
    t1 = L.attempt_timeout(None)
    assert t1 == pytest.approx(4.0)                # 0.4 x total
    c.t = 4.0
    t2 = L.attempt_timeout(t1)
    assert t2 == pytest.approx(5.8)                # min(remaining 6 - margin 0.2, 8)
    c.t = 10.0
    with pytest.raises(BudgetExceeded) as e:
        L.attempt_timeout(t2)
    assert e.value.dimension == "runtime"


def test_no_process_may_start_inside_the_safety_margin():
    L, c = ledger(max_runtime_s=0.3)
    assert L.margin_s == pytest.approx(0.1)
    assert L.attempt_timeout(None) == pytest.approx(0.12)          # min(0.3-0.1, 0.4*0.3)
    c.t = 0.25                                                      # 0.05 s left < 0.1 s margin
    with pytest.raises(BudgetExceeded) as e:
        L.attempt_timeout(0.12)
    assert e.value.dimension == "runtime"


def test_snapshot_reports_all_dimensions():
    L, _ = ledger()
    assert set(L.snapshot()) == {"tool_calls", "retries", "points", "wallclock_s"}


# ---------------- recovery catalog ----------------
def test_catalog_classification():
    for c in ("MISSING_INCLUDE", "MODEL_NOT_FOUND", "NETLIST_SYNTAX"):
        r = classify(c)
        assert r.recognised and not r.recoverable
    for c in ("TIMEOUT", "ROW_COUNT_MISMATCH", "NO_OUTPUT", "NONFINITE_VALUES", "NONCONVERGENCE"):
        r = classify(c)
        assert r.recognised and r.recoverable
    u = classify("WEIRD_FAULT")
    assert not u.recognised and not u.recoverable
    assert not classify(None).recognised


def test_solver_ladder_never_touches_gmin_or_abstol():
    for step in SOLVER_LADDER:
        assert not ({"gmin", "abstol", "reltol"} & set(step))
        validate_solver_overrides(step)
    for bad in ({"gmin": 1e-12}, {"abstol": 1e-9}, {"reltol": 0.1}, {"itl1": 0}, {"itl1": 1.5}, {"method": "euler"}):
        with pytest.raises(ValueError):
            validate_solver_overrides(bad)


def test_solver_options_line():
    assert solver_options_line(None) is None and solver_options_line({}) is None
    assert solver_options_line({"itl2": 200, "itl1": 400}) == ".options itl1=400 itl2=200"
    assert "method=gear" in solver_options_line(SOLVER_LADDER[1])


# ---------------- status machine ----------------
def build(rej, stop, out, meas, rec, fault):
    ev = []
    if fault:
        ev.append({"kind": "fault", "code": "X", "recognised": True, "recoverable": True})
    if rec:
        ev.append({"kind": "recovery", "label": "L"})
    if out:
        ev.append({"kind": "output_ok"})
    if meas == "all":
        ev.append({"kind": "measurements", "ok": ["A", "B"], "refused": {}})
    elif meas == "some":
        ev.append({"kind": "measurements", "ok": ["A"], "refused": {"B": "E"}})
    elif meas == "none":
        ev.append({"kind": "measurements", "ok": [], "refused": {"A": "E", "B": "E"}})
    if stop:
        ev.append({"kind": "stop", "reason": stop})
    if rej:
        ev.append({"kind": "rejected", "status": rej})
    return ev


def test_truth_table_every_status_is_justified_by_its_evidence():
    seen = set()
    for rej, stop, out, meas, rec, fault in itertools.product(
            [None, "rejected_invalid_input", "stopped_budget_limit"], [None, "budget", "unrecoverable", "unrecognised", "ladder_exhausted"],
            [False, True], [None, "all", "some", "none"], [False, True], [False, True]):
        ev = build(rej, stop, out, meas, rec, fault)
        st = final_status(ev)
        assert check_evidence(st, ev) == [], (st, ev)
        seen.add(st)
    assert seen == set(S)                          # all six states are reachable


@pytest.mark.parametrize("ev,expected", [
    (build(None, None, True, "all", False, False), S.SUCCESSFUL),
    (build(None, None, True, "all", True, True), S.RECOVERED),
    (build(None, None, True, "some", False, False), S.PARTIAL),
    (build(None, None, True, "some", True, True), S.PARTIAL),         # recovery happened but a measurement still refused
    (build(None, None, True, "none", False, False), S.FAILED),
    (build(None, None, True, None, False, False), S.PARTIAL),         # validated, nothing extracted: never SUCCESSFUL
    (build(None, None, True, "all", False, True), S.FAILED),          # an unaccounted fault can never end as success
    (build(None, None, False, None, False, True), S.FAILED),
    (build(None, "budget", False, None, True, True), S.STOPPED_BUDGET),
    (build(None, "unrecoverable", False, None, False, True), S.FAILED),
    (build(None, "ladder_exhausted", False, None, True, True), S.FAILED),
    (build("rejected_invalid_input", None, False, None, False, False), S.REJECTED_INVALID),
    (build("stopped_budget_limit", None, False, None, False, False), S.STOPPED_BUDGET),
])
def test_known_outcomes(ev, expected):
    assert final_status(ev) == expected


def test_success_is_impossible_with_an_unhandled_fault_or_refused_measurement():
    ev = build(None, None, True, "all", False, True)       # a fault with no recovery event but a 'successful' log
    assert check_evidence(S.SUCCESSFUL, ev) != []          # the evidence checker refuses to bless it
    assert check_evidence(S.SUCCESSFUL, build(None, None, True, "some", False, False)) != []
