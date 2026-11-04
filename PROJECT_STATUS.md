# TinySPICE — Project Status

_Last updated: 2026-11-04 (end of day 1)_

Status legend used across all docs: **IMPLEMENTED** (code exists) · **MOCK-TESTED** · **NGSPICE-TESTED** · **VERIFIED** (checked against independent reference) · **NOT IMPLEMENTED**.

## Stage progress
| Stage | State |
|---|---|
| 0 Foundation | DONE (committed) |
| 1 Simulator core | CODE DONE and tested; gate met for a real run (see below); awaiting commit review |
| 2 Measurement engine | not started |

## Components
| Component | Status |
|---|---|
| schemas (spec, device limits, status) | IMPLEMENTED, MOCK-TESTED |
| planner | IMPLEMENTED, MOCK-TESTED |
| simulator: netlist generator, model profiles, safe ngspice runner, output validation, error classification | IMPLEMENTED, MOCK-TESTED, **NGSPICE-TESTED** (ngspice 47) |
| simulator: MockSimulator with fault injection | IMPLEMENTED, MOCK-TESTED |
| NMOS Id-Vg on SKY130 `nfet_01v8` (tt corner) | **NGSPICE-TESTED** (plausibility only; not VERIFIED against any reference) |
| Id-Vd netlist | netlist generation MOCK-TESTED only; no real Id-Vd run yet |
| PMOS | NOT IMPLEMENTED (rejected with UnsupportedDevice) |
| measurements, sampling, budget runtime, recovery, provenance store, providers, agent, benchmark, CLI | NOT IMPLEMENTED |

## Evidence (real runs)
- ngspice-47 executed from `.tools/ngspice/Spice64/bin/ngspice_con.exe`.
- SKY130 NFET W=1 um, L=0.18 um, T=27 C, VDS=1.8 V, VGS 0..1.8 V: 91 points, validated (row count, finite, monotonic sweep, endpoints). Id rises from ~pA at VGS=0 to ~0.4 mA at 1.8 V.
- Failure path exercised for real: missing include file is detected and reported as MISSING_INCLUDE (not hidden).
- Tests: 67 passed (63 unit incl. 4 real-ngspice integration).

## Known limitations
- Process corner is fixed to `tt`; the spec has no corner field yet.
- SKY130 geometry limits (W 0.36-100 um, L 0.15-100 um) verified from the model bins; voltage and temperature limits are conventions (`limits_verified=false`).
- The built-in Level-1 model is educational (runner smoke tests only; no subthreshold).
- Tool downloads: 7zr.exe has no published checksum (only hashed after download); SKY130 files pinned by upstream commit.

## Environment
Windows 11, Python 3.14.7, venv `.venv`. All third-party tools live in `.tools/` (git-ignored, ~80 MB): ngspice 47, 7zr, SKY130 NFET model files. Nothing is read from other projects.
Note: the venv once lost packages unexpectedly (cause unknown); repaired with `pip install --force-reinstall -e .[dev]`; `pip check` clean.

## Next
1. Commit Stage 1 (after final test run).
2. Stage 2: measurement engine, analytic-curve tests first.
3. Time candidate local LLMs (Qwen3.5 small, Phi-4-mini, SmolLM3-3B) once measurements are in.

## Schedule
On plan: Stage 1 finished on day 1 of 5 allotted (Nov 6-10).
