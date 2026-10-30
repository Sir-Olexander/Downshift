# Phase 0 results: can the optimizer find the fix on its own? (2026-10-29, evening)

Setup: after this branch's changes (model notes from the technical reports, the rewriter sees the final
message of failed runs, cost capped below one task in the objective, correctness-first prompt rule, tool
budget enforced), the Nano optimization on text2sql was run three times with the same split (seed 42: 24
optimization tasks, 16 held out), a 20-task sample per round and 3 rounds, on Ollama Cloud. Each run's
recommended Nano harness was then run **fresh** (no replay, every tool call live) twice on the 16 held-out
tasks, next to the Ultra baseline and the plain Nano swap on the same provider. Harnesses are in
`phase0-harnesses/`, per-task outcomes in `phase0-harnesses/fresh-results.jsonl`. Spend at Token Factory
list prices: $0.48 for the three optimizations, $0.33 for the fresh runs.

## What the optimizer did

| run | swap on the 20-task sample | best rewrite round (sample) | what the rewrite changed | Downshift's held-out replay | verdict shown to the user |
|---|---|---|---|---|---|
| 1 `opt_47da8d24f05c` | 65% | round 1: 80% (= Ultra) | thinking on, max_tokens 10000, temperature 0.6, one closing rule ("final message must contain the complete SQL in one ```sql block, never prose"), two few-shot replies | 75% (12/16) | recommended |
| 2 `opt_a744997b4c7e` | 60% | round 1: 65% | the same closing rule and few-shot, plus max_tokens unset, max_tool_calls 15 and an identifier-quoting rule ("double quotes for identifiers") | 56% (9/16) | rejected (below the bar) |
| 3 `opt_9fcc451aa4d6` | 60% | round 2: 70% | the same closing rule, three few-shot replies, extra SQL-pattern rules in round 3 (dropped: round 3 scored 60%) | 88% (14/16) | recommended |

All three runs kept thinking on and wrote an explicit final-reply rule in round 1, which is what the
guidance now asks for and what the hand-made diagnostic had shown to work. No run switched thinking off.

## What fresh runs say (16 held-out tasks, Ollama Cloud unless marked)

| arm | pass / 16 | prose, no SQL | prose taken as SQL | SQL error | wrong rows | $ per task | output tokens per task |
|---|---|---|---|---|---|---|---|
| Ultra baseline, Token Factory, trials 1 and 2 | 11, 12 | 0 | 0 | 0 | 5, 4 | 0.0116 | 630 |
| Ultra baseline, Ollama | 12 | 0 | 0 | 0 | 4 | 0.0129 | 670 |
| Nano plain swap, Token Factory, trials 1 and 2 | 7, 7 | 6, 2 | 1, 5 | 1, 0 | 1, 2 | 0.0009-0.0019 | 1700-3700 |
| Nano plain swap, Ollama, trials 1 and 2 | 8, 8 | 4, 5 | 3, 2 | 0 | 1 | 0.0019 | 2600-4100 |
| **run 1 harness**, trials 1 and 2 | **14, 12** | 0 | 0 | 0, 2 | 2, 2 | 0.0018, 0.0007 | 2850, 1340 |
| run 2 harness, trials 1 and 2 | 8, 11 | 2, 0 | 1, 3 | 2, 0 | 3, 2 | 0.0011, 0.0008 | 2250, 1460 |
| run 3 harness, trials 1 and 2 | 9, 11 | 0 | 0 | 3, 2 | 4, 3 | 0.0008 | 1570 |

Per task, P = pass (tasks sp04 … sp37 in order):

```
Ultra baseline (TF t1, TF t2, Ollama)   P P P . P P . P P . . P . P P P / P P P . P P P P P . . P . P P P / same as t2
Nano plain swap (4 trials)              7-8 passes each, different tasks each time
run 1 harness t1 / t2                   P P P P P P P P P P . P . P P P / P P P P P . P P P P . . . P P P
run 2 harness t1 / t2                   . P P . P . P P P P . . . . P . / P P P . P P . P P P . . . P P P
run 3 harness t1 / t2                   P P . . P P P P . . . P . P P . / P P P . . P P . P P . P . P P P
```

## Reading it without bias

1. **The optimizer can find the fix.** All three runs wrote the final-reply rule by themselves, and the
   format failures (prose instead of SQL) fell from 7 of 16 to 0-3 of 16 in every arm. This is the change the
   earlier optimizations never made, and the reason is now visible: the guidance pushed thinking off and the
   rewriter never saw the prose.
2. **One harness of three beats the plain swap and matches Ultra fresh.** Run 1's harness scored 14 and 12
   against the swap's 7-8 and Ultra's 11-12, at $0.0007-0.0018 per task against Ultra's $0.012-0.013
   (about an 85-94% cost cut). Paired against the swap on the same tasks it is +6 and +4 tasks; paired
   against Ultra, +2/+3 and 0/+1. Downshift's own held-out replay for it (12/16) sits inside the fresh range.
3. **Two harnesses of three do not hold up fresh.** Run 3's harness was reported at 14/16 from one replay and
   came out at 9 and 11 fresh: an overestimate of three to five tasks, and below Ultra. Run 2's was reported
   at 9/16 and came out at 8 and 11; the rejection was right. The remaining failures in both are SQL errors
   and wrong rows, not format: once the container is fixed, Nano's actual SQL ability on these tasks is what is
   left, and extra rules made it worse (run 2's quoting rule produced backtick and quoting errors; run 3's
   extra few-shot and SQL-pattern rules did not help). Shorter rewrites did better, as the literature predicts
   (`prompt-optimization-for-small-models.md`).
4. **The Phase 0 bar was not met.** The plan asked for at least 2 of 3 runs to produce a harness that scores
   at least 12/16 fresh. One did. The optimizer finds the right idea reliably, but which other changes it
   bundles with the idea decides the result, and a 20-task sample with one replay cannot tell those bundles
   apart: on the optimization sample run 1's rounds all scored 80% and run 3's rounds scored 70%, with no
   signal to prefer the minimal harness.
5. **The reporting problem is confirmed, not solved.** Single held-out replays were off by up to five tasks
   on 16 (run 3). Every Downshift number should be read with the ±22-point interval that 16 tasks carry, and
   Phase 1 (240 tasks, trials, paired tests, non-inferiority with "inconclusive") is the next step, not more
   rewriting.

## What this changes in the claims

- "Rewrites have not beaten a plain model swap" is no longer true without qualification: on text2sql, one
  of three Downshift-written Nano harnesses beat the swap by 4-6 tasks of 16 in two fresh trials and matched
  Ultra at about a tenth of the cost. The other two did not; the optimizer cannot yet tell which is which.
- "Rewrites that turned Nano's thinking off broke the tool loop" was wrong (see the diagnostic); the
  guidance no longer says so, and no rewrite in Phase 0 switched thinking off.
- The honest headline for the README stays conditional: Downshift *can* produce a Nano harness that matches
  Ultra on this agent at about one tenth of the cost, and its replay-based numbers are not yet reliable
  enough to know when it has.
