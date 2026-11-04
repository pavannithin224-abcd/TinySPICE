"""Stage-5 failure-injection suite (E4) + replay/verify (E5). Cases and expected statuses come from the PRE-REGISTERED file
tests/benchmark/stage5_injection_expected.json (committed before any Stage-5 code). Real ngspice, real runner, real SQLite store."""
import json
import shutil
from pathlib import Path

import pytest

from tinyspice.provenance import ProvenanceStore, verify_run
from tinyspice.recovery.injection import InjectingSimulator
from tinyspice.replay import replay
from tinyspice.runner import run_experiment
from tinyspice.schemas import ExperimentSpec, ExperimentStatus
from tinyspice.simulator import NgspiceSimulator, find_tools
from tinyspice.status import check_evidence

TOOLS = find_tools()
pytestmark = pytest.mark.ngspice
needs_all = pytest.mark.skipif(
    TOOLS.ngspice_exe is None or TOOLS.sky130_root is None
    or not (TOOLS.sky130_root / "cells/nfet_01v8/sky130_fd_pr__nfet_01v8__tt.pm3.spice").exists(),
    reason="ngspice + SKY130 not installed (scripts/setup_tools.py)")

EXPECTED = json.loads((Path(__file__).resolve().parents[1] / "benchmark" / "stage5_injection_expected.json").read_text(encoding="utf-8"))
CASES = EXPECTED["cases"]


def build_spec(case) -> ExperimentSpec:
    d = {"device_type": "nmos", "model_name": "sky130_fd_pr__nfet_01v8", "width_um": 1.0, "length_um": 0.18, "temperature_c": 27.0,
         "analysis": "idvg", "vds_v": 1.8, "measurements": ["VTH", "SS", "GM", "ION", "IOFF"], "ion_vgs_v": 1.8, "ioff_vgs_v": 0.0}
    stop = 1.8
    for k, v in (case.get("spec") or {}).items():
        if k == "sweep_stop":
            stop = v
        elif v is None:
            d.pop(k, None)
        else:
            d[k] = v
    d["sweep"] = {"start": 0.0, "stop": stop, "points": case["N"]}
    d["budget"] = {"max_points": case["max_points"], **(case.get("budget") or {})}
    return ExperimentSpec.model_validate(d)


def run_case(case, limits, tmp_path, store):
    sim = NgspiceSimulator()
    inj = case.get("inject")
    if inj:
        sim = InjectingSimulator(sim, inj["type"], inj["mode"])
    return run_experiment(build_spec(case), limits, sim, tmp_path / "runs", strategy=case.get("strategy", "uniform"), store=store,
                          injected=inj)


@needs_all
@pytest.mark.parametrize("case", CASES, ids=[c["id"] for c in CASES])
def test_pre_registered_expected_status(case, limits, tmp_path):
    store = ProvenanceStore(tmp_path / "prov.sqlite")
    r = run_case(case, limits, tmp_path, store)
    exp = case["expect"]
    assert r.status.value == exp["status"], (case["id"], case["name"], r.status.value, r.message, r.events[-3:])
    if "retries_used" in exp:
        assert r.retries_used == exp["retries_used"], (case["id"], r.retries_used, r.recovery_chain)
    if "recovery_chain" in exp:
        assert r.recovery_chain == exp["recovery_chain"], (case["id"], r.recovery_chain)
    # ---- invariants that must hold for EVERY case ----
    b = r.budget
    assert all(v["used"] <= v["limit"] for v in b.values()), (case["id"], b)                  # no budget is ever exceeded
    assert check_evidence(r.status, r.events) == []                                           # no state without its evidence
    if case.get("inject"):
        assert r.status is not ExperimentStatus.SUCCESSFUL, "SUCCESSFUL on an injected fault"
    assert verify_run(store, r.run_id)["ok"], verify_run(store, r.run_id)                     # provenance recorded and intact
    assert store.run(r.run_id)["status"] == r.status.value and len(store.events(r.run_id)) == len(r.events)
    # ---- case-specific facts ----
    if case["id"] == "I05":
        assert any(f.startswith("SOLVER_OVERRIDE") for f in r.flags)
    if case["id"] == "I14":
        assert r.n_points <= case["max_points"] and all(m.ok for m in r.measurements.values()), (r.n_points, r.message)
    if case["id"] == "I15":
        assert r.n_points == case["N"] == 16 and r.measurements["SS"].ok is False
    if case["id"] in ("I17", "I18"):
        assert not any(e["kind"] == "output_ok" for e in r.events)                            # simulator never reached
    store.close()


@needs_all
def test_replay_reproduces_and_verify_detects_tampering(limits, tmp_path):
    store = ProvenanceStore(tmp_path / "prov.sqlite")
    base = next(c for c in CASES if c["id"] == "I01")
    r1 = run_case(base, limits, tmp_path, store)
    assert r1.status is ExperimentStatus.SUCCESSFUL
    # R04 verify passes on an untouched run
    assert verify_run(store, r1.run_id)["ok"]
    # R01 replay reproduces every measurement within rtol 1e-6, and the replay is itself a recorded run
    rp = replay(store, r1.run_id, NgspiceSimulator(), limits, tmp_path / "replays", rtol=1e-6)
    assert rp["matched"], rp
    assert store.run(rp["new_run_id"])["replay_of"] == r1.run_id
    # R02 an edited netlist is detected and named
    net = next(Path(r1.run_dir).rglob("netlist.cir"))
    original = net.read_text(encoding="utf-8")
    net.write_text(original + "* tampered\n", encoding="utf-8")
    v = verify_run(store, r1.run_id)
    assert not v["ok"] and any("netlist.cir" in p for p in v["problems"]), v
    net.write_text(original, encoding="utf-8", newline="\n")
    assert verify_run(store, r1.run_id)["ok"]                                                # restoring the bytes restores integrity
    # R03 a deleted artefact is detected
    victim = Path(r1.run_dir) / "measurements.json"
    backup = tmp_path / "m.bak"
    shutil.copy(victim, backup)
    victim.unlink()
    assert not verify_run(store, r1.run_id)["ok"]
    shutil.copy(backup, victim)
    store.close()


@needs_all
def test_store_is_append_only(limits, tmp_path):
    import sqlite3
    store = ProvenanceStore(tmp_path / "prov.sqlite")
    r = run_case(next(c for c in CASES if c["id"] == "I01"), limits, tmp_path, store)
    for sql in ("UPDATE runs SET status='successful' WHERE run_id=?", "DELETE FROM runs WHERE run_id=?",
                "DELETE FROM events WHERE run_id=?", "UPDATE measurements SET value=0 WHERE run_id=?"):
        with pytest.raises(sqlite3.DatabaseError):
            store.con.execute(sql, (r.run_id,))
    store.close()
