"""Provenance store: SQLite (WAL, append-only via triggers, parameterised SQL only) + a per-run folder with a sha256 manifest.

Nothing here ever UPDATEs or DELETEs a recorded row; run ids are unique and run folders are never overwritten.
"""
from __future__ import annotations

import datetime as dt
import hashlib
import json
import sqlite3
import subprocess
from pathlib import Path

MANIFEST_NAME = "manifest.json"

SCHEMA = """
CREATE TABLE IF NOT EXISTS runs(
  run_id TEXT PRIMARY KEY, created_utc TEXT NOT NULL, spec_sha256 TEXT NOT NULL, status TEXT NOT NULL, message TEXT,
  strategy TEXT, retries_used INTEGER, tool_calls INTEGER, points INTEGER, wallclock_s REAL, budget_json TEXT,
  recovery_chain_json TEXT, code_git_commit TEXT, code_dirty INTEGER, ngspice_version TEXT, model_files_json TEXT,
  llm_json TEXT, run_dir TEXT, manifest_sha256 TEXT, injected_json TEXT);
CREATE TABLE IF NOT EXISTS events(run_id TEXT NOT NULL, seq INTEGER NOT NULL, kind TEXT NOT NULL, json TEXT NOT NULL, PRIMARY KEY(run_id, seq));
CREATE TABLE IF NOT EXISTS measurements(run_id TEXT NOT NULL, name TEXT NOT NULL, ok INTEGER NOT NULL, value REAL, unit TEXT,
  error_code TEXT, flags_json TEXT, diagnostics_json TEXT, PRIMARY KEY(run_id, name));
CREATE TABLE IF NOT EXISTS defaults(run_id TEXT NOT NULL, field TEXT NOT NULL, value TEXT, reason TEXT, PRIMARY KEY(run_id, field));
CREATE TABLE IF NOT EXISTS artefacts(run_id TEXT NOT NULL, relpath TEXT NOT NULL, sha256 TEXT NOT NULL, bytes INTEGER NOT NULL, PRIMARY KEY(run_id, relpath));
"""
TABLES = ("runs", "events", "measurements", "defaults", "artefacts")


def sha256_file(p: Path) -> str:
    h = hashlib.sha256()
    with open(p, "rb") as f:
        for chunk in iter(lambda: f.read(1 << 20), b""):
            h.update(chunk)
    return h.hexdigest()


def build_manifest(run_dir: Path) -> dict:
    run_dir = Path(run_dir)
    out = {}
    for p in sorted(run_dir.rglob("*")):
        if p.is_file() and p.name != MANIFEST_NAME:
            out[p.relative_to(run_dir).as_posix()] = {"sha256": sha256_file(p), "bytes": p.stat().st_size}
    return out


def write_manifest(run_dir: Path) -> tuple[dict, str]:
    man = build_manifest(run_dir)
    path = Path(run_dir) / MANIFEST_NAME
    path.write_text(json.dumps(man, indent=1, sort_keys=True), encoding="utf-8", newline="\n")
    return man, sha256_file(path)


