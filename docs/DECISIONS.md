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
