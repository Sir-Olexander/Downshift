# Does the optimizer find the Nano fix reliably? Three repeat runs (2026-10-30)

After Phase 1 the optimizer got three changes: the race includes every candidate (not the top two by the
small-sample objective), the rewriter sees failures grouped by kind, and it is told to make the smallest change
that fixes the commonest kind instead of rules for single tasks. The SDK final-format repair was also available
to it as a harness switch. Then the Nano optimization on text2sql was run three times, unchanged otherwise:
240 tasks, seed 42 split (144 optimization, 96 held out), 20-task rounds × 3, race on 30 unseen optimization
tasks × 2 trials, held-out 96 tasks × 3 trials for both the chosen harness and the plain swap. Ollama Cloud.

| run | race (chosen vs plain swap, of 60) | chosen harness, held-out pass^1 | paired Δ vs Ultra (90% CI) | verdict | Δ vs plain swap, same run (95% CI) | cost vs Ultra |
|---|---|---|---|---|---|---|
| `opt_b8a49e660f6e` | 45 vs 29 | 74.3% (pass^k 66.7%) | +3.5 (−1.4 to +8.7) | non-inferior | +23.6 (+16.3 to +31.2): better | −84% |
| `opt_9e05ce50d344` | 44 vs 30 | 75.0% (pass^k 68.8%) | +4.2 (−1.0 to +10.1) | non-inferior | +21.9 (+14.9 to +28.8): better | −89% |
| `opt_d1daf706906d` | 43 vs 39 | 68.8% (pass^k 57.3%) | −2.1 (−6.9 to +2.8) | non-inferior | +11.5 (+5.2 to +17.7): better | −76% |

Ultra baseline on the 96 held-out tasks: 70.8% (recorded run per task). Optimization spend: $1.47-2.64 per run at
list prices.

What all three chosen harnesses have in common: thinking on, temperature 0.6, max_tokens 8000-10000, one explicit
final-reply rule, one or two few-shot replies, and the SDK repair switched on (`final_format: "```sql"`). Prose
answers among the chosen harnesses' held-out runs fell to 1-2 of 288, against 53-74 of 288 for the plain swap.
Runs 1 and 2 also added verification rules (inspect columns before use); run 3 is the minimal version.

## Reading it without bias

1. **The bar is met three times out of three.** Each run, on its own, produced a Nano harness that is non-inferior
   to Ultra at a 10-point margin on 96 held-out tasks × 3 trials and beats the plain Nano swap with the interval
   excluding zero, at 76-89% lower cost. This is the "plain swap fails, rewrite recovers" case, found by the
   procedure rather than picked by hand.
2. **The gain over the swap is inflated by provider drift, but survives without it.** The same plain-swap harness
   scored 61.1% on these tasks at 01:00 and 50.7% and 53.1% between 08:00 and 10:30 (more prose answers: 53, 74,
   67 of 288). Within each run both arms were measured in the same hour, so the paired comparison is fair; against
   the overnight swap measurement the chosen harnesses gain about 8-14 points instead of 12-24.
3. **The same held-out tasks were used for every run and for designing the fixes.** No harness was selected on
   them (selection is the race, on optimization tasks), but the three optimizer changes were made after reading
   Phase 1's held-out failures. A fresh set of tasks (Spider dev has 794 more) would remove that last degree of
   freedom.
4. **This is one agent and one model pair.** The same procedure on gpt-oss 120B to 20B gave +2 points over the
   swap, within noise, and on tau2 telecom (Super to Nano) the swap already matched the baseline on 16 held-out
   tasks. The result is specific to a small model whose main failure is the format of its final message, which is
   exactly what prompt rules and a repair turn can fix; it does not show that rewrites close capability gaps.

## Fresh tasks: the re-check on untouched questions (2026-10-30, 15:55)

The 96 held-out tasks also informed the last optimizer fixes, so the claim was re-checked on 200 Spider dev
questions **no optimizer run ever saw** (seed 44 sample of the 794 unused; ids fr001-fr200). One trial per task,
Ollama Cloud, paired per task; the plain Nano swap and the best chosen harness (`opt_b8a49e660f6e`) against the
recorded Ultra baseline. The 16:00 cutoff left the Ultra baseline at 136 of 200 tasks, so all comparisons use
those 136 (an unbiased subset; the swap completed all 200). The other two chosen harnesses were not re-run in
time and remain open.

| arm | tasks | pass | 95% CI | paired Δ vs Ultra (90% CI) | verdict at 10 pp | Δ vs plain swap (95% CI) | $/task |
|---|---|---|---|---|---|---|---|
| Ultra baseline | 136 | 74.3% | 66.3-80.9% | reference | reference | - | $0.0154 |
| plain Nano swap | 136 | 69.9% | 61.7-76.9% | −4.4 (−10.3 to +1.5) | inconclusive | - | $0.0018 |
| chosen Nano harness (repro 1) | 136 | **77.2%** | 69.5-83.5% | **+2.9 (−1.5 to +7.4)** | **non-inferior** | **+7.4 (+0.7 to +14.7): better** | $0.0020 |

Reading: on questions untouched by every optimization, fix and selection, the optimizer-chosen harness again
matches Ultra (non-inferior at 10 pp) and beats the plain swap with the interval excluding zero — by +7.4 points,
a smaller margin than the +12-24 seen on the older tasks, and the lower bound is +0.7. One trial per task and
136 tasks carry roughly ±5 points of paired precision, so treat the gap as "clearly positive, size uncertain".
The swap here is only −4.4 from Ultra (inconclusive), not the −13 to −19 of the earlier measurements: more
evidence that the plain swap's measured quality drifts by provider and hour, which the paired-same-hour design
guards against. Cost: 87% below Ultra. Spend for the whole re-check: $2.72 at list prices.
