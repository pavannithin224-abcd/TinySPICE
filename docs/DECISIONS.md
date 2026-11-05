# Decisions

| Date | Decision | Why |
|---|---|---|
| 2026-11-04 | Name changed SiliconOps -> TinySPICE | owner choice |
| 2026-11-04 | Self-contained: everything (ngspice, PDK, models, LLM runtime) installed inside the TinySPICE folder; no reads from other projects | owner order |
| 2026-11-04 | Use pretrained LLMs; no training or fine-tuning (optional LoRA ablation only if time remains) | 26 days, CPU-only, no data; guardrails must carry the result |
| 2026-11-04 | LLM shortlist to time locally: Qwen3.5 small, Phi-4-mini, SmolLM3-3B | owner approved |
| 2026-11-04 | No paid API; no hosted API without explicit approval | owner order |
| 2026-11-04 | CLI-first; no dashboard; FastAPI optional | schedule |
| 2026-11-04 | PDK: SKY130 `nfet_01v8` (real PDK, not an educational model) | open, ngspice-compatible |
| 2026-11-04 | Defaults vbs=0, vth_ic=1e-7*W/L, max_retries=2, max_runtime=300s, max_tool_calls=20 | conventional; always echoed in plan |
| 2026-11-04 | Never coarsen a sweep to fit a budget; reject instead | honesty over convenience |
| 2026-11-04 | License MIT (provisional) | owner has not specified |
| 2026-11-04 | Explicit `.option gmin=1e-18 abstol=1e-18` in every netlist (profile field `solver_options`, echoed in provenance) | ngspice defaults put a gmin*VDS = 1.8 pA floor under IOFF; measured 100x error at 27 C; stable down to 1e-20 |
| 2026-11-04 | Valid simulation without measurements ends PARTIAL, never SUCCESSFUL | SUCCESSFUL requires validated output AND successful extraction |
| 2026-11-04 | GDS defined at the last Id-Vd sweep point; GM defined as max dId/dVGS; SS window = Ic/1e3..Ic with R^2 >= 0.995 gate | spec has no bias for GDS/GM/SS; deterministic, documented, refuses rather than guesses |
| 2026-11-04 | SUCCESSFUL only if every requested measurement succeeds; some fail -> PARTIAL; all fail -> FAILED | honest-status rule |
| 2026-11-04 | Metrics and tasks frozen by Nov 23, before final run | prevents benchmark tuning |

## D-S4-1 Non-uniform sweep points (Stage 4, 2026-11-04) - VERIFIED on real ngspice-47
Question: can ngspice sweep an arbitrary list of gate voltages? Spikes: scripts/spike_dc_list.py, scripts/spike_dc_pwl.py.
- `dc VGS LIST v1 v2 ...` does NOT exist for the dc command: "Error: Bad syntax" for every variant; a 200-value dc line also crashed the process (exit 0xC0000409). Rejected.
- CHOSEN (primary): sweep an integer index source `VIDX idx 0 0` with `dc VIDX 0 N-1 1` and drive the gate with a behavioral source `BGS g 0 V = pwl(v(idx), 0,v0, 1,v1, ...)`, written with `+` continuation lines. Measured: 2, 5, 15 and 200 arbitrary points all returned exactly N rows with gate values equal to the requested ones (atol 1e-9), ~0.7 s each, one process. Id at points shared with a plain uniform sweep agrees to <= 3.6e-4 relative (default reltol 1e-3 path noise; ~0.01 mV of VTH), so uniform and adaptive strategies will BOTH be run through the same PWL path to keep the comparison fair.
- FALLBACK (works, not used): piecewise-uniform sub-sweeps, several `dc` + `wrdata raw<k>.dat` inside one control block (3 segments -> 4+9+5 rows in one process).
- Cost model: a two-phase adaptive run = 2 ngspice processes (pilot, then refinement of ONLY the new points) = 2 tool calls; total simulated points = pilot + refinement <= budget.

