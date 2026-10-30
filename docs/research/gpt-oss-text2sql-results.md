# Another family: gpt-oss 120B to 20B on text2sql (2026-10-30)

Same agent, tasks, split (seed 42: 144 optimization, 96 held out), settings and grader as Phase 1, with the
baseline recorded on gpt-oss 120B and the target `model:gpt-oss-20b` (project `text2sql-oss`, optimization
`opt_b7b120b707e9`). Ollama Cloud; costs at list prices (gpt-oss 120B at Token Factory's $0.15/$0.60, 20B at the
OpenRouter median $0.03/$0.145).

| step | result |
|---|---|
| gpt-oss 120B baseline, 240 tasks | 190/240 (79.2%), $0.49 in total |
| plain 20B swap on the 20-task sample | 70% (baseline 80%) |
| rewrites, rounds 1-3 (sample) | 85%, 70%, 70%; round 1 switched on the SDK final-format repair by itself |
| race, 30 unseen tasks × 2 | rounds 3 and 2: 40/60, round 1: 37/60, plain swap: 36/60 → round 3 kept |
| held-out, chosen 20B harness, 96 tasks × 3 | pass^1 69.8%, pass^k 55.2%, 95% CI 64.3-74.8% |
| paired Δ vs 120B baseline (76.0% on these tasks) | −6.3 pp, 90% CI −12.2 to −0.3 → **inconclusive** at 10 pp |
| paired Δ vs plain 20B swap | +2.1 pp, 95% CI −2.8 to +6.6 → **undecided** |
| cost per task | 20B $0.0004, 120B $0.0018 (78% lower) |

Reading: on this family the plain swap loses less (about 8 points) than Nano does against Ultra, and the
optimizer's rewrite recovers about 2 points, within noise. The rewriter used the new repair switch unprompted,
and the race picked a rewrite over the swap by 40 to 36 task-trials, a margin that did not survive the held-out
set. So the Nemotron result does not generalize to this pair: here, a Downshift user would be told "the swap
costs about 6 points and the rewrite does not clearly help", which is what the data say.
