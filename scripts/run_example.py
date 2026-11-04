"""Full pipeline demo on real SKY130: spec -> plan -> ngspice -> validation -> measurements -> honest status."""
import json
import sys
from pathlib import Path

from tinyspice.executor import execute
from tinyspice.schemas import ExperimentSpec, load_device_limits
from tinyspice.simulator import NgspiceSimulator

ROOT = Path(__file__).resolve().parents[1]
spec_path = Path(sys.argv[1]) if len(sys.argv) > 1 else ROOT / "configs/experiments/example_idvg.json"
spec = ExperimentSpec.model_validate(json.loads(spec_path.read_text()))
limits = load_device_limits(ROOT / "configs/devices/sky130_nfet_01v8.json")
rec = execute(spec, limits, NgspiceSimulator(), ROOT / "experiments" / "runs")
print("run_id :", rec.run_id)
print("status :", rec.status.value, "|", rec.message)
print("run_dir:", rec.run_dir)
for name, m in (rec.measurements or {}).items():
    if m.ok:
        v = "curve" if m.value is None else f"{m.value:.6g} {m.unit}"
        print(f"  {name:5s} {v:18s} {m.method}")
        extra = {k: d for k, d in m.diagnostics.items() if k in ("r2", "span_decades", "window_vgs_v", "near_solver_floor", "vgs_at_max_v", "max_on_sweep_edge", "target_current_a")}
        if extra:
            print("        ", extra)
    else:
        print(f"  {name:5s} FAILED {m.error_code}: {m.error_detail}")
sys.exit(0 if rec.status.value == "successful" else 1)