def git_state(repo: Path) -> tuple[str | None, bool | None]:
    try:
        head = subprocess.run(["git", "-C", str(repo), "rev-parse", "HEAD"], capture_output=True, text=True, timeout=10, shell=False)
        dirty = subprocess.run(["git", "-C", str(repo), "status", "--porcelain", "--untracked-files=no"], capture_output=True, text=True, timeout=10, shell=False)
        if head.returncode != 0:
            return None, None
        return head.stdout.strip(), bool(dirty.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        return None, None


class ProvenanceStore:
    def __init__(self, db_path: Path):
        self.path = Path(db_path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self.con = sqlite3.connect(self.path)
        self.con.execute("PRAGMA journal_mode=WAL")
        self.con.executescript(SCHEMA)
        for t in TABLES:                       # append-only: accidents (and bugs) cannot rewrite history
            for op in ("UPDATE", "DELETE"):
                self.con.execute(f"CREATE TRIGGER IF NOT EXISTS {t}_no_{op.lower()} BEFORE {op} ON {t} "
                                 f"BEGIN SELECT RAISE(ABORT, 'provenance is append-only'); END")
        self.con.commit()

    def close(self) -> None:
        self.con.close()

    def record_run(self, run: dict, events: list[dict], measurements: dict, defaults: list[tuple], artefacts: dict) -> None:
        """One transaction: either the whole record exists or none of it does."""
        c = self.con
        with c:
            c.execute("INSERT INTO runs VALUES(:run_id,:created_utc,:spec_sha256,:status,:message,:strategy,:retries_used,:tool_calls,"
                      ":points,:wallclock_s,:budget_json,:recovery_chain_json,:code_git_commit,:code_dirty,:ngspice_version,"
                      ":model_files_json,:llm_json,:run_dir,:manifest_sha256,:injected_json)", run)
            for i, e in enumerate(events):
                c.execute("INSERT INTO events VALUES(?,?,?,?)", (run["run_id"], i, e["kind"], json.dumps(e, sort_keys=True)))
            for name, m in measurements.items():
                c.execute("INSERT INTO measurements VALUES(?,?,?,?,?,?,?,?)",
                          (run["run_id"], name, int(m["ok"]), m.get("value"), m.get("unit"), m.get("error_code"),
                           json.dumps(m.get("flags", [])), json.dumps(m.get("diagnostics", {}), default=str)))
            for f, v, why in defaults:
                c.execute("INSERT INTO defaults VALUES(?,?,?,?)", (run["run_id"], f, json.dumps(v, default=str), why))
            for rel, d in artefacts.items():
                c.execute("INSERT INTO artefacts VALUES(?,?,?,?)", (run["run_id"], rel, d["sha256"], d["bytes"]))

    def run(self, run_id: str) -> dict | None:
        cur = self.con.execute("SELECT * FROM runs WHERE run_id=?", (run_id,))
        row = cur.fetchone()
        return dict(zip([d[0] for d in cur.description], row)) if row else None

    def events(self, run_id: str) -> list[dict]:
        return [json.loads(r[0]) for r in self.con.execute("SELECT json FROM events WHERE run_id=? ORDER BY seq", (run_id,))]

    def measurements(self, run_id: str) -> dict:
        out = {}
        for name, ok, value, unit, code, flags, diag in self.con.execute(
                "SELECT name, ok, value, unit, error_code, flags_json, diagnostics_json FROM measurements WHERE run_id=?", (run_id,)):
            out[name] = {"ok": bool(ok), "value": value, "unit": unit, "error_code": code, "flags": json.loads(flags), "diagnostics": json.loads(diag)}
        return out

    def artefacts(self, run_id: str) -> dict:
        return {r[0]: {"sha256": r[1], "bytes": r[2]} for r in self.con.execute("SELECT relpath, sha256, bytes FROM artefacts WHERE run_id=?", (run_id,))}

    def defaults(self, run_id: str) -> dict:
        return {r[0]: (json.loads(r[1]), r[2]) for r in self.con.execute("SELECT field, value, reason FROM defaults WHERE run_id=?", (run_id,))}

    def run_ids(self) -> list[str]:
        return [r[0] for r in self.con.execute("SELECT run_id FROM runs ORDER BY created_utc")]


def verify_run(store: ProvenanceStore, run_id: str) -> dict:
    """Tamper evidence: every recorded artefact must exist with its recorded hash, and manifest.json must match the DB."""
    rec = store.run(run_id)
    if rec is None:
        return {"ok": False, "problems": [f"unknown run {run_id}"]}
    run_dir = Path(rec["run_dir"])
    problems = []
    if not run_dir.exists():
        return {"ok": False, "problems": [f"run folder missing: {run_dir}"]}
    for rel, d in store.artefacts(run_id).items():
        p = run_dir / rel
        if not p.exists():
            problems.append(f"missing: {rel}")
        elif sha256_file(p) != d["sha256"]:
            problems.append(f"changed: {rel}")
    mp = run_dir / MANIFEST_NAME
    if not mp.exists():
        problems.append(f"missing: {MANIFEST_NAME}")
    elif sha256_file(mp) != rec["manifest_sha256"]:
        problems.append(f"changed: {MANIFEST_NAME}")
    return {"ok": not problems, "problems": problems}


def utc_now() -> str:
    return dt.datetime.now(dt.timezone.utc).strftime("%Y-%m-%dT%H:%M:%S.%fZ")
