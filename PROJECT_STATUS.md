# TinySPICE — Project Status

_Last updated: 2026-11-04_

Status legend used across all docs: **IMPLEMENTED** (code exists) · **MOCK-TESTED** · **NGSPICE-TESTED** · **VERIFIED** (checked against independent reference) · **NOT IMPLEMENTED**.

## Today
- Renamed SiliconOps -> TinySPICE (dir, package, docs). 32 tests pass after rename.
- Stage 0 docs written (11 docs + README).
- Owner approved: self-contained downloads (ngspice 47 + SKY130 NFET models) into `.tools/`; LLM shortlist timing.

## Components
| Component | Status |
|---|---|
| schemas (spec, device limits, status) | IMPLEMENTED, MOCK-TESTED |
| planner | IMPLEMENTED, MOCK-TESTED |
| simulator, measurements, sampling, budget runtime, recovery, provenance, providers, agent, benchmark, CLI | NOT IMPLEMENTED |

## Environment
Windows 11, Python 3.14.7, venv `.venv`, pydantic 2.14.2, numpy 2.5.4, scipy 1.18.1, pandas 3.1.0, pytest 9.2.0. i5-1145G7 (4C/8T), 15.7 GB RAM, Iris Xe, no discrete GPU.
ngspice: **not yet installed inside TinySPICE**. Model files: none yet.

## Blockers
None. Device limits are provisional (unverified).

## Next
1. Install ngspice 47 + SKY130 NFET models into `.tools/`; smoke test.
2. Netlist generator + safe ngspice runner + mock simulator.
3. First real Id-Vg run with provenance fields.

## Schedule
Realistic if gates hold; see `docs/DEVELOPMENT_ROADMAP.md`.
