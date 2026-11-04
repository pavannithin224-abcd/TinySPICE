# TinySPICE

TinySPICE: A Budget-Aware and Reliability-Driven LLM Agent for Reproducible MOSFET Characterization

TinySPICE turns a plain-English MOSFET characterization request into a validated, budget-limited, fully recorded ngspice experiment.
The LLM only *interprets* the request. Planning, simulation, measurement and bookkeeping are deterministic code, so every number
comes from simulator output and every run ends in an honest status.

> Early development (deadline 2026-11-30). See `PROJECT_STATUS.md` for what actually works today.

## Status
Status legend used across all docs: **IMPLEMENTED** (code exists) · **MOCK-TESTED** · **NGSPICE-TESTED** · **VERIFIED** (checked against independent reference) · **NOT IMPLEMENTED**.

| Component | State |
|---|---|
| Experiment spec (Pydantic) | IMPLEMENTED, MOCK-TESTED |
| Deterministic planner | IMPLEMENTED, MOCK-TESTED |
| ngspice runner, measurements, sampling, recovery, provenance, LLM provider, benchmark | NOT IMPLEMENTED |

## Setup (Windows)
```
python -m venv .venv
.venv\Scripts\python -m pip install -e .[dev]
.venv\Scripts\python -m pytest -q
```
Third-party tools (ngspice, SKY130 models) live in `.tools/` inside this folder and are never committed.

## Docs
Start with `docs/PROJECT_CHARTER.md`, then `docs/SYSTEM_ARCHITECTURE.md` and `docs/TINYSPICEBENCH.md`.

## Naming
Formerly "SiliconOps" (renamed 2026-11-04). TinySPICE is the official name.
