# TinySPICE — Project Status

_Last updated: 2026-11-06 (Stage 7 in progress). Deadline 2026-11-30._

Labels: **IMPLEMENTED** (code exists) · **MOCK-TESTED** · **NGSPICE-TESTED** · **VERIFIED** (independent reference or pre-registered experiment with committed raw results) · **NOT IMPLEMENTED**.
Reproduce everything reported here: `python scripts/reproduce.py all` (18 checks; passes from a fresh clone). Full test suite: 269 passed (unit + integration with real ngspice).

## Stage progress
| Stage | State |
|---|---|
| 0 Foundation | DONE |
| 1 Simulator core (ngspice 47 + SKY130 NFET in `.tools/`) | DONE; hardened (gmin/abstol leakage artefact fixed: IOFF 1.82 pA -> 20.9 fA) |
| 2 Measurement engine (ID, GM, GDS, VTH, SS, ION, IOFF) | DONE; VERIFIED on analytic curves and real data |
| 3 English -> spec (local llama.cpp: Qwen3.5 0.8B/2B, SmolLM2 135M/360M) + deterministic guardrails | DONE with limits. F3 (untainted): 2B = 7/20 exact, 0/21 bad requests accepted (raw: 4 silent-wrong, 7/21 accepted). Safe; recall about 35 % |
| 4 Adaptive sampling | DONE. Curvature sampling NOT SUPPORTED (null). Window sampling for SS CONFIRMED: 24/24 vs 4/24, p = 1e-6, one device family |
| 5 Reliability + provenance | DONE. Budget ledger, recovery catalogue, six-state status, SQLite provenance, replay/verify, CLI. 20/20 pre-registered injection cases. Convergence cure verified only against an injected fault; no physical non-convergence could be provoked (24 hostile runs) |
| 6 TinySPICEBench | DONE (one frozen run, 2B): false success A 30/72, B 9/72, C 0/72; completion 0.50 / 0.46 / 0.86. Task-level sign test A-only 10, C-only 0, p = 0.001 (seeds are mostly pseudo-replicates, so the task-level p is the honest one). Oracle row: A 0.42 false success, B and C 0 |
| 6b Bounded LLM re-ask | NOT SUPPORTED (safety condition failed on a contradiction after field removal); system keeps the plain parser |
| 7a Fixed-bias guard gap | DONE: contradictions accepted under prune 5/36 -> 0/36 (2B), 6/36 -> 0/36 (0.8B); 0 correct extractions lost |
| 7b README, 7c reproduction + fresh-clone gate | DONE (18/18 from a clean clone after one CRLF defect was found and fixed) |
| 7d Figures + demo | DONE |
| 7e Report + one-page summary | DONE (`docs/REPORT.md`, `docs/SUMMARY.md`) |

## Components
| Component | Status |
|---|---|
| schemas, planner (device limits, point/tool-call budgets) | NGSPICE-TESTED |
| simulator: netlists, safe runner, output validation, error classification; mock with fault injection | NGSPICE-TESTED |
| NMOS Id-Vg and Id-Vd on SKY130 `nfet_01v8`, `tt` corner | NGSPICE-TESTED (physical trends checked; not validated against silicon) |
| measurements | VERIFIED (analytic + scipy cross-check) |
| parser providers (rules floor, scripted, llama.cpp), strict interpreter, grounding / coverage / omitted-bias / omitted-limit / conflict guards | IMPLEMENTED; guards VERIFIED on pre-registered sets |
| sampling (uniform, curvature, window) | NGSPICE-TESTED; window VERIFIED, curvature null |
| budget ledger, recovery, status machine, provenance, replay, CLI (`plan run ask replay verify runs`) | NGSPICE-TESTED |
| benchmark harness, baselines A/B/C, independent scoring | VERIFIED (frozen run) |
| PMOS and other devices/PDKs, non-Windows platforms | NOT IMPLEMENTED |

## Evidence worth keeping (real runs)
- SKY130 NFET W = 1 um, L = 0.18 um, 27 C, VDS = 1.8 V: VTH 0.596 V, SS 81.6-82.7 mV/dec, GM 0.485 mS (max at the sweep edge, flagged), ION 431.5 uA, IOFF 20.9 fA.
- Bug found and fixed in Stage 1: ngspice default gmin = 1e-12 S put a 1.8 pA floor under every current, so IOFF measured the solver. Fixed with `.option gmin=1e-18 abstol=1e-18` in every netlist; regression-tested.
- Bug found by the fresh-clone gate (Stage 7c): git `autocrlf` rewrote the frozen sets and broke their sha256; fixed with `.gitattributes`.

## Known limitations
- One author wrote the tasks, system and baselines (author bias; mitigated by freezing and pre-registration). n = 24 tasks, one device family, one corner (`tt`), one platform.
- All three benchmark configurations share the measurement code: the benchmark isolates orchestration, not extraction.
- Small-model parse recall is low; the guards trade recall for safety.
- Voltage and temperature device limits are conventions (`limits_verified=false`); geometry limits verified from the model bins.
- Physical non-convergence recovery never exercised.
- Prior art: LLM + SPICE is not new (AnalogAgent, arXiv 2603.23910, others); claimed contributions are the narrower ones listed in the README.
- 7zr.exe has no published checksum (hashed after download); SKY130 files are pinned by upstream commit.

## Environment
Windows 11, Python 3.14.7, venv `.venv`. Third-party tools in `.tools/` (git-ignored): ngspice 47, SKY130 NFET model files, llama.cpp b12102, GGUF models. `.gitattributes` pins LF on frozen sets.

## Next
7d figures (script-generated from committed raw results) and demo capture; 7e technical report (~6 pages) plus one-page summary. Pending the user: public GitHub push, write-up format.
