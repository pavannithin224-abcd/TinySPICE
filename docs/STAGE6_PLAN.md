# Stage 6 plan: TinySPICEBench (DRAFT, awaiting approval; nothing built)

Goal: measure, on 24 pre-written tasks, whether a structured, budget-aware, recovering agent beats direct LLM-to-tool execution, and say so honestly if it does not. Everything below is written and frozen BEFORE any benchmark run (freeze target brought forward from Nov 23 to about Nov 9).

## The three configurations (same LLM, same simulator, same extractors, same dense reference)
| | A: direct LLM-to-tool | B: structured agent | C: full TinySPICE |
|---|---|---|---|
| LLM output | a tool call `simulate(...)` straight from the request | `ExperimentSpec` JSON | `ExperimentSpec` JSON |
| Validation | JSON-schema types only | pydantic spec validation + planner (device limits, point budget) | + grounding, coverage, request-side guards (Stage 3) |
| Missing / unstated values | filled in by the model or by tool defaults | rejected (spec validation) | rejected |
| Execution | one call, no budget enforcement | one run, planner pre-check only | budget ledger, bounded recovery, window sampling, SS recovery (Stage 4-5) |
| Status reported | "success" if the process exited 0 (naive) | executor status | evidence-checked six-state status |
| Provenance | none | run folder only | SQLite + manifest + replay |
Measurement extraction code is shared by all three on purpose: the experiment isolates ORCHESTRATION (validation, planning, budgets, recovery, honest status), not the extractors.

## Tasks: 24 = 4 groups x 6 (texts, gold specs, expected final status, frozen with a hash)
- G1 Understanding: valid parse; missing parameter; contradiction; typed spec; stated constraints preserved; no invented conditions.
- G2 Planning / simulation: valid plan; point limit respected; valid experiment executes; simulator error detected; output validated; out-of-range request refused.
- G3 Measurement / sampling: all five measurements extracted; incomplete data detected; uniform vs window compared at small N; reconstruction error vs dense reference; point reduction; numerical edge case (sweep ends below threshold).
- G4 Reliability: recover from a recognised fault; stop at the retry limit; respect the time budget; provenance preserved; reproduce from the stored spec; no false success. G4 reuses the Stage-5 injection mechanism (identical faults injected into A, B and C).
Rule: include tasks where C is expected to FAIL (unrecognised fault -> failed is the correct answer) and tasks where A can be right. Expected outcomes are written before A and B exist.

## Metrics (as defined in docs/TINYSPICEBENCH.md, unchanged)
Task completion (final status == gold status; rejection counts as correct on rejection tasks), specification validity, tool-call validity, measurement error vs dense reference (median and max), point reduction, budget violations, recovery success, reproducibility (rtol 1e-6), FALSE-SUCCESS RATE (reported success that fails an independent ground-truth check), wall-clock, tool calls.

## Statistics (pre-specified)
24 tasks x 3 configurations x 3 trials = 216 runs. Per-group rates with Wilson 95 % intervals; paired task-level comparisons C vs A and C vs B by exact sign test on discordant tasks; trial variability reported, not hidden. No p-hacking: the primary endpoint is FALSE-SUCCESS RATE (A vs C) and the secondary is task completion. Trend-level claims only (n = 24).

## Compute and schedule
LLM ~25 s per parse on this CPU + ~1-3 s simulation: about 2 hours for the whole benchmark. Nov 5-8: write + freeze tasks and expected outcomes. Nov 8-11: harness (A, B, C adapters). Nov 12: one frozen run. Nov 13-15: analysis and report. Stage 7 (release) follows with a large buffer before Nov 30.

## Decisions I need from you
1. **Config definitions.** Is A (tool call straight from the LLM, naive success reporting) and B (spec validation + planner but no grounding/ledger/recovery) a fair reading of "direct" and "structured"? I put grounding in C only because it is part of the contribution being tested. *Recommended: yes.*
2. **Trials.** At temperature 0 with a fixed seed the LLM is deterministic, so "3 trials" would be identical. Proposal: temperature 0.2 and seeds 0, 1, 2 so trial variance is real and reported. *Recommended: yes.*
3. **LLM rows.** Run the full benchmark with Qwen3.5-2B only, or also with Qwen3.5-0.8B (risk R6: a weak LLM inflates the guardrail benefit; a second model shows how much)? 0.8B adds about 40 minutes of compute. *Recommended: add 0.8B.*
4. **LLM re-ask sub-stage** (bounded re-ask on a deterministic error to lift the 35 % parse recall): do it AFTER the benchmark, as a pre-registered sub-stage, and only if parse recall turns out to be the bottleneck in the data. *Recommended: after.*

## Risks
I write both the tasks and the system (author bias): mitigated by freezing tasks and expected outcomes before the baselines exist and by including tasks C should fail. Small n (24 tasks): trend-level claims only. The 2B parser's low recall will depress every configuration on G1-style tasks: reported, not hidden.
