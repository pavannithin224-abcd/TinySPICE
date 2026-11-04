# Stage 4 confirmatory pre-registration: does window sampling fix SS extraction at small budgets?

Written and committed BEFORE the confirmatory run. The run executes once. Anything changed after it is an amendment logged at the bottom.

## Why this exists
In the Stage-4 held-out run (docs/STAGE4_PREREG.md) the pre-registered H4 was NOT supported for either arm. The one practically large effect, window sampling raising SS-extraction success at N = 16-20, was found after inspecting tuning data and was not captured by the pooled-median rule, so it is EXPLORATORY. This run tests it as a single, narrow, pre-specified claim on conditions never used before.

## Claim under test
At small point budgets (N = 16 and N = 20), measurement-aware `window` sampling extracts the subthreshold swing successfully (the extractor does not refuse) more often than `uniform_pwl` sampling with the same number of simulated points.

## Fixed design (nothing is tuned here)
- Arms: `uniform_pwl` (U) and `window` (W) only. W parameters frozen from the earlier tuning: `pilot_frac = 0.4`, `window_target = 5`.
- Device/protocol as in STAGE4_PREREG.md: SKY130 `sky130_fd_pr__nfet_01v8`, tt, Id-Vg, VDS = 1.8 V, VGS 0..1.8 V, ION at 1.8 V, IOFF at 0 V, same extractors, same dense 1 mV reference.
- **Fresh conditions (disjoint from the 18 used before): 12 = W in {0.84, 2.0, 10.0} um x L in {0.25, 1.0} um x T in {0, 85} C.** All inside the verified model bins (W 0.36-100, L 0.15-100) and the conventional temperature range.
- Budgets run: N in {12, 16, 20, 30, 50}. **Primary analysis uses N in {16, 20} only (24 paired cells)**; this restriction is justified by the exploratory result and is disclosed here, not hidden.

## Primary endpoint and decision rule (pre-specified)
Per (condition, N) pair, SS "success" = the SS extractor returned a value (did not refuse). Let `d_W` = number of discordant pairs where W succeeded and U failed, `d_U` = the reverse.
**The claim is CONFIRMED if and only if BOTH hold:**
1. pooled success rate(W) - success rate(U) >= +0.30 (absolute) over the 24 pairs, and
2. exact one-sided binomial sign test on discordant pairs, P(X >= d_W | n = d_W + d_U, p = 0.5) < 0.01.
Otherwise it is **NOT confirmed** and the earlier finding stays exploratory/withdrawn.

## Secondary (descriptive, no threshold decides the claim)
SS success by N for all five N; SS accuracy when both arms succeed (median |error| in %); the cost side: VTH and GM error (median W minus U) at all N, with a pre-stated "acceptable cost" of at most 0.5 x tolerance (VTH 2.5 mV, GM 2.5 %) in the median; extraction-failure rate over VTH/SS/GM.

## Known limits stated up front
One device family and corner; 12 conditions; the W arm is coupled to the SS extractor's window definition; no claim about Id-Vd or other devices; if W succeeds only because it reads the extractor's own definitions, that coupling is the finding, not a flaw to hide.

## Amendments
(none)
