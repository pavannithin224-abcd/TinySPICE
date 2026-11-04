"""Status machine. `final_status` is a PURE function of the event log, and `check_evidence` re-derives the evidence every
status requires, so a state can never be emitted without its proof.

Event kinds (dicts with "kind"):
  rejected      {"status": "rejected_invalid_input" | "stopped_budget_limit"}  planner refused; simulator never called
  fault         {"code", "recognised", "recoverable"}
  recovery      {"label"}                       a recovery action was taken
  stop          {"reason": "budget" | "unrecoverable" | "unrecognised" | "ladder_exhausted", "dimension"?}
  output_ok     {}                              simulator output passed validation
  measurements  {"ok": [names], "refused": {name: code}}   (latest one wins)
"""
from __future__ import annotations

from tinyspice.schemas.status import ExperimentStatus as S


def _last(events, kind):
    for e in reversed(events):
        if e["kind"] == kind:
            return e
    return None


def final_status(events: list[dict]) -> S:
    rej = _last(events, "rejected")
    if rej:
        return S(rej["status"])
    stop = _last(events, "stop")
    if stop:
        return S.STOPPED_BUDGET if stop["reason"] == "budget" else S.FAILED
    if not _last(events, "output_ok"):
        return S.FAILED
    if _last(events, "fault") and not _last(events, "recovery"):
        return S.FAILED                        # a fault nobody accounted for can never end as success
    m = _last(events, "measurements")
    if m is None:
        return S.PARTIAL                       # validated output but nothing extracted: never SUCCESSFUL
    if not m["ok"]:
        return S.FAILED
    if m["refused"]:
        return S.PARTIAL
    return S.RECOVERED if any(e["kind"] == "recovery" for e in events) else S.SUCCESSFUL


def check_evidence(status: S, events: list[dict]) -> list[str]:
    """Return the list of violated evidence requirements (empty = the status is justified by the log)."""
    bad = []
    has = lambda k: any(e["kind"] == k for e in events)  # noqa: E731
    m = _last(events, "measurements")
    if status in (S.SUCCESSFUL, S.RECOVERED):
        if not has("output_ok"):
            bad.append("no validated output")
        if m is None or m["refused"] or not m["ok"]:
            bad.append("not every requested measurement succeeded")
        if has("stop") or has("rejected"):
            bad.append("run was stopped/rejected")
    if status is S.SUCCESSFUL and has("recovery"):
        bad.append("SUCCESSFUL but a recovery occurred")
    if status is S.SUCCESSFUL and has("fault"):
        bad.append("SUCCESSFUL but a fault occurred")
    if status is S.RECOVERED and not has("recovery"):
        bad.append("RECOVERED without a recovery event")
    if status is S.PARTIAL and (not has("output_ok") or m is not None and (not m["refused"] or not m["ok"])):
        bad.append("PARTIAL needs validated output with some measurements ok and some refused (or none extracted)")
    if status is S.STOPPED_BUDGET and not (has("rejected") or any(e["kind"] == "stop" and e["reason"] == "budget" for e in events)):
        bad.append("STOPPED_BUDGET without a budget stop")
    if status is S.REJECTED_INVALID and not has("rejected"):
        bad.append("REJECTED without a rejection")
    return bad
