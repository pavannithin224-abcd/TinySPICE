"""TinySPICE command line:  tinyspice plan|run|ask|replay|verify|runs  (python -m tinyspice ...)

Exit codes: 0 successful / recovered / verify ok / replay matched; 2 partially_completed; 1 anything else (failed, stopped, rejected, verify/replay mismatch).
`plan` is a dry run: it validates and prints the plan and spends nothing."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from tinyspice.errors import PlanRejected
from tinyspice.planner import build_plan
from tinyspice.provenance import ProvenanceStore, verify_run
from tinyspice.replay import replay
from tinyspice.runner import run_experiment
from tinyspice.schemas import ExperimentSpec, ExperimentStatus
from tinyspice.schemas.device import load_device_limits

ROOT = Path(__file__).resolve().parents[3]


def _limits(spec: ExperimentSpec, override: str | None):
    if override:
        return load_device_limits(Path(override))
    for p in sorted((ROOT / "configs" / "devices").glob("*.json")):      # match on the model name INSIDE the file
        lim = load_device_limits(p)
        if lim.model_name == spec.model_name:
            return lim
    sys.exit(f"no device limits file in configs/devices for model {spec.model_name!r}; pass --limits")


def _sim(name: str):
    if name == "mock":
        from tinyspice.simulator import MockSimulator
        return MockSimulator()
    from tinyspice.simulator import NgspiceSimulator
    return NgspiceSimulator()


def _load_spec(path: str) -> ExperimentSpec:
    return ExperimentSpec.model_validate_json(Path(path).read_text(encoding="utf-8"))


def cmd_plan(a) -> int:
    spec = _load_spec(a.spec)
    try:
        plan = build_plan(spec, _limits(spec, a.limits), a.strategy)
    except PlanRejected as e:
        print(f"REJECTED [{e.code}] -> {e.status.value}: {e.message}")
        return 1
    print(json.dumps(plan.model_dump(mode="json"), indent=2))
    print("\n(dry run: nothing was simulated, no budget was spent)")
    return 0


def cmd_run(a) -> int:
    spec = _load_spec(a.spec)
    store = ProvenanceStore(Path(a.db))
    r = run_experiment(spec, _limits(spec, a.limits), _sim(a.simulator), Path(a.runs), strategy=a.strategy, store=store)
    print(f"status   : {r.status.value}\nmessage  : {r.message}\nrun_id   : {r.run_id}\nrun dir  : {r.run_dir}")
    print(f"retries  : {r.retries_used}   recovery chain: {r.recovery_chain or '-'}   flags: {r.flags or '-'}")
    print("budget   : " + "  ".join(f"{k} {v['used']}/{v['limit']}" for k, v in r.budget.items()))
    for k, m in (r.measurements or {}).items():
        print(f"  {k:5s} " + (f"{m.value:.6g} {getattr(m, 'unit', '')}" if m.ok else f"REFUSED ({m.error_code})"))
    store.close()
    return {ExperimentStatus.SUCCESSFUL: 0, ExperimentStatus.RECOVERED: 0, ExperimentStatus.PARTIAL: 2}.get(r.status, 1)


def cmd_ask(a) -> int:
    """English request -> (parser) -> validated spec -> normal run. The parser only extracts; rejection is a normal, reported outcome."""
    from tinyspice.agent import interpret_request
    text = Path(a.request[5:]).read_text(encoding="utf-8") if a.request.startswith("file:") else a.request
    if a.parser == "rules":
        from tinyspice.providers import RuleBasedProvider
        provider, closer = RuleBasedProvider(), None
    else:
        from tinyspice.providers import LlamaCppProvider
        provider = closer = LlamaCppProvider(a.parser.split(":", 1)[1], temperature=0.0)
        provider.start()
    try:
        r = interpret_request(text, provider, ground=True)
    finally:
        if closer is not None:
            closer.stop()
    if not r.ok:
        print("status   : rejected_invalid_input")
        for e in r.errors:
            print(f"  - {e['loc'] or 'request'}: {e['msg']}")
        print("(nothing was simulated, no budget was spent)")
        return 1
    spec = r.spec
    print("understood request (the parser extracts; code validated it):")
    print(json.dumps(spec.model_dump(mode="json", exclude_none=True), indent=2))
    if a.dry_run:
        return 0
    from tinyspice.benchmark.bench import strategy_for
    store = ProvenanceStore(Path(a.db))
    strategy = a.strategy or strategy_for(spec)
    res = run_experiment(spec, _limits(spec, a.limits), _sim(a.simulator), Path(a.runs), strategy=strategy, store=store)
    print()
    print(f"status   : {res.status.value}")
    print(f"message  : {res.message}")
    print(f"run_id   : {res.run_id}   strategy: {strategy}")
    print("budget   : " + "  ".join(f"{k} {v['used']}/{v['limit']}" for k, v in res.budget.items()))
    for k, m in (res.measurements or {}).items():
        print(f"  {k:5s} " + (f"{m.value:.6g} {getattr(m, 'unit', '')}" if m.ok else f"REFUSED ({m.error_code})"))
    store.close()
    return {ExperimentStatus.SUCCESSFUL: 0, ExperimentStatus.RECOVERED: 0, ExperimentStatus.PARTIAL: 2}.get(res.status, 1)


def cmd_replay(a) -> int:
    store = ProvenanceStore(Path(a.db))
    rec = store.run(a.run_id)
    if rec is None:
        sys.exit(f"unknown run {a.run_id}")
    spec = ExperimentSpec.model_validate_json((Path(rec["run_dir"]) / "spec.json").read_text(encoding="utf-8"))
    out = replay(store, a.run_id, _sim(a.simulator), _limits(spec, a.limits), Path(a.runs), rtol=a.rtol)
    print(json.dumps(out, indent=2, default=str))
    store.close()
    return 0 if out["matched"] else 1


def cmd_verify(a) -> int:
    store = ProvenanceStore(Path(a.db))
    v = verify_run(store, a.run_id)
    print("VERIFIED: every recorded artefact is intact" if v["ok"] else "TAMPERED/INCOMPLETE:\n  " + "\n  ".join(v["problems"]))
    store.close()
    return 0 if v["ok"] else 1


def cmd_runs(a) -> int:
    store = ProvenanceStore(Path(a.db))
    for rid in store.run_ids():
        r = store.run(rid)
        print(f"{rid}  {r['status']:24s} {r['strategy']:10s} points={r['points']} retries={r['retries_used']} calls={r['tool_calls']}")
    store.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(prog="tinyspice", description="Budget-aware, reliability-driven MOSFET characterization")
    ap.add_argument("--db", default=str(ROOT / "experiments" / "provenance.sqlite"))
    ap.add_argument("--runs", default=str(ROOT / "experiments" / "runs"))
    ap.add_argument("--limits", default=None)
    ap.add_argument("--simulator", choices=("ngspice", "mock"), default="ngspice")
    sub = ap.add_subparsers(dest="cmd", required=True)
    p = sub.add_parser("plan", help="dry-run: validate and print the plan")
    p.add_argument("spec"), p.add_argument("--strategy", default="uniform", choices=("uniform", "curvature", "window"))
    p.set_defaults(fn=cmd_plan)
    p = sub.add_parser("run", help="execute an experiment spec")
    p.add_argument("spec"), p.add_argument("--strategy", default="uniform", choices=("uniform", "curvature", "window"))
    p.set_defaults(fn=cmd_run)
    p = sub.add_parser("ask", help="English request -> validated spec -> run (parser: rules, or llm:<model-key>)")
    p.add_argument("request", help="the request text, or file:<path>")
    p.add_argument("--parser", default="rules")
    p.add_argument("--strategy", default=None, choices=("uniform", "curvature", "window"))
    p.add_argument("--dry-run", action="store_true")
    p.set_defaults(fn=cmd_ask)
    p = sub.add_parser("replay", help="re-run a stored run and compare measurements")
    p.add_argument("run_id"), p.add_argument("--rtol", type=float, default=1e-6)
    p.set_defaults(fn=cmd_replay)
    p = sub.add_parser("verify", help="check a stored run's artefact hashes")
    p.add_argument("run_id")
    p.set_defaults(fn=cmd_verify)
    p = sub.add_parser("runs", help="list recorded runs")
    p.set_defaults(fn=cmd_runs)
    a = ap.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
