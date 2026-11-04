# Project Charter — TinySPICE

**Title:** TinySPICE: A Budget-Aware and Reliability-Driven LLM Agent for Reproducible MOSFET Characterization
**Deadline:** 2026-11-30 (started 2026-11-04)  **Owner:** Pavan D

## One-sentence idea
A user describes a MOSFET characterization in English; TinySPICE validates it, plans it inside hard budgets, runs real ngspice, extracts measurements, recovers from named failures within limits, and stores a reproducible record, ending in an honest status.

## Scope (in)
DC characterization of one device family: SKY130 `sky130_fd_pr__nfet_01v8`. Id-Vg first; Id-Vd/GDS, PMOS, temperature sweeps only if time allows.

## Scope (out)
Transient/circuit simulation, other PDKs, GUI/dashboard, measured-silicon accuracy claims, training or fine-tuning an LLM.

## Central research question
Can a structured LLM agent orchestrate MOSFET characterization more reliably and efficiently than direct, unstructured LLM-to-tool execution while maintaining reproducible results?

## Contribution (claimed only after measurement)
The *combination* of: hard budget enforcement; bounded recovery from named ngspice faults; six-state honest status; adaptive sampling scored against a dense reference; replayable provenance; and a benchmark (TinySPICEBench) comparing three configurations. Components alone are NOT novel (see RESEARCH_PROBLEM.md prior art).

## Non-negotiables
No fabricated results. No paid API without explicit approval. No hidden network calls. No secrets in Git. Self-contained: nothing read from other project folders; CellWise-X/IVForge is never touched.

Status legend used across all docs: **IMPLEMENTED** (code exists) · **MOCK-TESTED** · **NGSPICE-TESTED** · **VERIFIED** (checked against independent reference) · **NOT IMPLEMENTED**.
