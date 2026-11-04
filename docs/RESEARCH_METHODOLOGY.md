# Research Methodology

1. **Freeze before measure.** Metric definitions and the 24 task definitions are committed before the final benchmark run (target 2026-11-23). Later edits require a logged amendment.
2. **Ground truth.** Measurement reference = the same extraction applied to a dense reference sweep from real ngspice. LLM never supplies numbers.
3. **Three configurations**, identical simulator inputs/conditions: (A) direct LLM-to-tool; (B) structured agent (validated spec + planner); (C) full TinySPICE (budget manager, adaptive sampling, recovery, provenance).
4. **Repeats.** 3 trials per (task, configuration); LLM temperature 0 and fixed seed where supported. All outcomes recorded, including failures.
5. **Models.** Report the exact LLM (name, quantisation, runtime version) with every number. At least two models if time allows, to avoid tying conclusions to one weak model.
6. **Synthetic-first testing.** Measurement code is validated on analytic curves with known answers before real data.
7. **Honest reporting.** Negative or null results are reported. Results are not quoted before tasks have run.
8. **Provenance.** Every run stores spec, plan, netlist, model-file hash, ngspice version, raw output, measurements, errors/retries, runtime, budget use, git commit.