## Stage 5 decisions (2026-11-04) - approved by the user unless noted
- D-S5-1 `budget.max_runtime_s` is the TOTAL wall-clock deadline for the whole run, retries included (was a per-process timeout). First process timeout = min(remaining - margin, 0.4 x total); each timeout-retry doubles it.
- D-S5-2 Wall-clock safety margin max(0.1 s, min(2 s, 2 % of the limit)): killing a subprocess takes a few ms, so a timeout of exactly "what is left" overshot (0.318 s recorded against a 0.3 s limit in injection case I09). No process may start inside the margin. Found by the pre-registered invariant; the test was not relaxed. 10/10 stable repeats.
- D-S5-3 Recovery may change only iteration limits (itl1/itl2/itl4) and the integration method; gmin/abstol/reltol can never be changed (whitelist enforced in code and tested), because changing them re-creates the Stage-1 IOFF artefact.
- D-S5-4 Measurement-level recovery: an SS refusal for lack of points (WINDOW_TOO_NARROW / INSUFFICIENT_POINTS) with points left in the budget triggers one window-targeted refinement (Stage-4 method); success => RECOVERED.
- D-S5-5 points budget limits the FINAL dataset; failed attempts cost tool calls / retries / wall-clock, not points. Persistence has one tool call RESERVED up front.
- D-S5-6 Unaccounted fault can never end SUCCESSFUL: `final_status` maps (fault with no recovery) to FAILED. Found by the exhaustive truth-table test on its first run.
- D-S5-7 BUG FIXED: a `points`-based uniform dc sweep with a non-representable step (1.8/49) returned 49 rows for 50 planned (ngspice drops the last point). The validator caught it. Fix: dc stop nudged up by 0.1 % of a step. Regression test on real ngspice for N = 50/37/91/17.
- D-S5-8 HONEST LIMIT: injected NONCONVERGENCE is real in classification (a voltage-source loop gives a genuine ngspice DC failure) but its cure is synthetic (the fault is withdrawn once a solver override is applied). Whether the ladder cures a PHYSICAL convergence failure is NOT tested; no natural one exists for this device.
- Deferred (user-approved): LLM re-ask on a deterministic error and the H13 stated-limit extraction bug -> a later pre-registered sub-stage with a fresh test set.

## Pre-Stage-6 hardening (2026-11-04)
- D-H13 FIXED: stated tool-call / retry / runtime limits must be extracted (the schema used to apply its default silently: "at most 4 tool calls" -> 20) and the value must sit next to ITS OWN keyword (cross-field swaps blocked). Minutes/seconds are understood by numeric grounding (found by a held-out control that blocked a correct "within 2 minutes" -> 120 s; fixed after the first shot and disclosed). Held-out phrasing check: recall 12/14 (the 2 misses are vocabulary: "limited to 90 sec", "invocations"), expected SAFE false blocks on 2/2 adversarial distractors ("3 attempts last week"). No perfect extraction blocked across dev/frozen/F2/F3 (~93 tasks). On the saved 2B F3 outputs the one remaining silent wrong spec became a safe rejection (descriptive: F3 is tainted for this fix).
- D-S5-9 NATURAL CONVERGENCE FAILURE: not found. 24 hostile SKY130 runs (T -100..500 C, VDS 3..20 V, VBS -8..+2 V, W 0.36..100 um, L 0.15..100 um, VGS to 10 V) ALL converged (23 s). The only failure was W = 1000 um -> MODEL_NOT_FOUND (outside the bins; correct config-fault classification). Consequence: the solver-ladder cure stays UNTESTED on a physical failure (the Stage-5 limit stands, now with evidence that none is easy to provoke on this device's DC sweep).
- D-S5-10 NOTE: ngspice returns ok=True rows for physically absurd conditions (500 C, VDS 20 V). Physical validity is guaranteed ONLY by the planner's device limits, never by the simulator succeeding. Do not remove or loosen the planner checks.

## Stage 6b result (2026-11-05): bounded re-ask NOT SUPPORTED; system keeps R0
Frozen fresh set R1 (28 valid + 12 bad) x 3 seeds, Qwen3.5-2B: exact R0 56/84 (0.667), R1 prune 61/84 (0.726), R2 re-ask 60/84 (0.714). R2 gain +0.048 (< 0.05), sign p = 0.0625 (> 0.05), and SAFETY FAILED: bad requests accepted rose 2 -> 4 (R1) and 2 -> 5 (R2). All new accepts are task B08 (the contradiction "VGS held at 0.7 V while VGS is swept"): the model fills `vgs_v` (the evidence of the contradiction); stripping or re-asking that stray field erases the evidence, and the omitted-bias / conflict guards did NOT fire on this phrasing ("... is also held at ..."), so a contradictory request became a valid spec. This is the exact failure the unit test `test_prune_cannot_hide_a_stated_contradiction` covers for the canonical phrasing, but real model output plus a new phrasing slipped through: a guard gap. R1 beat R0 (+5 exact, p = 0.031) but is rejected on the same safety ground; R2 never beat R1 (0 R2-only wins), so no LLM re-ask is justified either way. 0.8B: 3/84 in all arms (no effect). Separate pre-existing hole found: B05 (analysis unstated, "A sweep") is ACCEPTED by R0 in 2 of 3 seeds (the model fills analysis from nothing). Not fixed here: the fresh set has been seen, so any guard fix needs a new untainted set. Decision: R0 stays the system; recall limit (about 0.67 on valid requests, 2B) is reported as is.
