# Experiment Plan

| ID | Question | Method | Pass/report rule |
|---|---|---|---|
| E1 | Do measurement extractors recover known values? | Analytic curves (square-law, exponential subthreshold) | Error under stated tolerance |
| E2 | Do extractors agree on real SKY130 data? | Dense Id-Vg sweep, cross-check vs independent numpy/scipy computation | Report agreement; no claim vs silicon |
| E3 | Uniform vs curvature sampling | Dense reference (e.g. several hundred points); compare at equal N and at equal error | Table of N, MAE, max error, reduction; reported even if no win |
| E4 | Failure injection and recovery | Corrupted include, non-convergence, truncated output, timeout, bad bias | Correct status for every case |
| E5 | Replay reproducibility | Re-run stored specs | Match within tolerance |
| E6 | TinySPICEBench A/B/C | See TINYSPICEBENCH.md | Metrics as defined, repeated trials |

Compute budget: ngspice DC sweeps are cheap (seconds). Local LLM parsing ~tens of seconds per call (unmeasured); benchmark size sized accordingly.
