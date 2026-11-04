"""TinySPICEBench plumbing: shared helpers and the configuration adapters.

All three configurations receive the IDENTICAL LLM output (recorded once per task/model/seed); they differ only in what happens after:
  A direct LLM-to-tool : lenient tool wrapper, no validation, no planner, no budget enforcement, naive success reporting
  B structured agent   : pydantic spec validation + planner + one run (Stage 1-2 executor); no grounding, no ledger, no recovery
  C full TinySPICE     : grounding/coverage/guards + budget ledger + bounded recovery + window sampling + evidence-checked status + provenance
Measurement extraction and output validation live in the shared tool layer and are identical for all three on purpose: the experiment
isolates ORCHESTRATION.
"""
from __future__ import annotations

import json
import time
from dataclasses import dataclass, field
from pathlib import Path

from tinyspice.agent import interpret_request
from tinyspice.agent.raw import RAW_FIELDS
from tinyspice.providers import ScriptedProvider
from tinyspice.recovery.injection import InjectingSimulator
from tinyspice.runner import run_experiment
from tinyspice.schemas import ExperimentSpec
from tinyspice.simulator import NgspiceSimulator

ROOT = Path(__file__).resolve().parents[3]
TASKS_PATH = ROOT / "tests" / "benchmark" / "bench_tasks.json"
TOL = {"VTH": 5.0, "SS": 5.0, "GM": 5.0, "ION": 2.0, "IOFF": 0.05, "ID": None, "GDS": None}   # same tolerances as Stage 4


def load_tasks() -> list[dict]:
    return json.loads(TASKS_PATH.read_text(encoding="utf-8"))["tasks"]


def full_raw(gold: dict) -> dict:
    """A gold (non-null only) extraction expanded to the flat schema."""
    return {k: None for k in RAW_FIELDS} | gold


def oracle_provider(task: dict) -> ScriptedProvider:
    return ScriptedProvider(json.dumps(full_raw(task["gold_raw"])))


class CountingSimulator:
    """Counts simulator invocations (and accumulates ngspice wall-clock) for every configuration the same way."""
    name = "counting"

    def __init__(self, inner):
        self.inner, self.calls, self.sim_seconds = inner, 0, 0.0

    def version(self):
        return self.inner.version()

    def run(self, spec, run_dir, **kw):
        self.calls += 1
        t0 = time.monotonic()
        try:
            return self.inner.run(spec, run_dir, **kw)
        finally:
            self.sim_seconds += time.monotonic() - t0


def make_sim(task: dict) -> CountingSimulator:
    inner = NgspiceSimulator()
    if task.get("inject"):
        inner = InjectingSimulator(inner, task["inject"]["type"], task["inject"]["mode"])
    return CountingSimulator(inner)


def strategy_for(spec: ExperimentSpec) -> str:
    """C's sampling policy: measurement-aware window sampling for Id-Vg with >= 12 points, uniform otherwise."""
    return "window" if (spec.analysis.value == "idvg" and spec.sweep.n_points >= 12) else "uniform"


@dataclass
class Outcome:
    config: str
    status: str                       # one of the six ExperimentStatus values ('successful'/'failed' only for config A)
    spec: dict | None = None          # the spec actually executed (None if nothing ran)
    values: dict = field(default_factory=dict)     # measurement name -> value or None (refused)
    points: int = 0
    wallclock_s: float = 0.0
    sim_calls: int = 0
    tool_calls: int = 0
    retries: int = 0
    run_dir: str | None = None
    run_id: str | None = None
    notes: str = ""


def run_config_c(task: dict, provider, limits, workdir: Path, store=None) -> Outcome:
    t0 = time.monotonic()
    r = interpret_request(task["text"], provider, ground=True)
    if not r.ok:
        return Outcome("C", "rejected_invalid_input", wallclock_s=time.monotonic() - t0, notes="; ".join(f"{e['loc']}: {e['msg']}" for e in r.errors)[:300])
    sim = make_sim(task)
    res = run_experiment(r.spec, limits, sim, workdir, strategy=strategy_for(r.spec), store=store)
    vals = {k: (m.value if m.ok else None) for k, m in (res.measurements or {}).items()}
    return Outcome("C", res.status.value, spec=r.spec.model_dump(mode="json"), values=vals, points=res.n_points,
                   wallclock_s=time.monotonic() - t0, sim_calls=sim.calls, tool_calls=res.budget["tool_calls"]["used"],
                   retries=res.retries_used, run_dir=str(res.run_dir), run_id=res.run_id, notes=res.message[:200])
