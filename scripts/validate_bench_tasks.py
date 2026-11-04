"""Validates the 24 benchmark tasks: the FULL system (config C) with a PERFECT parser must reach every task's expected status.
This proves each expected status is achievable (no wishful gold) before the baselines exist. Real ngspice."""
import shutil
import sys
from pathlib import Path

from tinyspice.benchmark.bench import load_tasks, oracle_provider, run_config_c
from tinyspice.schemas.device import load_device_limits

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "experiments" / "runs" / "_bench_validate"
if OUT.exists():
    shutil.rmtree(OUT)
limits = load_device_limits(ROOT / "configs" / "devices" / "sky130_nfet_01v8.json")
only = set(sys.argv[1:])
bad = 0
for t in load_tasks():
    if only and t["id"] not in only:
        continue
    o = run_config_c(t, oracle_provider(t), limits, OUT / t["id"])
    ok = o.status == t["expected_status"]
    bad += not ok
    print(f"{t['id']} {t['group']} {'OK ' if ok else 'MISMATCH'} expected={t['expected_status']:24s} got={o.status:24s} pts={o.points:3d} retries={o.retries} {t['name'][:42]:42s} {'' if ok else o.notes[:120]}")
print("mismatches:", bad)
sys.exit(1 if bad else 0)
