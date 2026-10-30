# tau2-bench telecom through Downshift (2026-10-30)

First agent run end to end through the new proxy path: tau2-bench's own LLM agent, unmodified, with its model
calls routed through `downshift.proxy.ChatProxy` and graded by tau2's reward (`examples/tau2/`). Telecom test
split, 40 tasks; simulated customer Nemotron 3 Super with thinking off, temperature 0; Ollama Cloud; costs at
Token Factory list prices. **Super is the baseline** here.

| step | result |
|---|---|
| Super baseline, 40 tasks × 1 | 23/40 (57.5%), $3.74 ($0.09 per task), up to 50 agent calls per conversation |
| split | 24 optimization / 16 held out (seed 42) |
| plain Nano swap on the 12-task sample | 16.7% (Super 50% on the same tasks) |
| rewrites, rounds 1 and 2 (sample) | 25.0%, 33.3% (thinking on, temperature 0.6; round 2 added a self-check rule and two few-shot replies) |
| race, 12 unseen optimization tasks × 2 | swap 16/24, round 2 14/24, round 1 13/24 → **plain swap kept** |
| held-out, plain Nano swap, 16 tasks × 2 | pass^1 62.5%, pass^k 43.8%, 95% CI 45-77% |
| paired Δ vs Super baseline | +0.0 pp, 90% CI −18.8 to +18.8 → **inconclusive** |
| cost per task | Nano $0.016, Super $0.089 (82% lower) |
| optimization spend | about $7 at list prices (Ollama) |

Reading:

1. **The proxy path works**: no line of tau2 was changed, every agent call was recorded, costed and replayable,
   and the optimizer ran its full loop on an agent whose tools change state.
2. **No gap to recover on these tasks.** The swap's 16.7% on the first 12 tasks became 67% (16/24) on the next 12
   and 62.5% on the held-out 16: the early number was noise. NVIDIA's model cards report Nano 42.2 vs Super 64.4
   on this domain; with 16-40 tasks and a single baseline run per task our numbers cannot confirm or refute that.
3. **Downshift's verdict is the right one for the evidence**: it kept the plain swap (the rewrites did worse in
   the race) and reported "inconclusive" rather than a pass, because the interval is ±19 points.
4. **Telecom is too expensive and noisy for a decisive test at this size.** A 10-point claim needs on the order of
   100-200 tasks; the domain has 40 test and 74 train tasks, and each Super conversation costs about $0.09. The
   test-plus-train set (114 tasks) with two trials would cost about $25-30 at list prices.
