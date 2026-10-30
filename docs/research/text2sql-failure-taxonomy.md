# What actually fails when Nano runs text2sql (evidence from our own runs)

Source: the fresh verification runs of the real text2sql agent on the 16 held-out Spider tasks of
optimization `opt_10b7f3486f2d` (`demo_agents_2/_eval/verify/opt_10b7f3486f2d/run_*`, two trials per
harness, Nebius Token Factory, 2026-10-29), plus the stored optimization rounds in
`server/data/downshift.sqlite3`. Classification rule: `pass` = the grader passed; `no_sql_prose` = the
grader reported "no SQL" (the final reply had no ```sql block and no SELECT/WITH to fall back on);
`prose_extracted_as_sql` = the SQL that text2sql extracted does not start with SELECT/WITH (its fallback
took English text from the first "with"); `sql_error` = real SQL that fails to execute; `wrong_rows` =
real SQL, wrong result.

## Failure classes per harness (16 held-out tasks, fresh runs)

| harness (fresh run) | pass | no_sql_prose | prose_extracted_as_sql | sql_error | wrong_rows | $/task | output tokens/task |
|---|---|---|---|---|---|---|---|
| Ultra, text2sql's own prompt, trial 1 | 11 | 0 | 0 | 0 | 5 | 0.0116 | 628 |
| Ultra, text2sql's own prompt, trial 2 | 12 | 0 | 0 | 0 | 4 | 0.0112 | 645 |
| Super, Downshift's round-1 rewrite, trial 1 | 13 | 0 | 1 | 1 | 1 | 0.0034 | 534 |
| Super, Downshift's round-1 rewrite, trial 2 | 12 | 0 | 0 | 1 | 3 | 0.0028 | 531 |
| Nano, model swap only (thinking on), trial 1 | 7 | 6 | 1 | 1 | 1 | 0.0009 | 1673 |
| Nano, model swap only (thinking on), trial 2 | 7 | 2 | 5 | 0 | 2 | 0.0019 | 3721 |

Over the full 40 tasks with the unmodified agent (`_eval/out/text2sql/*.jsonl`): Nano produced no SQL
in 13 and 8 of 40 answers (trials 1 and 2) and wrong SQL in 5 and 9; Super and Ultra never failed to
produce SQL (their 7-11 failures per trial are all wrong results).

## The format failures are "right answer, wrong container"

For the 14 Nano format failures above, the gold rows were compared with the text of Nano's final reply:

| trial | format failures | prose contains every gold value | examples |
|---|---|---|---|
| 1 | 7 | 5 of 7 | "The country with the most car makers is **Japan**."; a markdown table with all 18 expected rows; "there are **11** orchestras…" |
| 2 | 7 | 3 of 7 | same tasks again; the misses differ only in formatting (date written with non-breaking hyphens, "USA" vs the stored name, a prose table) |

So with thinking on, Nano explores the schema, runs the right query through the tool, reads the result
and then reports it in prose, breaking text2sql's contract ("the final reply must contain the SQL in a
```sql block"). It is not a reasoning failure. Fixing only the final-message format would move Nano from
7/16 to roughly 12-14/16 on these tasks, which is the Ultra baseline's range (11-12/16).

Ultra's own failures are different: 4-5 of 16 are real result mismatches, several on tasks whose Spider
gold answer is debatable (for example "greater than any country in Europe" graded as "greater than the
smallest European country").

## What Downshift's rewriter did with Nano, and why it could not see this

From the stored rounds of the two text2sql optimizations (`opt_4dba6d045f4f`, `opt_10b7f3486f2d`):

| optimization | Nano round | reasoning | temperature | max_tokens | success on the 8-task sample |
|---|---|---|---|---|---|
| opt_4dba6d045f4f | 1 (rewrite) | off | 0.6 | 2000 | 25.0% |
| opt_4dba6d045f4f | 2 (rewrite) | off | 0.6 | 2000 | 50.0% |
| opt_10b7f3486f2d | 0 (model swap only) | provider default (on) | none | none | 62.5% |
| opt_10b7f3486f2d | 1 (rewrite) | off | 0.6 | 2000 | 12.5% |
| opt_10b7f3486f2d | 2 (rewrite) | off | 0.6 | 2000 | 12.5% |

Every Nano rewrite set `reasoning: off`, including the round that said it "reverted round 1 changes that
degraded performance". Three things push it there:

1. `server/app/optimizer/guidance.py` says of Nano: "Thinking can be switched off (reasoning: off), which
   makes short mechanical steps much cheaper and faster", and the general tips say "moving reasoning off
   for mechanical steps and on for synthesis". A single tool-loop step reads as "mechanical".
2. The rewrite prompt's rules say "Prefer fewer, cheaper model calls when it does not cost correctness",
   and the objective adds up to +10 points for cost savings.
3. With thinking off, Nano's failures changed character (tool calls written as text, guessed table names
   such as `museums`, `continents`), so the rewriter spent its second round fixing the failures its own
   first round caused, never the prose-instead-of-SQL failure of the thinking-on swap.

The web lookup that is meant to give the rewriter model-specific guidance returned, for both targets,
the Wikipedia pages "Nemotron", "Nvidia", "Humanity's Last Exam" and "List of free and open-source
software packages" (no Tavily key was set). It contributed nothing.

## Also seen

- Super's round-1 rewrite (`reasoning: low`, then `on`) matched or beat the plain Super swap only within
  noise on 8 tasks (75% vs 62.5%) and on the held-out set (68.8% claimed, 75-81% fresh vs 69-81% for the
  swap). `reasoning: low` maps to `reasoning_effort: low` on Token Factory; whether vLLM honours that
  for Nemotron has not been verified (only `enable_thinking=false` was).
- Nano with thinking on uses 3-6× more output tokens than Super, so its cost advantage per task shrinks
  from 5× (price) to about 2-3× (measured $0.0009-0.0019 vs $0.0028-0.0034).
- One Nano trial-2 run (sp04) returned an empty final message: finish without content, likely the
  thinking consumed the budget; max_tokens was unset there, so this needs a look.
