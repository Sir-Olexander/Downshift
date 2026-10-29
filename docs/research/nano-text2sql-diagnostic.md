# Diagnostic: what one format rule does for Nano on text2sql (2026-10-29)

**This is a hand-made diagnostic, not a Downshift result.** The format rule below was written after reading
the failures on these same 16 tasks, so this is the ceiling a rewrite *could* reach, not evidence that the
optimizer reaches it. One trial per arm; a 95% interval on 16 tasks is about ±22 points. The harnesses are in
`diag-harnesses/` and the per-task outcomes in `diag-harnesses/results.jsonl`. Provider: Ollama Cloud
(costs are computed at Token Factory list prices, as everywhere in Downshift).

How to reproduce (from `demo_agents_2/text2sql-framework-main`, with the held-out ids of
`opt_10b7f3486f2d`):

```bash
.venv/bin/python -m downshift.runner record --provider ollama --harness <one of the yaml files> \
  --only sp04,sp05,sp10,sp11,sp12,sp13,sp19,sp22,sp24,sp25,sp26,sp29,sp31,sp33,sp35,sp37 \
  --offline-dir /tmp/run --tag diag --concurrency 3
```

## The four arms

| harness | what changed | pass | format failures (prose, no SQL) | wrong or failing SQL | $/task | output tokens/task | tool calls/task |
|---|---|---|---|---|---|---|---|
| nano-swap-thinking-on | text2sql's own prompt, model swapped to Nano (what Downshift recommended against) | **8/16** | 7 | 1 | 0.0019 | 4138 | 6.9 |
| nano-swap-thinking-off | the same, with only `reasoning: off` added | **4/16** | 9 | 3 | 0.0011 | 486 | 8.0 |
| nano-rewrite-opt_4dba6d045f4f-thinking-off | Downshift's first Nano rewrite (thinking off, few-shot that wrote tool calls as `{"tool": ...}` text, Postgres `information_schema` queries) | **2/16** | 0 | 14 (text tool calls, never ran a real query) | 0.0037 | 373 | 1.7 |
| nano-swap-thinking-on-plus-format-rule | the swap harness plus two sentences in the system prompt (below) | **14/16** | 0 | 2 | 0.0014 | 2658 | 5.9 |

For comparison, fresh runs of the Ultra baseline on the same 16 tasks gave 11/16 and 12/16 at $0.0116 per task,
and the Super harness Downshift recommended gave 13/16 and 12/16 at $0.0028-0.0034 (Token Factory,
`text2sql-failure-taxonomy.md`).

The rule added to the system prompt:

> Final reply rule: when you have the answer, your final message must contain the complete SQL query
> inside one ```sql code block. Never answer with the result values in prose only.

## What this settles

1. **The gap Downshift could not close is a final-message format gap.** With the rule, every run ends with
   SQL in a code block; the two remaining failures are semantic (a debatable Spider gold query for "greater
   than any country in Europe", and a tie on "fewest flights"), the same tasks Ultra and Super also miss.
2. **Thinking off does not stop Nano from calling tools.** The thinking-off swap made 8 real tool calls per
   task and wrote no tool call as text. It halves the pass rate (8 → 4) through more prose answers and more
   wrong SQL, which fits Nano's training (about 10% reasoning-off SFT data, see
   `nemotron-3-model-guides.md`). So "thinking off" is a cost knob with a real quality price on Nano, not a
   breakage.
3. **The "tool calls written as text" failure was caused by Downshift's own few-shot**, which showed
   `{"tool": "execute_sql", "args": ...}` lines as assistant text; Nano copied the format in 14 of 16 runs
   and never executed a query. The few-shot check added afterwards catches this; the thinking-off setting was
   blamed for it in the README and should be corrected.
4. **The rule also makes Nano cheaper** (2658 vs 4138 output tokens per task): a run that stops with a code
   block costs less than one that dumps a markdown table of results.
5. **Why the optimizer did not find the rule.** Its guidance steered every Nano rewrite to thinking off, its
   objective rewards cost savings, its failure excerpts show the extracted SQL rather than the final message,
   and each candidate was judged on 8 tasks (one task = 12.5 points). The plan in
   `../prove-the-optimizer-plan.md` addresses each of these.

## What this does not settle

- One trial, 16 tasks: 14/16 vs 8/16 is a 6-task difference, about 2.5 standard errors on paired data; it
  needs the larger held-out set and repeated trials described in `evaluation-methodology.md`.
- The rule was written by someone who had seen these tasks fail. The real test is whether Downshift's
  rewriter, given the right guidance and the real failure text, proposes an equivalent rule on the
  optimization split and it then holds on a held-out split it never saw.
