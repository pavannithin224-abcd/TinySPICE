# Stage 5 plan: reliability and provenance (DRAFT, awaiting approval; nothing built)

Gate (from the roadmap): **every failure-injection case ends in the pre-registered correct status.** Added gates: consumed budget never exceeds a limit; a stored run replays within rtol 1e-6; no SUCCESSFUL on an unhandled injected fault.

## Components
| # | Component | What it is | Notes |
|---|---|---|---|
| 5.1 | `budget/` BudgetLedger | counts points, tool calls, retries, wall-clock; **charges before** each action; raises before exceeding | STOPPED_BUDGET; invariant tested |
| 5.2 | `recovery/` catalog | table: named fault -> (recoverable?, action, max attempts, physics rule) | below |
| 5.3 | `status/` machine | pure function `final_status(events)`; exhaustive truth-table tests | six states, evidence-gated |
| 5.4 | `provenance/` store | SQLite (WAL, append-only, parameterised SQL only) + run folder + sha256 manifest; defaults ledger | stores spec/plan hashes, model-file hashes, ngspice version, code git commit, LLM id + prompt hash + grounding-policy version, event timeline, budget use, recovery chain, validity flags |
| 5.5 | replay / verify | `replay(run_id)`: re-run stored spec+plan+strategy, compare measurements (rtol 1e-6); `verify(run_id)`: manifest hashes intact | E5 |
| 5.6 | failure-injection suite (E4) | real-ngspice injections where possible, mock otherwise; **expected-status table written and committed first** | feeds benchmark G4 |
| 5.7 | CLI | `tinyspice plan | run | replay | verify` (dry-run plan preview = `plan`) | FastAPI stays cut |

## Recovery catalog (proposal)
| Fault | Recoverable? | Action | Rule |
|---|---|---|---|
| MISSING_INCLUDE, MODEL_NOT_FOUND, NETLIST_SYNTAX | no (configuration) | FAILED at once, clear diagnosis | retrying would be guessing |
| TIMEOUT | yes | one retry with a longer limit if wall-clock budget remains, else STOPPED_BUDGET | |
| ROW_COUNT_MISMATCH / NO_OUTPUT / NONFINITE_VALUES (truncated, NaN) | yes (transient) | one clean re-run | |
| NONCONVERGENCE | yes | solver ladder: raise iteration limits, then gear integration; **never gmin/abstol** (changing them re-creates the IOFF artefact found in Stage 1) | recovered run is flagged; IOFF re-checked against the solver floor |
| SS/VTH extractor refusal (window too narrow, too few points) | yes, **if points remain in the budget** | spend leftover budget on window-targeted refinement (the Stage-4 confirmed method), re-extract | this is where RECOVERED earns its name |
| anything unrecognised | no | stop, FAILED | never creative |

Recovery attempts are bounded by `max_retries` (default 2) AND by the ledger. A recovery may not change anything that alters a measured value beyond tolerance unless the measurement is flagged.

## Decisions I need from you
1. **Runtime semantics.** Today `max_runtime_s` is a per-ngspice-process timeout. Proposal: make it the **total wall-clock deadline for the whole run, retries included**, with each process timeout = min(remaining, cap). (Recommended: otherwise 3 retries can silently take 3x the stated limit.)
2. **NONCONVERGENCE recovery** via the solver ladder above (flagged, never touching gmin/abstol), or no solver changes at all (retry only)? (Recommended: ladder, flagged.)
3. **Measurement-level recovery** (SS refusal -> window refinement with leftover budget -> RECOVERED)? (Recommended: yes; it puts the Stage-4 result to work.)
4. **LLM re-ask on a deterministic error** and the open H13 bug (stated budget limits left null get silently defaulted): defer to a later pre-registered sub-stage with a fresh test set F4? (Recommended: defer; it needs its own evaluation.)

## Schedule (ahead of plan: original slot Nov 21-23)
Nov 5-6: 5.1-5.3 with tests. Nov 7-8: 5.4-5.5. Nov 9-10: 5.6 + CLI. Then freeze TinySPICEBench early (was Nov 23) so Stage 6 has buffer.

## Cut order if behind
learned-rules ablation -> LLM re-ask -> CLI polish -> FastAPI (already cut). The ledger, catalog, status machine, store, replay and injection suite are never cut.

## Risks
Replay non-determinism in ngspice (check first, cheaply); recovery that changes physics (rule above + flags); scope creep (cut order); status-machine bugs that mislabel success (exhaustive tests + the injection suite is the oracle).
