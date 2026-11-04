"""TinySPICEBench harness. See docs/BENCH_PREREG.md (frozen before the baselines existed).
  python scripts/run_bench.py llm      # record the LLM outputs (2 models x 24 tasks x 3 seeds); resumable
  python scripts/run_bench.py run      # the ONE frozen evaluation (oracle row + both LLM rows, configs A, B, C); refuses to run twice
  python scripts/run_bench.py report   # analysis only; safe to repeat
The phase is checked BEFORE any heavy work; unknown phases are refused."""
import sys
from pathlib import Path

PHASES = ("llm", "run", "report")
if __name__ == "__main__" and (len(sys.argv) != 2 or sys.argv[1] not in PHASES):
    sys.exit(f"usage: run_bench.py <{'|'.join(PHASES)}>  (got {sys.argv[1:]!r})")

import hashlib
import json
import time

from tinyspice.agent import interpret_request
from tinyspice.agent.interpret import SYSTEM_PROMPT
from tinyspice.agent.raw import raw_json_schema
from tinyspice.benchmark.bench import TASKS_PATH, full_raw, load_tasks, run_config_c
from tinyspice.benchmark.baselines import run_config_a, run_config_b
from tinyspice.benchmark.scoring import SUCCESS_CLAIMS, cluster_bootstrap_diff, score, sign_test_one_sided, wilson
from tinyspice.provenance import ProvenanceStore
from tinyspice.providers import LlamaCppProvider, ScriptedProvider
from tinyspice.replay import replay
from tinyspice.schemas.device import load_device_limits
from tinyspice.simulator import NgspiceSimulator

ROOT = Path(__file__).resolve().parents[1]
OUT = ROOT / "results" / "bench"
MODELS = ["qwen3.5-2b", "qwen3.5-0.8b"]
SEEDS = (0, 1, 2)
TEMPERATURE = 0.2
RUN_JSON = OUT / "run.json"
LIMITS = load_device_limits(ROOT / "configs" / "devices" / "sky130_nfet_01v8.json")


class RecordingProvider:
    def __init__(self, inner):
        self.inner, self.texts, self.name = inner, [], getattr(inner, "name", "?")

    def complete_json(self, *a, **k):
        r = self.inner.complete_json(*a, **k)
        self.texts.append(r.text)
        return r


def check_frozen() -> None:
    want = (ROOT / "tests" / "benchmark" / "bench_tasks.sha256").read_text().split()[0]
    got = hashlib.sha256(TASKS_PATH.read_bytes()).hexdigest()
    if want != got:
        sys.exit(f"bench_tasks.json does not match its frozen hash ({got[:12]} != {want[:12]}); refusing to run")


def phase_llm() -> None:
    check_frozen()
    OUT.mkdir(parents=True, exist_ok=True)
    tasks = load_tasks()
    for model in MODELS:
        f = OUT / f"llm_{model}.json"
        data = json.loads(f.read_text()) if f.exists() else {"model": model, "temperature": TEMPERATURE, "seeds": list(SEEDS),
                                                              "prompt_sha256": hashlib.sha256(SYSTEM_PROMPT.encode()).hexdigest(),
                                                              "schema_sha256": hashlib.sha256(json.dumps(raw_json_schema(), sort_keys=True).encode()).hexdigest(),
                                                              "outputs": {}}
        prov = LlamaCppProvider(model, temperature=TEMPERATURE)
        with prov:
            data["model_meta"] = prov.tools.manifest["models"][model]
            data["llama_cpp_tag"] = prov.tools.manifest["llama_cpp"]["tag"]
            for t in tasks:
                for seed in SEEDS:
                    key = f"{t['id']}|{seed}"
                    if key in data["outputs"]:
                        continue
                    rec = RecordingProvider(prov)
                    t0 = time.monotonic()
                    interpret_request(t["text"], rec, ground=False, seed=seed)       # records the first response and any repair response
                    data["outputs"][key] = {"texts": rec.texts, "latency_s": round(time.monotonic() - t0, 2)}
                    f.write_text(json.dumps(data, indent=1))
                print(f"{model} {t['id']} done", flush=True)
    print("llm phase complete")


