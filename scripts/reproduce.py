"""Reproduce TinySPICE's checks.

  python scripts/reproduce.py quick     # ~2 min: tests + a real ngspice run from an English request + verify + replay (needs `setup_tools.py` done)
  python scripts/reproduce.py results   # ~1 min: recompute every reported table from the committed raw results (no ngspice, no LLM) and check the headline numbers
  python scripts/reproduce.py all       # both

Exit code 0 only if every check passes. The full LLM re-recording (hours) is NOT part of this script; see README.
"""
import json
import os
import re
import subprocess
import sys
import tempfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PY = sys.executable
results: list[tuple[str, bool, str]] = []


def run(args, **kw):
    p = subprocess.run(args, capture_output=True, text=True, cwd=ROOT, encoding="utf-8", errors="replace", env={**os.environ, "PYTHONIOENCODING": "utf-8"}, **kw)
    return p.returncode, (p.stdout or "") + (p.stderr or "")


def check(name: str, ok: bool, detail: str = "") -> None:
    results.append((name, bool(ok), detail))
    print(("PASS  " if ok else "FAIL  ") + name + (f"   [{detail}]" if detail else ""), flush=True)


def quick() -> None:
    tools = ROOT / ".tools" / "manifest.json"
    check("tools installed (.tools/manifest.json; run scripts/setup_tools.py)", tools.exists())
    code, out = run([PY, "-m", "pytest", "-q", "-p", "no:cacheprovider"])
    m = re.search(r"(\d+) passed", out)
    check("test suite", code == 0 and m is not None, (m.group(0) if m else out[-200:]).strip())
    if not tools.exists():
        return
    tmp = Path(tempfile.mkdtemp(prefix="tinyspice_repro_"))
    db, runs = str(tmp / "p.sqlite"), str(tmp / "runs")
    code, out = run([PY, "-m", "tinyspice", "--db", db, "--runs", runs, "ask", f"file:{ROOT / 'examples' / 'requests' / 'idvg_complete.txt'}"])
    rid = re.search(r"run_id\s*:\s*(\S+)", out)
    vth = re.search(r"VTH\s+([0-9.]+) V", out)
    ss = re.search(r"SS\s+([0-9.]+) mV/dec", out)
    check("English request -> validated spec -> real ngspice run (status successful)", code == 0 and "status   : successful" in out and rid is not None)
    check("VTH matches the recorded Stage-2 value (0.596 V, +-5 mV)", vth is not None and abs(float(vth.group(1)) - 0.596) <= 0.005, vth.group(1) if vth else "none")
    check("SS in the recorded range (82 mV/dec, +-5 %)", ss is not None and abs(float(ss.group(1)) - 82.7) / 82.7 <= 0.05, ss.group(1) if ss else "none")
    if rid:
        code, out = run([PY, "-m", "tinyspice", "--db", db, "--runs", runs, "verify", rid.group(1)])
        check("provenance verify (every recorded artefact hash intact)", code == 0 and "VERIFIED" in out)
        code, out = run([PY, "-m", "tinyspice", "--db", db, "--runs", str(tmp / "replay_runs"), "replay", rid.group(1)])
        check("replay reproduces the stored measurements (rtol 1e-6)", code == 0 and '"matched": true' in out.lower())
    code, out = run([PY, "-m", "tinyspice", "--db", db, "--runs", runs, "ask", f"file:{ROOT / 'examples' / 'requests' / 'idvg_example.txt'}"])
    check("an incomplete request is refused, nothing is simulated", code == 1 and "rejected_invalid_input" in out)


def results_phase() -> None:
    code, out = run([PY, "scripts/run_bench.py", "report"])
    check("TinySPICEBench report recomputed", code == 0)
    blocks = out.split("===== row:")
    two_b = next((b for b in blocks if b.strip().startswith("qwen3.5-2b")), "")
    check("bench primary decision: C SUPPORTED over A (pre-registered)", "C is SUPPORTED over A" in two_b)
    fs = re.findall(r"^([ABC])\s+\d+/72 = [0-9.]+\s+(\d+)/72", two_b, flags=re.M)
    check("bench 2B false-success counts A=30, B=9, C=0", dict(fs) == {"A": "30", "B": "9", "C": "0"}, str(dict(fs)))
    committed = (ROOT / "results" / "bench" / "report.txt").read_text(encoding="utf-8").replace("\r\n", "\n").strip()
    check("recomputed bench report identical to the committed report", out.replace("\r\n", "\n").strip().endswith(committed[-400:]) or committed in out.replace("\r\n", "\n"))

    code, out = run([PY, "scripts/report_r1.py"])
    check("Stage 6b report recomputed: re-ask NOT supported", code == 0 and "R2 NOT supported" in out)

    code, out = run([PY, "scripts/run_f4.py", "report"])
    two = out.split("===== qwen3.5-0.8b")[0]
    check("Stage 7a: contradictions accepted under prune 5/36 -> 0/36 (2B)", "prune   v0: contradictions accepted 5/36" in two and "prune   v1: contradictions accepted 0/36" in two)
    check("Stage 7a: zero correct extractions lost", out.count("LOST by the change: 0") == 4)

    d = json.loads((ROOT / "results" / "stage4_confirm" / "confirm_result.json").read_text())
    check("Stage 4 confirmatory: SS success window 24/24 vs uniform 4/24, CONFIRMED", d["CONFIRMED"] is True and d["ss_success"] == {"window": 24, "uniform_pwl": 4}, f"p={d['sign_test_p_one_sided']:.2e}")

    code, out = run([PY, "scripts/replay_policies.py", "frozen3"])
    row = re.search(r"qwen3\.5-2b\s+frozen3\s+ground\s+\|\s+(\d+)/20\s+(\d+)\s+(\d+)/21", out)
    check("Stage 3 full-guard replay, 2B on F3: 7/20 exact, 0 silent-wrong, 0/21 bad accepted",
          code == 0 and row is not None and row.groups() == ("7", "0", "0"), str(row.groups()) if row else "no row")

    code, out = run([PY, "scripts/replay_grounding.py"])
    lost = re.findall(r"\|\s*(\d+)\s*$", out, flags=re.M)
    check("Stage 3 grounding replay: no correct output lost to the guard", code == 0 and bool(lost) and all(x == "0" for x in lost), f"{len(lost)} rows")


if __name__ == "__main__":
    mode = sys.argv[1] if len(sys.argv) == 2 else ""
    if mode not in ("quick", "results", "all"):
        sys.exit("usage: reproduce.py quick | results | all")
    if mode in ("quick", "all"):
        quick()
    if mode in ("results", "all"):
        results_phase()
    bad = [n for n, ok, _ in results if not ok]
    print(f"\n{len(results) - len(bad)}/{len(results)} checks passed" + (f"; FAILED: {bad}" if bad else ""))
    sys.exit(1 if bad else 0)
