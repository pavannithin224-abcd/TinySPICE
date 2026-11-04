# Risk Register

| # | Risk | Likelihood | Impact | Mitigation | Status |
|---|---|---|---|---|---|
| R1 | ngspice 47 / SKY130 setup inside project fails or is large | M | H | download only needed model files; report size first; smoke test | open |
| R2 | Local LLM too slow or weak on this CPU laptop (i5-1145G7, 15.7 GB RAM, no dGPU) | M | H | time 2-3 models before committing; mock for tests; optional free hosted row with approval | open |
| R3 | SKY130 device limits (provisional) wrong | M | M | verify against model card in Stage 1 before any range claim | open |
| R4 | Curvature sampling fails to beat uniform | M | L | report null result; it is still a finding | open |
| R5 | Small benchmark -> weak statistics | H | M | repeated trials; claim trends only | open |
| R6 | Weak LLM inflates guardrail benefit | M | H | report model with every number; add second model if possible | open |
| R7 | Novelty over-claimed | M | H | wording rule: combination, unverified; cite prior art | open |
| R8 | Schedule slip | M | H | gates + cut order | open |
| R9 | Accidental coupling to other project folders | L | H | self-contained `.tools/`; no outside paths in config | open |
