import json
from pathlib import Path

from tinyspice.cli import main

ROOT = Path(__file__).resolve().parents[2]
SPEC = str(ROOT / "configs" / "experiments" / "example_idvg.json")


def cli(tmp_path, *args):
    return main(["--db", str(tmp_path / "p.sqlite"), "--runs", str(tmp_path / "runs"), "--simulator", "mock", *args])


def test_plan_is_a_dry_run_that_spends_nothing(tmp_path, capsys):
    assert cli(tmp_path, "plan", SPEC) == 0
    out = capsys.readouterr().out
    assert '"strategy": "uniform"' in out and "dry run" in out
    assert not (tmp_path / "runs").exists() and not (tmp_path / "p.sqlite").exists()


def test_plan_rejects_a_bad_spec_with_exit_1(tmp_path, capsys):
    bad = tmp_path / "bad.json"
    d = json.loads(Path(SPEC).read_text())
    d["width_um"] = 500.0
    bad.write_text(json.dumps(d))
    assert cli(tmp_path, "plan", str(bad)) == 1
    assert "GEOMETRY_OUT_OF_RANGE" in capsys.readouterr().out


def test_run_verify_replay_roundtrip_with_mock(tmp_path, capsys):
    assert cli(tmp_path, "run", SPEC) in (0, 2)
    out = capsys.readouterr().out
    assert "status" in out and "budget" in out
    assert cli(tmp_path, "runs") == 0
    rid = capsys.readouterr().out.split()[0]
    assert cli(tmp_path, "verify", rid) == 0
    assert "VERIFIED" in capsys.readouterr().out
    assert cli(tmp_path, "replay", rid) == 0
    assert '"matched": true' in capsys.readouterr().out


def test_verify_exit_code_flags_tampering(tmp_path, capsys):
    cli(tmp_path, "run", SPEC)
    capsys.readouterr()
    cli(tmp_path, "runs")
    rid = capsys.readouterr().out.split()[0]
    (next((tmp_path / "runs" / rid).rglob("spec.json"))).write_text("{}")
    assert cli(tmp_path, "verify", rid) == 1
    assert "changed" in capsys.readouterr().out


REQ_OK = ROOT / "examples" / "requests" / "idvg_complete.txt"
REQ_INCOMPLETE = ROOT / "examples" / "requests" / "idvg_example.txt"


def test_ask_runs_a_complete_request_end_to_end_on_the_mock(tmp_path, capsys):
    code = cli(tmp_path, "ask", f"file:{REQ_OK}")
    out = capsys.readouterr().out
    assert code in (0, 2) and "understood request" in out and "status   :" in out and "run_id" in out


def test_ask_rejects_an_incomplete_request_without_spending_anything(tmp_path, capsys):
    code = cli(tmp_path, "ask", f"file:{REQ_INCOMPLETE}")
    out = capsys.readouterr().out
    assert code == 1 and "rejected_invalid_input" in out and "no budget was spent" in out
    assert not (tmp_path / "runs").exists()


def test_ask_dry_run_prints_the_understood_spec_only(tmp_path, capsys):
    assert cli(tmp_path, "ask", f"file:{REQ_OK}", "--dry-run") == 0
    out = capsys.readouterr().out
    assert "understood request" in out and "run_id" not in out and not (tmp_path / "runs").exists()


def test_ask_accepts_the_request_text_inline(tmp_path, capsys):
    assert cli(tmp_path, "ask", "Run a MOSFET simulation with some reasonable settings.") == 1
    assert "rejected_invalid_input" in capsys.readouterr().out
