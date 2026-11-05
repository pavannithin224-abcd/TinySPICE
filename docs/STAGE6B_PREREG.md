# Stage 6b pre-registration: bounded LLM re-ask (DRAFT, awaiting approval; no code written)

## Motivation (from the frozen TinySPICEBench run, 2B row)
Configuration C lost 10 of 72 runs (completion 0.86), all on valid requests, all rejected by the strict spec for a STRAY FIELD the model should have left null: `ion_vgs_v` without ION (T07), `vgs_v` on an Id-Vg sweep (T13, T18), and once an unstated `sweep_step` (T16). C reported honest rejections, never wrong results. Question: can ONE bounded re-ask recover these without weakening the guarantees?

## Hypothesis
H-R: a single deterministic re-ask raises exact-match recall on valid requests by >= 0.05 absolute, with zero new silent-wrong specs and no increase in accepted bad requests.

## Arms (same model, same recorded first response; arms differ only after the first response)
- **R0 (current C parse):** strict interpreter, one FORMAT repair only. Baseline.
- **R1 (deterministic prune):** the existing `prune` mode: drop-and-log fields that are inapplicable to the requested measurements/analysis. No second LLM call. Included because a non-LLM fix must be beaten before an LLM call is justified.
- **R2 (re-ask):** if and only if validation fails with a RE-ASKABLE error, send the model its own output plus the exact validator message once, and re-validate the new output through the identical strict pipeline (grounding, coverage, guards unchanged).

## What is re-askable (frozen list)
Only errors of class STRAY/INAPPLICABLE FIELD: a bias given that the chosen measurements or analysis do not use (`ion_vgs_v`/`ioff_vgs_v` without ION/IOFF; `vgs_v` on Id-Vg; `vds_v` on Id-Vd) and step-AND-points both set. NEVER re-asked: missing required values, values not found in the request (grounding failures), contradictions in the request, device-limit/budget rejections. At most ONE re-ask per request; the re-ask output must pass every check R0 applies. No loop.

## Fresh task set (written and frozen with a sha256 BEFORE any run; none of F1-F3 or the 24 bench tasks reused)
40 requests: 28 valid (varied measurement sets, both analyses, unit forms, distractor text; at least 10 designed to tempt a stray-field mistake: ION/IOFF without a bias value, Id-Vg with a stated VDS) and 12 bad (missing parameter, contradiction, ungrounded budget, out-of-range), each with gold flat extraction or expected rejection. Oracle-checked by `verify_set.py` before freezing. Models: Qwen3.5-2B (primary), 0.8B (secondary). Temperature 0.2, seeds 0, 1, 2 -> 120 requests per model per arm. First responses recorded once and shared by all arms.

## Metrics (per arm)
exact-match recall on valid requests; silent-wrong rate (accepted spec differing from gold); bad-request acceptance rate; re-ask rate and re-ask success rate; latency added; R1 prune log (what was dropped).

## Decision rule (primary: 2B)
R2 is SUPPORTED iff ALL: (a) exact-match(R2) - exact-match(R0) >= 0.05; (b) one-sided exact sign test on discordant (request, seed) pairs p < 0.05; (c) silent-wrong(R2) <= silent-wrong(R0) and bad-accepted(R2) <= bad-accepted(R0); (d) not dominated by R1: if R1 achieves the same recall (within 0.02) with no LLM call, the headline is "deterministic prune suffices" and R2 is dropped from the system. Otherwise NOT supported and reported as such; the system keeps R0. Secondary: same comparison for R1 vs R0, and the 0.8B row, descriptive.

## After the result
If the winner changes the system, TinySPICEBench is NOT re-scored against the frozen run; instead its first responses are replayed through the new parse as a clearly labelled post-hoc row (descriptive, not a replacement for the frozen result).

## Known limits stated up front
I author the fresh set and the arms (author bias, mitigated by freeze + oracle check); 28 valid requests is small; stray-field errors are what I observed, so the re-askable list was derived from the benchmark failures (the fresh set is what tests it); one device family.

## Amendments
(none)
