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
