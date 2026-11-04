# Research Problem

## Problem
Characterizing a MOSFET means preparing a SPICE deck, sweeping biases, running the simulator, and post-processing. An LLM can ease the front end, but letting it drive tools directly risks: invalid configs, silently invented parameters, wasted points, endless retries, wrong measurement extraction, missing records, and false claims of success.

## Prior art (found by web search 2026-11-04; not exhaustive, details unverified)
- LLM + ngspice tool servers: SPICEBridge, mcp-spice, eda-agents, PowerElecLLM, SPICEPilot.
- LLM agents for MOSFET parameter extraction: ModelGen (ACM TODAES).
- Benchmarks for LLM SPICE work: NetlistBench; Long-Horizon Analog Design Bench.
- Provenance/governance for LLM-driven experiments: KDD 2026 workshop paper on governed LLM experimentation.
- Adaptive sampling for device/circuit modelling: several older papers (SVM-based, statistical compact-model sampling).

**Therefore** "LLM drives ngspice" is not novel. We make no such claim.

## What we investigate
Whether hard budgets + bounded recovery + validated specs + honest status measurably reduce false success and budget violations versus direct LLM-to-tool execution, and whether curvature-based sampling saves Id-Vg points at acceptable error. Novelty of the combination is *unverified*; a five-search sweep found no MOSFET-characterization system combining all of these.

## Hypotheses (to be tested, may be falsified)
- H1: structured agent lowers invalid-spec and false-success rates vs direct execution.
- H2: budget manager yields zero budget violations by construction; direct baseline does not.
- H3: bounded recovery recovers recognised faults and stops on unrecognised ones.
- H4: curvature sampling reduces points vs uniform at equal reconstruction error. (May fail.)
- H5: stored records replay to within tolerance.
