# TinySPICE: one-page summary

**What it is.** An LLM agent for MOSFET characterization where the model only translates an English request into a typed spec; everything else (validation, budgets, real ngspice runs, measurements, recovery, status, provenance) is deterministic code. Every reported number comes from simulator output, and a run is "successful" only if every requested measurement succeeded.

**Why it matters.** Direct LLM-to-simulator agents invent unstated conditions, ignore stated budgets and report success when a measurement failed. TinySPICE measures and removes that failure mode.

**What I built (Nov 2026, solo):** ngspice 47 + SKY130 runner, measurement engine (VTH, SS, GM, GDS, ION, IOFF), a local-LLM parser with deterministic guardrails (llama.cpp, Qwen3.5 0.8B/2B), a budget ledger, a recovery catalogue, a six-state status machine, SQLite provenance with hash-verified replay, a CLI, and a 24-task benchmark with an independent scorer. 269 tests; one command reproduces every number from a clean clone (18/18 checks).

**Key results** (all pre-registered, committed raw data):
- **Benchmark (Qwen3.5-2B, 72 runs per configuration):** false success 30 (direct), 9 (structured), **0** (full system); completion 0.50 / 0.46 / **0.86**. Task-level sign test A-only 10 vs C-only 0, p = 0.001. With a perfect parser the direct baseline still falsely succeeded in 42 % of runs: the cause is orchestration, not language understanding.
- **Measurement-aware sampling:** subthreshold-swing extraction 24/24 vs 4/24 at 16-20 points on held-out conditions (p = 1e-6).
- **Guardrails:** a small local model plus deterministic guards accepted 0/21 bad requests (raw: 7/21) with no correct extraction lost; recall is only about 35 %.
- **Reliability:** 20/20 pre-registered failure-injection cases correct; replay matches within 1e-6.

**Reported honestly:** two ideas failed their pre-registered tests (curvature-adaptive sampling; an LLM re-ask) and are in the repo as negative results. I also corrected my own overstated p-value, a mislabelled test item, and a line-ending bug that broke frozen hashes on a fresh clone.

**Limits:** one author wrote tasks, system and baselines; 24 tasks; one device family and corner; Windows only; physical non-convergence recovery untested; small-model parse recall is low. Evidence supports a trend, not a general claim. "LLM + SPICE" is not new (e.g. AnalogAgent, arXiv 2603.23910); the claims here are the narrower ones above.

**Where to look:** `README.md` (status table), `docs/REPORT.md` (4-page report with figures), `docs/DEMO.md` (real transcript), `scripts/reproduce.py all`.
