# Phase 1 results: numbers a reader can trust (2026-10-30)

Setup: the text2sql task set grew from 40 to 240 Spider dev questions (the original 40 unchanged, 200 added
with seed 43; all 1034 dev questions run locally). The Ultra baseline for the 200 new tasks was recorded on
Ollama Cloud (147 of 200 passed, 73.5%, $3.25 at Token Factory list prices, 37 minutes at concurrency 3).
The engine now replays every held-out task several times, replays the plain swap on the same held-out
tasks, reports Wilson and paired bootstrap intervals, applies a non-inferiority bar (lower 90% bound of the
paired difference above −10 points; "inconclusive" when only the point estimate is) and races the two best
candidates against the swap on unseen optimization tasks before choosing.

Optimization settings: seed 42 split of 240 recorded runs into 144 optimization and 96 held-out tasks;
20-task sample per round, 3 rounds; race on 30 unseen optimization tasks × 2 trials; held-out 96 tasks × 3
trials; provider Ollama Cloud; costs at Token Factory list prices.

## Super (`opt_6912a11081d9`)

| stage | result |
|---|---|
| plain swap on the 20-task sample | 80% (= Ultra's 80% on the same tasks) |
| rewrite rounds 1-3 on the sample | 75%, 75%, 80% |
| race (30 unseen tasks × 2): round-3 rewrite vs plain swap | 45/60 vs 44/60 task-trials; round-3 kept |
| held-out, 96 tasks × 3 trials, rewrite | pass^1 72.9%, pass^k 66.7%, 95% CI 67.5-77.7%; per trial 68, 72, 70 of 96 |
| held-out, plain swap, same tasks × 3 | pass^1 71.2%; per trial 66, 71, 68 of 96 |
| Ultra baseline on the same 96 tasks (recorded) | 70.8% (68 of 96) |
| paired Δ vs baseline | +2.1 pp, 90% CI −2.1 to +6.9 → **non-inferior within 10 pp** |
| paired Δ vs plain swap | +1.7 pp, 95% CI −1.4 to +5.2 → **undecided** |
| cost per task | rewrite $0.0058, swap about $0.006, Ultra $0.0105 (45% lower) |

Reading: Super is a safe replacement for Ultra on this agent, and the rewrite adds nothing the plain swap
does not already give (the interval of the rewrite-minus-swap difference straddles zero). Downshift's
verdict is correct, and the race chose the rewrite over the swap on a 45-to-44 margin that means nothing;
with the "ties go to the swap" rule one more swap pass would have returned the simpler harness. Three
held-out tasks are failed by Ultra and passed by the Super rewrite in all three trials; one is the reverse.

**Trials versus tasks.** On these 96 tasks, 85 (rewrite) and 87 (swap) gave the same outcome in all three
trials. The between-task variance of the pass probability is about 0.16-0.18 and the within-task variance
about 0.03-0.04 (intraclass correlation 0.81-0.85). So, as `evaluation-methodology.md` predicted, a second
or third replay of the same task buys little; adding tasks is what shrinks the intervals. With 96 tasks the
paired comparison can detect gaps of roughly 8 points (bootstrap SE about 2.7 pp); the 16-task version
could detect about 30.

## Nano

The first run of the Nano target was cut off by a process time limit during its race; it was rerun on the same
split (`opt_5bc68e612d06`). The plain swap scored 70% on the 20-task sample, rewrites 65% and 65% (one round
was lost to an invalid rewriter reply, since fixed), and the race (30 unseen optimization tasks × 2) kept the
plain swap: 44/60 task-trials against 35/60 for the round-3 rewrite. On the held-out set:

| | result |
|---|---|
| plain swap, 96 tasks × 3 trials | pass^1 61.1%, pass^k 39.6%, 95% CI 55.4-66.6% |
| paired Δ vs Ultra baseline | −9.7 pp (90% CI −15.6 to −3.8): **inconclusive** at the 10 pp margin |
| failure classes over 288 runs | 53 prose answers (no SQL), 47 wrong rows, 12 SQL errors |

In this run the optimizer did **not** produce a better Nano harness. Its rewrites bundled extra rules (a "check
enum values" step, a lower temperature) that the race correctly rejected, while the minimal format-rule rewrite
of round 2 was never raced: only the top two candidates by the small-sample objective were. The race now
includes every candidate.

## The Phase 0 harness on new tasks, and the SDK repair alone

Two more arms separate "the right harness exists" from "the optimizer finds it":

- the Nano harness Downshift wrote in Phase 0 (`phase0-harnesses/run1-opt_47da8d24f05c-nano.yaml`: thinking on,
  max_tokens 10000, temperature 0.6, one final-reply rule, two few-shot replies);
- the plain Nano swap with only the new SDK repair switched on (`final_format: "```sql"` and a one-sentence
  repair prompt, `phase0-harnesses/nano-swap-plus-sdk-repair.yaml`), with no prompt change at all.

**Cleanest comparison: the 80 held-out tasks drawn from the 200 new questions.** No rewrite was written on them
and no harness was selected on them. (The Phase 0 harness was chosen among three using fresh runs on the original
16 held-out tasks, which are excluded here.) The Ultra baseline is the recorded run per task.

| arm | tasks x trials | pass^1 | 95% CI | pass^k | paired delta vs Ultra baseline (90% CI) | verdict at 10 pp | delta vs Nano plain swap (95% CI) |
|---|---|---|---|---|---|---|---|
| Ultra baseline (recorded, Ollama) | 80 x 1 | 71.2% | 60.5-80.0% | - | +0.0 (+0.0 to +0.0) | reference | - |
| Ultra fresh (Token Factory) | 80 x 1 | 70.0% | 59.2-78.9% | - | -1.2 (-6.2 to +3.8) | non_inferior | - |
| Super, chosen rewrite (Ollama x3) | 80 x 3 | 72.1% | 66.1-77.4% | 66.2% | +0.8 (-3.8 to +5.4) | non_inferior | - |
| Super, plain swap (Ollama x3) | 80 x 3 | 70.0% | 63.9-75.4% | 66.2% | -1.3 (-5.8 to +2.9) | non_inferior | - |
| Super, chosen rewrite (Token Factory) | 80 x 1 | 72.5% | 61.9-81.1% | - | +1.2 (-5.0 to +7.5) | non_inferior | - |
| Nano, plain swap (Ollama x3) | 80 x 3 | 58.3% | 52.0-64.4% | 36.2% | -12.9 (-19.2 to -6.3) | inferior | - |
| Nano, plain swap (Token Factory) | 80 x 1 | 50.0% | 39.3-60.7% | - | -21.2 (-30.0 to -12.5) | inferior | - |
| Nano, swap + SDK repair (Ollama x3) | 80 x 3 | 65.4% | 59.2-71.1% | 55.0% | -5.8 (-11.7 to -0.0) | inconclusive | +7.1 (+0.0 to +13.8): undecided |
| Nano, Phase 0 harness (Ollama x3) | 80 x 3 | 70.4% | 64.4-75.8% | 56.2% | -0.8 (-6.7 to +4.6) | non_inferior | +12.1 (+5.0 to +19.6): better |
| Nano, Phase 0 harness (Token Factory) | 80 x 1 | 71.2% | 60.5-80.0% | - | +0.0 (-7.5 to +7.5) | non_inferior | +12.9 (+4.2 to +21.3): better |

All 96 held-out tasks (87 for the Phase 0 harness, leaving out the 9 its rewriter saw):

| arm | tasks x trials | pass^1 | 95% CI | pass^k | paired delta vs Ultra baseline (90% CI) | verdict at 10 pp | delta vs Nano plain swap (95% CI) |
|---|---|---|---|---|---|---|---|
| Ultra baseline (recorded, Ollama) | 96 x 1 | 70.8% | 61.1-79.0% | - | +0.0 (+0.0 to +0.0) | reference | - |
| Ultra fresh (Token Factory) | 96 x 1 | 71.9% | 62.2-79.9% | - | +1.0 (-3.1 to +5.2) | non_inferior | - |
| Super, chosen rewrite (Ollama x3) | 96 x 3 | 72.9% | 67.5-77.7% | 66.7% | +2.1 (-2.4 to +6.6) | non_inferior | - |
| Super, plain swap (Ollama x3) | 96 x 3 | 71.2% | 65.7-76.1% | 67.7% | +0.3 (-4.2 to +4.9) | non_inferior | - |
| Super, chosen rewrite (Token Factory) | 96 x 1 | 72.9% | 63.3-80.8% | - | +2.1 (-3.1 to +8.3) | non_inferior | - |
| Nano, plain swap (Ollama x3) | 96 x 3 | 61.1% | 55.4-66.6% | 39.6% | -9.7 (-15.6 to -3.8) | inconclusive | - |
| Nano, plain swap (Token Factory) | 96 x 1 | 52.1% | 42.2-61.8% | - | -18.8 (-27.1 to -10.4) | inferior | - |
| Nano, swap + SDK repair (Ollama x3) | 96 x 3 | 67.7% | 62.1-72.8% | 57.3% | -3.1 (-8.3 to +2.4) | non_inferior | +6.6 (+1.0 to +12.5): better |
| Nano, Phase 0 harness (Ollama x3) | 87 x 3 | 71.3% | 65.5-76.4% | 57.5% | +1.1 (-4.6 to +6.9) | non_inferior | +11.1 (+4.2 to +18.0): better |
| Nano, Phase 0 harness (Token Factory) | 87 x 1 | 70.1% | 59.8-78.7% | - | +0.0 (-6.9 to +6.9) | non_inferior | +10.0 (+1.1 to +18.4): better |

Cost per task at Token Factory list prices: Ultra $0.0116, Super rewrite $0.0034, Nano plain swap $0.0013,
Nano Phase 0 harness $0.0011-0.0014, Nano swap with the SDK repair $0.0023. The repair fired on 34 of 288
runs (12%).

## Reading it without bias

1. **The case the project needed now exists, on fresh tasks and two providers.** On 80 tasks no rewrite or
   selection touched, the Downshift-written Nano harness is non-inferior to Ultra (paired Δ −0.8 pp, 90% CI −6.7
   to +4.6 on Ollama; +0.0, −7.5 to +7.5 on Token Factory) and beats the plain Nano swap by about 12 points with
   the interval excluding zero (+12.1, 95% CI +5.0 to +19.6; +12.9, +4.2 to +21.3), at about a tenth of Ultra's
   cost. On the same 80 tasks the plain swap is inferior to Ultra on both providers (−12.9 pp on Ollama, −21.2 pp
   on Token Factory).
2. **The optimizer does not find it reliably.** That harness came from one of three Phase 0 runs and was
   picked by fresh runs on 16 other tasks; the Phase 1 run on the larger sample kept the plain swap. The
   ingredients are right every time (thinking on, a final-reply rule); which extras get bundled decides the result.
3. **The SDK repair alone helps, but less.** With no prompt change, the repair turn lifts the plain swap by
   about 7 points (+6.6 pp, 95% CI +1.0 to +12.5 on all 96 tasks; +7.1, 0.0 to +13.8 on the clean 80), at the
   cost of one extra short call on 12% of runs. Against Ultra that is non-inferior on the 96 tasks (−3.1 pp, 90%
   CI −8.3 to +2.4) but only inconclusive on the clean 80 (−5.8, −11.7 to 0.0). It recovers less than the
   Phase 0 harness, whose final-reply rule prevents most prose answers before a repair is needed.
4. **Super is a safe swap and the rewrite adds nothing.** Non-inferior on every check; rewrite minus swap
   +1.7 pp, interval straddling zero.
5. **Providers differ.** Nano's plain swap scored 61.1% on Ollama (3 trials) and 52.1% on Token Factory
   (1 trial) on the same tasks; Ultra, Super and the Phase 0 harness agreed across providers within a point or
   two. Claims about Nano's plain swap should name the provider.
6. **Ultra fresh on Token Factory reproduces the recorded baseline** (71.9% vs 70.8%, paired Δ +1.0): for
   text2sql, a replay (recorded tool results for identical SQL on a read-only database) and a fresh run measure
   the same thing, so the multi-trial held-out replays already are the fresh check here. The `verify` command
   remains for agents with live or state-changing tools.
