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
| 2026-11-04 | Metrics and tasks frozen by Nov 23, before final run | prevents benchmark tuning |
