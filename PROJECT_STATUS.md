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
| NMOS Id-Vg on SKY130 `nfet_01v8` (tt corner) | **NGSPICE-TESTED** (physical trends checked; not VERIFIED against any independent reference) |
| NMOS Id-Vd on SKY130 | **NGSPICE-TESTED** (real run, saturation behaviour checked) |
| executor (spec -> plan -> simulator -> run dir -> honest status) | IMPLEMENTED, MOCK-TESTED, NGSPICE-TESTED. Valid simulation yields PARTIAL only; SUCCESSFUL is unreachable until Stage 2 extraction exists |
| PMOS | NOT IMPLEMENTED (rejected with UnsupportedDevice) |
| measurements, sampling, budget runtime, recovery, provenance store, providers, agent, benchmark, CLI | NOT IMPLEMENTED |

## Evidence (real runs)
- ngspice-47 executed from `.tools/ngspice/Spice64/bin/ngspice_con.exe`.
- SKY130 NFET W=1 um, L=0.18 um, T=27 C, VDS=1.8 V, VGS 0..1.8 V: 91 points, validated (row count, finite, monotonic sweep, endpoints). Id rises from ~20 fA at VGS=0 to ~0.43 mA at 1.8 V.
- Failure path exercised for real: missing include file is detected and reported as MISSING_INCLUDE (not hidden); a real 0.01 s timeout returns TIMEOUT in ~0.03 s and leaves no stray process.
- Physics sanity (real runs, `scripts/sanity_probe.py`): Ion(W=2)/Ion(W=1)=2.17 and Ion(W=4)/Ion(W=1)=4.14 (binned model, not exactly linear); Ion falls with L (4.3e-4 -> 2.8e-4 -> 1.3e-4 A for L=0.18/0.36/1.0); Ion falls with T (4.9e-4 / 4.3e-4 / 3.7e-4 A at -40/27/125 C) while subthreshold Id at 0.45 V rises ~280x from -40 to 125 C; Id-Vd (VGS=1.2) starts at ~0, increases monotonically, slope falls from 4.4e-4 to 2e-5 S (saturation).
- **Bug found and fixed (Stage 1 hardening):** ngspice default gmin=1e-12 S put a gmin*VDS = 1.8 pA floor under every current, so IOFF at 27 C measured the solver, not the device (1.82 pA vs true ~20.9 fA; at -40 C 1.81 pA vs ~10 fA). Fixed with explicit `.option gmin=1e-18 abstol=1e-18` in every netlist, recorded in run provenance; results are stable down to gmin=abstol=1e-20, reltol=1e-6 (`scripts/gmin_probe.py`). Regression-tested.
- Tests: 77 passed (11 real-ngspice integration tests, confirmed run).

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
