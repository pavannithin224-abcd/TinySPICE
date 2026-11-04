# TinySPICEBench pre-registration (written and frozen BEFORE baselines A and B exist)

## Frozen artefacts
`tests/benchmark/bench_tasks.json` (24 tasks = 4 groups x 6; sha256 in `bench_tasks.sha256`). Every task was validated by running configuration C with a PERFECT parser: all 24 reach their expected status (`scripts/validate_bench_tasks.py`). Expected statuses were set before this validation and were not changed afterwards.

## Configurations (all receive the IDENTICAL recorded LLM output per task / model / seed)
- **A direct LLM-to-tool.** Lenient tool wrapper: the model's flat extraction is turned into a simulator call with NO validation. Unstated values are filled with fixed defaults (device nmos, model sky130_fd_pr__nfet_01v8, W 1.0 um, L 0.18 um, T 27 C, analysis idvg, sweep 0..1.8 V step 0.02 V, VDS 1.8 V (Id-Vg) / VGS 0.9 V (Id-Vd), measurements VTH, ION at the sweep stop, IOFF at the sweep start); contradictions are resolved silently (step wins over points; a fixed bias on the swept variable is dropped; a step that does not divide the range is truncated to the nearest multiple); stated budget limits are NOT enforced; no planner, no device-limit check, no retries; one simulator call; reported status is "successful" whenever the simulator returned valid data, even if measurements were refused, else "failed". A malformed model output is "failed".
- **B structured agent.** `interpret_request(ground=False)` (flat schema, strict null-drop, pydantic `ExperimentSpec` validation, one format repair) + the planner (device limits, point and tool-call pre-check) + one run through the Stage 1-2 executor (uniform sampling). No grounding / coverage / request-side guards, no ledger, no recovery, no provenance. Statuses: the executor's (successful, partially_completed, failed, rejected_invalid_input, stopped_budget_limit).
- **C full TinySPICE.** `interpret_request(ground=True)` (+ coverage + request-side guards) + `run_experiment`: budget ledger, bounded recovery, evidence-checked status, SQLite provenance; sampling policy = window sampling for Id-Vg with >= 12 points, uniform otherwise.
Shared by all three, on purpose: output validation and measurement extraction (the experiment isolates ORCHESTRATION). Fault injection (tasks T11, T12, T19-T21, T24) is applied identically to all three.

## LLM rows
Primary: Qwen3.5-2B-Q4_K_M. Secondary: Qwen3.5-0.8B-Q4_K_M. Diagnostic: an ORACLE-PARSE row where each configuration receives the gold extraction (separates orchestration from LLM recall; not part of the original plan, added before any result exists). Sampling: temperature 0.2, seeds 0, 1, 2 (3 trials); constrained JSON; prompt = the frozen `SYSTEM_PROMPT` of Stage 3 (sha256 recorded with the run). The oracle row has one trial (it is deterministic).

## Independent ground-truth check ("true success")
A reported SUCCESS CLAIM = status in {successful, recovered_after_failure}. It is a **false success** unless ALL hold:
1. the task's expected status is successful or recovered_after_failure (otherwise any success claim is false: executing a request that should have been rejected, stopped or failed is itself the error);
2. the executed spec matches the gold spec on: width, length, temperature, analysis, sweep (start, stop, and step or points), the fixed bias, measurement set, ION/IOFF bias points, and every budget field the gold states (rel 1e-6);
3. every gold measurement is present and within tolerance of the reference extracted from a dense plain-dc sweep (1 mV) of the GOLD spec (VTH 5 mV, SS 5 %, GM 5 %, ION 2 %, IOFF 0.05 decade; ID/GDS present and finite);
4. no stated budget is exceeded: points <= gold max_points; wall-clock <= gold max_runtime_s; 2 x simulator invocations <= gold max_tool_calls (when stated).

## Metrics
completion (status == expected); false-success rate (success claims failing the check / all runs); honest-failure rate (runs whose truth is failure that are NOT reported as success); specification validity (executed specs matching gold / runs that executed a spec for tasks with a valid gold); invented-condition rate (executions on tasks whose gold is a rejection); tool-call validity (executed specs the planner would accept / simulator invocations); measurement error (relative to tolerance, over true-success runs); budget violations; recovery success (T19, T20 completed / 2); reproducibility (T23: replay matches; configurations without a stored record are reported as "not replayable", not hidden); wall-clock; simulator invocations.

## Primary endpoint and decision rule
Primary row: Qwen3.5-2B. Unit = (task, seed) pair (72 per configuration). **PRIMARY: false-success rate, A vs C.** C is supported over A iff (a) false-success(C) < false-success(A), (b) the exact one-sided sign test on discordant pairs (A false & C not, vs the reverse) gives p < 0.01, and (c) the 95 % cluster-bootstrap CI (resampling TASKS, 2000 resamples, seed 20261104) of the paired difference excludes 0. Otherwise the claim is NOT supported and is reported as such. **Secondary** (descriptive, same tests, no multiplicity correction, all reported): C vs B false-success; completion by group with Wilson 95 % intervals; the 0.8B and oracle rows; trial-to-trial variability.

## Known limits stated up front
I wrote both the tasks and the system (author bias), mitigated by freezing tasks and expected outcomes first and by including tasks where C is expected to fail or tie (T11, T24 are pure controls); A is a deliberately lenient wrapper whose design is mine (a different "direct" design could do better, and the wrapper defaults above are the reader's check on fairness); n = 24 tasks, one device family, shared extractors; the 2B parser's low recall will depress every configuration on language-understanding tasks (the oracle row exposes that effect); constrained decoding at temperature 0.2 gives limited trial variance.

## Execution rules
Phase `llm` records model outputs (resumable); phase `run` is the ONE frozen evaluation and refuses to run twice; unknown phases are refused before any work. Amendments are logged below.

## Amendments
(none)