def phase_run() -> None:
    check_frozen()
    if RUN_JSON.exists():
        sys.exit("run.json exists: the frozen evaluation executes ONCE (docs/BENCH_PREREG.md). Refusing.")
    llm = {}
    for m in MODELS:
        p = OUT / f"llm_{m}.json"
        if not p.exists():
            sys.exit(f"missing {p}; run the llm phase first")
        d = json.loads(p.read_text())
        if len(d["outputs"]) != 24 * len(SEEDS):
            sys.exit(f"{p.name} is incomplete ({len(d['outputs'])} of {24 * len(SEEDS)} outputs)")
        llm[m] = d
    store = ProvenanceStore(OUT / "provenance.sqlite")
    rows = []
    t_start = time.monotonic()
    for row in ["oracle"] + MODELS:
        for t in load_tasks():
            for seed in ([None] if row == "oracle" else SEEDS):
                texts = [json.dumps(full_raw(t["gold_raw"]))] if row == "oracle" else llm[row]["outputs"][f"{t['id']}|{seed}"]["texts"]
                wd = OUT / "runs" / row / t["id"] / str(seed)
                outs = {
                    "A": run_config_a(t, texts, wd / "A"),
                    "B": run_config_b(t, ScriptedProvider(*texts), LIMITS, wd / "B"),
                    "C": run_config_c(t, ScriptedProvider(*texts), LIMITS, wd / "C", store=store),
                }
                for cfg, o in outs.items():
                    repro = None
                    if t["id"] == "T23" and cfg == "C" and o.run_id:
                        rp = replay(store, o.run_id, NgspiceSimulator(), LIMITS, wd / "replay", rtol=1e-6)
                        repro = bool(rp["matched"])
                    s = score(t, o, LIMITS, OUT / "work", reproducible=repro)
                    s.update({"row": row, "seed": seed})
                    rows.append(s)
        print(f"row {row} done ({len(rows)} scored runs, {time.monotonic() - t_start:.0f}s)", flush=True)
    store.close()
    RUN_JSON.write_text(json.dumps({"rows": rows, "models": {m: {k: llm[m][k] for k in ("temperature", "prompt_sha256", "schema_sha256", "model_meta", "llama_cpp_tag")} for m in MODELS},
                                    "tasks_sha256": hashlib.sha256(TASKS_PATH.read_bytes()).hexdigest()}, indent=1))
    phase_report()


def phase_report() -> None:
    data = json.loads(RUN_JSON.read_text())
    rows = data["rows"]
    lines = []
    P = lambda s="": (print(s), lines.append(s))   # noqa: E731
    for row in ["qwen3.5-2b", "qwen3.5-0.8b", "oracle"]:
        R = [r for r in rows if r["row"] == row]
        P(f"\n===== row: {row}  ({len(R) // 3} runs per configuration)")
        P(f"{'cfg':3s} {'completion':>16s} {'FALSE-SUCCESS':>20s} {'success claims':>14s} {'honest-fail':>12s} {'invented':>9s} {'budget viol':>11s} {'spec valid':>11s}")
        for cfg in "ABC":
            C = [r for r in R if r["config"] == cfg]
            n = len(C)
            k_comp = sum(r["completion"] for r in C)
            k_fs = sum(r["false_success"] for r in C)
            k_claim = sum(r["claim"] for r in C)
            nf = [r for r in C if not r["truth_achieved"]]
            k_hf = sum(r["honest_failure"] for r in nf)
            k_inv = sum(r["invented"] for r in C)
            k_bv = sum(r["budget_violation"] for r in C)
            sv = [r["spec_valid"] for r in C if r["spec_valid"] is not None]
            lo, hi = wilson(k_fs, n)
            P(f"{cfg:3s} {k_comp:3d}/{n:<3d}={k_comp / n:5.2f}    {k_fs:3d}/{n:<3d}={k_fs / n:5.2f} [{lo:.2f},{hi:.2f}] {k_claim:6d}      {k_hf:3d}/{len(nf):<3d}={k_hf / max(1, len(nf)):5.2f}  {k_inv:5d}     {k_bv:5d}       {sum(sv)}/{len(sv)}")
        P("completion by group (A / B / C):  " + "   ".join(
            f"{g}: " + "/".join(f"{sum(r['completion'] for r in R if r['config'] == c and r['group'] == g)}" for c in "ABC") + f" of {sum(1 for r in R if r['config'] == 'A' and r['group'] == g)}"
            for g in ("G1", "G2", "G3", "G4")))
        for other in ("A", "B"):
            pairs, wo, bo = [], 0, 0
            key = lambda r: (r["task"], r["seed"])    # noqa: E731
            cm = {key(r): r for r in R if r["config"] == "C"}
            om = {key(r): r for r in R if r["config"] == other}
            for k, rc in cm.items():
                ro = om[k]
                pairs.append((k[0], float(ro["false_success"]), float(rc["false_success"])))
                wo += bool(ro["false_success"] and not rc["false_success"])
                bo += bool(rc["false_success"] and not ro["false_success"])
            diff, lo, hi = cluster_bootstrap_diff(pairs)
            p = sign_test_one_sided(wo, bo)
            P(f"false-success {other} vs C: {other}-only {wo}, C-only {bo}; exact one-sided sign p = {p:.2e}; mean diff ({other} - C) = {diff:+.3f}  95% task-cluster CI [{lo:+.3f}, {hi:+.3f}]"
              + ("   <== PRIMARY" if (row == 'qwen3.5-2b' and other == 'A') else ""))
            if row == "qwen3.5-2b" and other == "A":
                supported = (diff > 0) and (p < 0.01) and (lo > 0)
                P(f"PRIMARY DECISION (pre-registered): C is {'SUPPORTED' if supported else 'NOT supported'} over A on false-success.")
        T23 = [r for r in R if r["task"] == "T23" and r["config"] == "C"]
        if T23:
            P("reproducibility (T23, config C replay matches): " + ", ".join(str(r["reproducible"]) for r in T23) + "   (A and B keep no stored record: not replayable)")
    (OUT / "report.txt").write_text("\n".join(lines), encoding="utf-8")


if __name__ == "__main__":
    {"llm": phase_llm, "run": phase_run, "report": phase_report}[sys.argv[1]]()
