# Research Problem

## Problem
Characterizing a MOSFET means preparing a SPICE deck, sweeping biases, running the simulator, and post-processing. An LLM can ease the front end, but letting it drive tools directly risks: invalid configs, silently invented parameters, wasted points, endless retries, wrong measurement extraction, missing records, and false claims of success.

## Prior art (found by web search 2026-11-04; not exhaustive, details unverified)
- LLM + ngspice tool servers: SPICEBridge, mcp-spice, eda-agents, PowerElecLLM, SPICEPilot.
- LLM agents for MOSFET parameter extraction: ModelGen (ACM TODAES).
- Benchmarks for LLM SPICE work: NetlistBench; Long-Horizon Analog Design Bench.
- Provenance/governance for LLM-driven experiments: KDD 2026 workshop paper on governed LLM experimentation.
- Adaptive sampling for device/circuit modelling: several older papers (SVM-based, statistical compact-model sampling).
- Execution-driven multi-agent analog *design* generation: **AnalogAgent** (KDD 2026 AI4Science oral, arXiv 2603.23910; repo TheWind-upBird/Analogagent, MIT) with a Code Generator / Design Optimizer / Knowledge Curator and a self-evolving rule memory; also AnalogCoder and AnalogCoder-Pro. Evaluated by Pass@1/Pass@5 on circuit-design tasks; has a per-task attempt cap `K`. Read 2026-11-04 (abstract + paper HTML; code not read or run). Not found in the paper text: point/time budgets, honest status states, false-success metric, provenance/replay (absence not proven). Reference only; no code reused.

**Therefore** "LLM drives ngspice" is not novel. We make no such claim.

## What we investigate
Whether hard budgets + bounded recovery + validated specs + honest status measurably reduce false success and budget violations versus direct LLM-to-tool execution, and whether curvature-based sampling saves Id-Vg points at acceptable error. Novelty of the combination is *unverified*; a five-search sweep found no MOSFET-characterization system combining all of these.

## Hypotheses (to be tested, may be falsified)
- H1: structured agent lowers invalid-spec and false-success rates vs direct execution.
- H2: budget manager yields zero budget violations by construction; direct baseline does not.
- H3: bounded recovery recovers recognised faults and stops on unrecognised ones.
- H4: curvature sampling reduces points vs uniform at equal reconstruction error. (May fail.)
- H5: stored records replay to within tolerance.
