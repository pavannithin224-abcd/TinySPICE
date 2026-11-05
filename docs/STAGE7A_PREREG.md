# Stage 7a pre-registration: fixed-and-swept contradiction guard (written and frozen BEFORE any F4 output exists)

## Facts, stated honestly
In the shipping parser (default: stray fields rejected by the schema) the Stage-6b contradiction (B08) was rejected 3/3, because the model writes the fixed bias into the inapplicable field and the schema refuses it. The guard gap bites only (a) when a stray field is removed (prune / re-ask), or (b) if a model OMITS the fixed bias entirely and the omission-guards fail to notice. 7a measures this latent risk, repairs the guard phrasing coverage, and checks that nothing correct is lost. B05 (Stage 6b) was a flaw in my set and is withdrawn.

## Set
`tests/benchmark/group1_f4.json` (sha256 in `group1_f4.sha256`): 12 fixed-and-swept contradictions (8 Id-Vg, 4 Id-Vd; six Id-Vg and three Id-Vd phrasings), 8 truly-unstated-analysis requests, 20 valid controls whose wording legitimately contains "held / fixed / constant / kept / also" (these must NOT be blocked). Oracle-checked: 0 problems.

## Procedure
1. Freeze F4 (this commit). 2. Record the model's FIRST response once per (model, task, seed) with the CURRENT code (commit before the guard change); score arms V0 (default parse) and V0p (stray=prune) from it. 3. Change the guard (derived from B08 and the phrasing space, tested by unit tests only; NOT tuned on F4 outputs). 4. Replay the SAME recorded responses through the new code: V1 (default) and V1p (prune). No other model calls, no re-ask. Models: Qwen3.5-2B and 0.8B, temperature 0.2, seeds 0-2 (seeds are partly pseudo-replicates; analyse at task level, majority over seeds, and also report raw counts).

## Decision rule
The guard fix is ADOPTED iff, on both models: (a) contradictions accepted by V1 = 0 and by V1p = 0; (b) unstated-analysis accepted by V1/V1p <= V0; (c) ZERO correct extractions lost, i.e. no (task, seed) that V0 reproduced exactly is rejected or wrong under V1 (valid controls included). If (a) fails the gap is reported as a limitation; if only (c) fails the fix is reverted. Prune is NOT adopted in 7a regardless of the outcome; V1p is descriptive evidence for a later decision.

## Limits
I author the set and the fix, and I know the weakness (author bias); the fix comes after the set is frozen but I have seen the B08 phrasing; n = 12 contradictions; two phrasing families may not span real user language.

## Amendments
(none)
