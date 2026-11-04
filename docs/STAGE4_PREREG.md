# Stage 4 pre-registration: uniform vs curvature sampling (E3 / H4)

Written and committed BEFORE any E3 result exists. Changing anything below after the held-out run is an amendment and must be logged at the bottom.

## Question (H4)
At the same number of simulated points N, does curvature-placed sampling extract MOSFET measurements closer to a dense reference than uniform sampling, or reach a given accuracy with fewer points? A null or negative result is reported as such.

## Strategies (identical ngspice mechanism: explicit-point PWL sweep, decision D-S4-1)
- **U** `uniform_pwl`: N evenly spaced points over VGS 0..1.8 V, one process.
- **C** `curvature`: pilot of ~`pilot_frac` x N uniform points plus the forced bias points (VGS=1.8 for ION, VGS=0 for IOFF), then the remaining points placed by greedy bisection on a cubic-spline model of log10(Id) (indicator h^2 max|f''|), two processes. Total simulated points == N for both.

## Device and conditions
SKY130 `sky130_fd_pr__nfet_01v8`, tt corner, Id-Vg, VDS = 1.8 V, VBS = 0, VGS 0..1.8 V. Measurements: VTH, SS, GM, ION (at 1.8 V), IOFF (at 0 V). 18 conditions = product of W in {0.42, 1, 5} um, L in {0.15, 0.5} um, T in {-40, 27, 125} C in lexicographic order (W slowest). **Tuning conditions** = those with index % 4 == 0 (5 conditions: temperatures -40/27/125/-40/27, W 0.42/0.42/1/5/5, L 0.15/0.5/0.15/0.15/0.5); **held-out conditions** = the other 13. The only tunable is `pilot_frac` in {0.2, 0.3, 0.4}; it is fit on tuning conditions only (argmin of mean over tuning conditions, N and measurements of error/tolerance, a failed extraction counting as 10). The held-out run is executed ONCE.

## Budgets
N in {12, 16, 20, 30, 50}.

## Reference and errors
Reference = the same extractors applied to a dense uniform sweep (step 1 mV, 1801 points, plain `dc VGS`). Strategies run through the PWL path; path noise vs plain dc is <= ~4e-4 relative in Id (measured), negligible against the tolerances below.
Error per measurement: VTH |dV| in mV; SS, GM, ION relative %; IOFF |log10(value/ref)| in decades. Tolerance: VTH 5 mV; SS 5 %; GM 5 %; ION 2 %; IOFF 0.05 decade. A measurement that fails to extract (honest refusal) counts as error = 10 x tolerance when the other strategy succeeded; both failing = tie (difference 0). Extraction-failure rate is reported separately.

## Pre-registered win criterion (held-out conditions only)
For each measurement, the paired difference d = err_U - err_C is formed per (condition, N). Pool over N, bootstrap over CONDITIONS (2000 resamples, seed 20261104) the median of d. **C wins a measurement** if the median is > 0 and the 95 % percentile CI excludes 0. **H4 is supported** if C wins >= 3 of the 5 measurements AND C's pooled extraction-failure rate <= U's. Otherwise H4 is **not supported** and is reported as a null/negative result. Also reported (descriptive, no threshold): per-N medians, crossover N, and N* = smallest grid N whose error is within tolerance (median over conditions, censored at ">50").

## Known limits stated up front
Single device family and corner; 13 held-out conditions (trend-level evidence only); GM is defined as the max finite-difference slope of the sampled curve so it depends on spacing by construction; the pilot uses 30 %-ish of the budget so very small N leaves little to place; Id-Vd not covered.

## Amendments
- 2026-11-04 (BEFORE any E3 run; no result existed): the split rule was changed from `index % 3` to `index % 4`. With the temperature axis having 3 values, `% 3` aliased onto T and would have put every tuning condition at -40 C and none of the held-out conditions there. Found by inspecting the generated split, not from data.
