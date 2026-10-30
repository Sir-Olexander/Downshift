# Judge audit on the research agent's held-out pairs (2026-10-30)

The demo results in the README rest on a Nemotron 3 Ultra judge comparing each candidate answer with the Ultra
baseline answer (optimization `opt_c5bcd27101b5`, 17 held-out questions × Super, Nano and per-step mix = 51 pairs).
`python -m app.judge_audit audit` judged every pair in both orders, with the Ultra judge and with a judge from
another family. Raw rows: `docs/judge-validation/audit-ultra-vs-deepseek.json`. Ollama Cloud, reasoning off for
both judges, temperature 0.

| judge | pairs parsed | same winner in both orders | prefers baseline | prefers candidate | tie |
|---|---|---|---|---|---|
| Nemotron 3 Ultra, run 1 | 51 | 88.2% | 48.0% | 10.8% | 41.2% |
| Nemotron 3 Ultra, run 2 | 51 | 72.5% | 52.0% | 10.8% | 37.3% |
| DeepSeek V4 Pro | 51 | 82.4% | 57.8% | 12.7% | 29.4% |
| GLM-5.3 (first attempt) | 14 | 92.9% | 75.0% | 7.1% | 17.9% |

On the 32 pairs where both Ultra (run 2) and DeepSeek gave the same verdict in both orders, they agreed on
**90.6%** (19 baseline, 7 tie, 3 candidate). GLM-5.3 returned unparseable verdicts for 37 of 51 pairs with
thinking off and is left out.

Reading:

1. **No sign of self-preference.** The judge from another family prefers the Ultra baseline more often than
   the Ultra judge does (57.8% vs 48-52%), and the two agree on 91% of the pairs both judge consistently.
2. **Position consistency is unstable.** The same Ultra judge at temperature 0 was consistent on 88.2% of pairs
   in one run and 72.5% in the next: about one pair in four to one in eight gets a different winner depending
   on which answer is shown first. Single-order verdicts, which the optimizer uses, carry that noise; judging
   both orders and counting split verdicts as ties would remove it at twice the judge cost.
3. **Both judges prefer the baseline about five times as often as the cheaper candidate.** This supports the
   README's existing caution that "within the bar" on the research agent means close, not as good.
4. **What this does not show:** whether either judge is *right*. That needs the human labels in
   `docs/judge-validation/labels.csv` (108 blind answers). Until then the research-agent numbers stay
   "judge-based, not validated against people".
