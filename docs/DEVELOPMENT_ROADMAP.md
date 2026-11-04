# Development Roadmap (2026-11-04 to 2026-11-30)

Every stage ends at a **gate**; the next stage starts only when the gate passes. Commit at each gate.

| Dates | Stage | Gate |
|---|---|---|
| Nov 4-5 | 0 Foundation: env, spec, planner, docs, metric drafts | plan approved, tests green, first commit |
| Nov 6-10 | 1 Simulator core: own ngspice 47 + SKY130 in `.tools/`, netlist gen, safe runner, parser, mock simulator, verify model limits | real Id-Vg run; rows == planned points; model hash + ngspice version stored |
| Nov 11-13 | 2 Measurement engine | analytic-curve tests pass, then real-data cross-check |
| Nov 14-17 | 3 LLM -> spec: provider interface, mock, local llama.cpp, constrained JSON, one repair retry, model timing | Group-1 parse accuracy measured |
| Nov 18-20 | 4 Adaptive sampling: uniform vs curvature | comparison table reported (win or not) |
| Nov 21-23 | 5 Reliability + provenance: budgets, recovery catalog, status machine, SQLite, replay; **freeze benchmark** | all failure-injection cases give correct status |
| Nov 24-27 | 6 TinySPICEBench runs | repeated trials complete; metrics computed |
| Nov 28-29 | 7 Release: CLI, README, figures, demo, reproduce script | fresh clone reproduces demo |
| Nov 30 | Buffer: critical fixes only | |

**Cut order if behind:** second LLM row -> error-guided sampling -> FastAPI -> PMOS -> temperature sweep. The pipeline and benchmark are never cut.

**Extra features (core):** failure-injection suite, replay & verify, dry-run plan preview, defaults ledger, measurement validity flags, frozen metrics.
**Optional ablation (first to cut):** learned failure-rules memory (idea from AnalogAgent, KDD 2026) compared against the deterministic recovery catalog.
**If time allows:** Id-Vd/GDS, PMOS, temperature sweep, Plotly report, error-guided sampling, FastAPI.
