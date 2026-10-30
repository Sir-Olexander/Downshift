# Judge validation: the stored verdicts against the labelled answers (2026-10-30)

The research agent's demo numbers (README, `opt_c5bcd27101b5`) rest on a Nemotron 3 Ultra judge. Its 51 held-out
pair verdicts and 108 answers (27 baseline + 27 per option, across the optimization and test splits) were
labelled in `docs/judge-validation/labels.csv` — a **model-assisted first pass** (the labels commit of 2026-10-30), each claim
checked against the full text of the cited Wikipedia pages; not human labels. This note compares the judge's
stored scores with those labels
(`python -m app.judge_audit compare opt_c5bcd27101b5`; raw items in that command's `--json` output).

## Scores versus labels (108 answers)

| dimension | agreement | judge passes a labelled-wrong answer | judge fails a labelled-correct answer |
|---|---|---|---|
| correct, at the pipeline's bar (score ≥ 3) | **87.0%** (92.2% ignoring side details) | 11 of 12 | 3 of 96 |
| complete (score ≥ 3) | 93.5% | 3 | 4 |
| supported (score ≥ 4) vs "no unsupported claim" | 73.1% | **19 of 19** | 10 of 89 |

The 12 labelled-wrong answers split into 8 wrong only on a side detail and 4 clearly wrong. The judge passed
**3 of the 4 clearly-wrong answers** (scores 4.0-5.0) and 6 of the 8 side details; it caught one clearly wrong
answer. Cohen's kappa is 0.07, but that is a prevalence artifact (89% of the answers are labelled correct);
the agreement and error rates above are the informative numbers.

**The "supported" rubric does not check support.** The judge scored every one of the 19 answers that make a
claim their cited pages do not back at supported ≥ 4 (mean 4.89 — its most confident dimension). It cannot do
otherwise: it never sees the sources, only the answers. What it measures is citation formatting. The automatic
checks still enforce that every cited URL appeared in the tools' results, but nothing in the pipeline catches
a claim the page does not support.

## Pairwise preference versus the labels

| pairs | judge's stored preference |
|---|---|
| 12 where the labels differ (one side correct, the other wrong) | right 6, tie 5, **wrong 1** |
| 69 where the labels say both are correct | **baseline 32**, tie 27, candidate 10 |

So the judge almost never prefers the side the labels call wrong, but it resolves only half of the clear
differences (5 ties), and among equal-quality answers it prefers the Ultra baseline about three times as
often as the cheaper candidate. That is a same-quality lean toward the longer/richer baseline answer, on top
of the position inconsistency already measured (72-88% between runs, `judge-audit.md`).

## What this means for the demo claims

1. **Bulk correctness is roughly right, individual verdicts are not.** 87% agreement is above the 75%
   acceptance bar, and false-fails are rare (3%). But the judge is lenient: among labelled-wrong answers its
   mean correct score is 4.0-5.0 for three of the four sources, so the success bar (correct ≥ 3) almost never
   binds. Judge-based success rates are therefore **upper bounds**: with 11 false passes in 108 answers, a
   reported 94% could plausibly be a few points lower.
2. **The quality score's "supported" third is decorative.** Any claim that the judge-based quality metric
   measures source support is wrong; it measures whether citations look right.
3. **"Within the bar" comparisons are directionally safe.** The baseline lean (3:1 at equal quality) works
   against the cheaper options, so when a cheaper option is reported as close to the baseline, the honest
   reading "close, not better" stands — if anything the lean makes the demo conservative.
4. **Labels are model-assisted.** Until a person spot-checks `labels.csv`, this is "validated against an
   independent source-checked labelling", not "validated against people". The 4 clearly-wrong answers are the
   highest-value rows for a human to re-check first (items i040, i053, i078, i107 in the CSV).
