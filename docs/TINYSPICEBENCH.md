# TinySPICEBench

**Status: DRAFT definitions; to be FROZEN by 2026-11-23, before any final benchmark run.** No results exist yet.

## Configurations
A. Direct LLM-to-tool. B. Structured agent (validated spec + planner). C. Full TinySPICE (+ budget manager, adaptive sampling, recovery, provenance). Same simulator inputs and conditions for all.

## Tasks: 24 = 4 groups x 6
- **G1 Understanding:** valid parse; missing parameter detected; contradiction rejected; typed spec generated; stated constraints preserved; no invented conditions.
- **G2 Planning/simulation:** valid plan; correct ngspice config; point limit respected; valid experiment executes; simulator error detected; output validated.
- **G3 Measurement/optimisation:** measurements extracted; incomplete data detected; uniform vs adaptive compared; reconstruction error measured; point reduction evaluated; numerical edge cases handled.
- **G4 Reliability/reproducibility:** recover from recognised fault; stop at retry limit; respect time budget; provenance preserved; reproduce from stored spec; no false-success report.
Individual task texts and gold answers: to be written in `tests/benchmark/` and frozen with this file.

## Metrics (definitions)
- **Task completion rate** = tasks whose final status equals the gold expected status / total (rejection is a correct outcome for rejection tasks).
- **Specification validity** = specs that pass `ExperimentSpec` AND match gold fields / specs produced.
- **Tool-call validity** = tool calls that are registered, schema-valid and in range / total tool calls.
- **Measurement error** = |measured - reference| / |reference| per measurement, reference from the dense sweep; report median and max.
- **Simulation-point reduction** = 1 - N_adaptive / N_uniform at equal reconstruction-error tolerance; also error at equal N.
- **Budget violations** = runs where any consumed budget dimension exceeded its limit.
- **Recovery success rate** = injected recoverable faults ending RECOVERED / injected recoverable faults.
- **Reproducibility** = replays whose measurements match stored values within rtol 1e-6 / replays.
- **False-success rate** = runs reported SUCCESSFUL that fail an independent ground-truth check / total runs.
- **Execution time** (wall-clock) and **tool-call count** per run.

Trials: 3 per (task, configuration). Report model name, quantisation, runtime version, seed. Failed runs are kept.
