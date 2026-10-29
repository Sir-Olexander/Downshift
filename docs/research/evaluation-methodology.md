# Evaluation methodology for Downshift: statistics, trials, selection, judges, reporting

Research notes, 2026-10-29. Sources were read on the web on that date. No model calls were made. Every
power and sample-size number below was computed by hand from the cited formulas (standalone Python,
normal approximation). Anything I could not check against a primary source is marked **unverified**.

**The problem in one paragraph.** Today each candidate gets one replay on about 10 optimization tasks,
which picks the winner, and one replay on 16-17 held-out tasks, which is reported. With n = 16 and a single
trial, the standard error of a pass rate near 60% is sqrt(0.24/16) = 12.2 pp, so the 95% CI is about
±24 pp. The Wilson interval for 10/16 is 38.6%-81.5%. A 62.5% replay that came out 44% in fresh runs
(3 tasks out of 16, 18.75 pp) is about 1.5 SE, which is ordinary noise. It does not prove that replays
are biased, but it cannot rule that out either. In short, the current design cannot resolve differences
smaller than about 30-35 pp between two systems (see Section 2).

---

## 1. Statistics for LLM evals

**Miller, E. (2024). *Adding Error Bars to Evals: A Statistical Approach to Language Model Evaluations*. Anthropic. arXiv:2411.00640. https://arxiv.org/abs/2411.00640**
- *What*: treats eval questions as draws from a super-population and gives formulas to analyse and plan evals.
- *Key formulas*:
  - Standard error of the mean: SE = sqrt(s²/n). For a binary score, SE = sqrt(p̄(1−p̄)/n). The 95% CI is mean ± 1.96·SE.
  - Clustered SE: SE_cl = sqrt(SE_CLT² + (1/n²) Σ_c Σ_i Σ_{j≠i} (s_ic − s̄)(s_jc − s̄)). On DROP the clustered SE is 3× the naive one (1.34 vs 0.44).
  - Resampling K answers per question: Var(μ̂) = (Var(x) + E[σ²]/K)/n. Var(x) is the **between-question** variance and E[σ²] is the **within-question** variance. In the worked example with difficulty uniform on [0,1], Var(x) = 1/12 and E[σ²] = 1/6. Variance relative to K = 1 is (1 + 2/K)/3, so K = 2 gives −1/3, K = 4 gives −1/2, and the reduction can never exceed −2/3.
  - Paired difference: SE_paired = sqrt(Var(s_A − s_B)/n) = sqrt(SE_A² + SE_B² − 2·SE_A·SE_B·Corr(s_A, s_B)). With a question-level correlation of 0.5, the variance falls by 1/3 compared with unpaired.
  - Power and sample size: n = (z_{α/2} + z_β)² · (ω² + σ_A²/K_A + σ_B²/K_B) / δ², where ω² = Var(x_A) + Var(x_B) − 2Cov(x_A, x_B). The minimum detectable effect is δ = (z_{α/2} + z_β)·sqrt((ω² + σ_A²/K_A + σ_B²/K_B)/n). Worked examples: detecting 3 pp needs about 969 questions. At n = 198, raising K from 1 to 10 lowers the MDE from 13.2% to 7.5%.
  - Recommendations: use CLT SEs, clustered SEs when questions come in groups, resampling, question-level paired differences, and power analysis. Report n, the number of clusters, the paired differences, their SEs and the correlation. Do not lower temperature to cut variance, because that can move variance into the between-question term or add bias.
- *Implication for Downshift*: adopt this framework as the default. Store per-task, per-trial outcomes and compute every comparison as a paired difference on the same tasks.

**Bowyer, S., Aitchison, L., Ivanova, D. R. (2025). *Position: Don't Use the CLT in LLM Evals With Fewer Than a Few Hundred Datapoints*. ICML 2025. arXiv:2503.01747. https://arxiv.org/abs/2503.01747**
- *What*: simulations at small N showing that CLT and bootstrap intervals under-cover.
- *Key numbers*: even at N = 100, a 95% CLT interval covers only 92.5% of the time. Below that, CLT and bootstrap fall "well below the nominal level". For a single proportion they recommend Wilson score or Bayesian Beta(1+k, 1+n−k) intervals; Clopper-Pearson is valid but too wide. For comparing two models on the same questions they recommend a **paired Bayesian** model, with unpaired Bayes as a simpler fallback. A library is available: github.com/sambowyer/bayes_evals.
- *Implication*: at n = 16-50, report Wilson or Beta intervals rather than ±1.96·SE. For paired deltas, use a paired Bayesian interval or an exact or permutation test, not a z-test.

**Kapoor, S., Stroebl, B., Siegel, Z. S., Nadgir, N., Narayanan, A. (2024). *AI Agents That Matter*. arXiv:2407.01502. https://arxiv.org/abs/2407.01502**
- *What*: a critique of agent benchmarking.
- *Key numbers*: on HumanEval, simple baselines matched or beat complex agents. Warming reached 93.2% for $2.45, while LATS reached 88.0% for $134.50, more than 50× the cost. Many published accuracies were above the maximum of the authors' own **5 reproduction runs**, for which they report the mean, min-max and t-based 95% CIs. Of 17 benchmarks, only some had holdouts suited to their generality level, and 7 had no holdout at all.
- *Recommendations*: use cost-controlled Pareto comparisons, include simple baselines, use holdouts matched to the claimed generality, report variance across runs, and report token counts so costs can be recomputed.
- *Implication*: the plain model swap is Downshift's "simple baseline", and every rewrite must beat it on held-out tasks with a CI. Report tokens as well as dollars. Treat "within the bar" as a cost-controlled claim that needs error bars.

**Kapoor, S., Stroebl, B., et al. (2025). *Holistic Agent Leaderboard: The Missing Infrastructure for AI Agent Evaluation*. ICLR 2026. arXiv:2510.11977. https://arxiv.org/abs/2510.11977**
- 21,730 rollouts covering 9 models × 9 benchmarks for about $40k. They log tokens and cost for every call and use Pareto analysis. Notable finding: higher reasoning effort *reduced* accuracy in most runs.
- *Implication*: "reasoning off/on" in Downshift harnesses should be judged by measurement, not assumed to help.

**Yao, S., Shinn, N., Razavi, P., Narasimhan, K. (2024). *τ-bench*. arXiv:2406.12045. https://arxiv.org/abs/2406.12045**
- *Key formulas*: with n trials per task and c successes, pass^k = E_task[C(c,k)/C(n,k)] is the probability that **all** k trials succeed. pass@k = 1 − E_task[C(n−c,k)/C(n,k)] is the probability that at least one succeeds.
- *Key numbers*: gpt-4o pass^1 = 61.2% on retail and 35.2% on airline, and retail pass^8 is below 25%. The main results use at least 3 trials per task.
- *Implication*: when a cheaper model swaps in, the risk is *inconsistency*, not just a lower mean. With K ≥ 3 trials, report pass^1 (the mean) and pass^3 for the baseline and each candidate. A candidate whose pass^1 is close to the baseline but whose pass^3 is much lower is less reliable.

**Heineman, D., Hofmann, V., Magnusson, I., Gu, Y., Smith, N. A., Hajishirzi, H., Lo, K., Dodge, J. (2025). *Signal and Noise: A Framework for Reducing Uncertainty in Language Model Evaluation*. NeurIPS 2025. arXiv:2508.13144. https://arxiv.org/abs/2508.13144**
- *Definitions*: signal = max_{j,k}|m_j − m_k| / m̄ across models. Noise = the relative standard deviation over a model's final checkpoints. SNR = signal / noise.
- *Key numbers*: SNR correlates with decision accuracy at R = 0.791. Continuous metrics raise SNR substantially; switching to bits-per-byte took GSM8K from 1.2 to 7.0 and MBPP from 2.0 to 41.8. Filtering noisy subtasks raised decision accuracy by 2.6-5%.
- *Implication*: a binary pass/fail on one trial is the noisiest metric available. A per-task success *rate* over K trials, or a graded score such as partial-credit SQL or the rubric total, carries more signal per task. Consider dropping tasks that give no signal (always pass or always fail for every system); they only dilute the comparison.

**Huang, W.-J. (2026). *How Many Tasks Are Enough for Agent Benchmark Decisions? A Replay Analysis of Public LLM Agent Benchmarks*. KDD workshop. arXiv:2607.12338. https://arxiv.org/abs/2607.12338**
- *What*: replays public task-level records to ask when a partial task set reaches the same pairwise decision as the full benchmark.
- *Key numbers*: to meet ≤5% false-accept/false-reject, ≤5% coverage failure and ≤25% unresolved comparisons, the budget needed was 15% of AppWorld, 25% of τ-bench and 90% of SWE-bench Verified; SWE-bench Lite never met the targets. They quote: "a task fraction is not a decision rule". If the targets are not met, "the appropriate output is more evaluation or no partial conclusion."
- *Implication*: before replaying, fix the threshold δ, the decision rule and an "unresolved" outcome. "Inconclusive" must be a valid Downshift verdict.

**Kotawala, A. (2026). *Resolution Diagnostics for Paired LLM Evaluation*. ICML 2026 workshop. arXiv:2605.30315. https://arxiv.org/abs/2605.30315**
- Many published pairwise rankings are "not resolved" at α = 0.05 and 80% power: 11 of 40 on Open LLM Leaderboard v1, and 4 of 9 adjacent top-10 pairs on MMLU-Pro (6 of 9 when clustered). The common "unpaired Cohen's h × (1−ρ)" shortcut gets N* wrong by about 2× in close comparisons, and three of five off-the-shelf calculators inherit this error.
- *Implication*: compute paired power directly from the variance of the per-task differences, as in Section 2, rather than with generic calculators.

**Not located**: I found no paper with the exact titles "Position: LLM evals need confidence intervals", "Beyond the leaderboard" (as an eval-statistics paper) or "Inferential statistics for LLM benchmarks" (**unverified / possibly misremembered titles**). The closest equivalents are Bowyer et al. 2025 and Kotawala 2026 above.

---

## 2. Concrete power numbers (paired, pass/fail, α = 0.05 two-sided, 80% power)

### Formulas
- **Paired difference with K trials per task per system (Miller).** Let d_i = p̂_Ai − p̂_Bi, where each p̂ is the mean over K trials.
  - Var(d̄) = [ω² + (σ²_wA + σ²_wB)/K] / n, where ω² = Var_i(p_Ai − p_Bi) is the **between-task** variance of the true per-task difference and σ²_w = E_i[p_i(1−p_i)] is the **within-task** Bernoulli variance.
  - n = 7.85 · [ω² + (σ²_wA + σ²_wB)/K] / δ². The constant is (1.96 + 0.84)² = 7.85; for a one-sided test or non-inferiority it is (1.645 + 0.84)² = 6.18.
- **McNemar for K = 1** (Connor 1987 approximation): n = [z_{α/2}·sqrt(ψ) + z_β·sqrt(ψ − δ²)]² / δ², where ψ = P(discordant pair) = p₁₀ + p₀₁.
- **More trials only shrink the within-task term.** The between-task term ω²/n falls only with more tasks. With a fixed run budget B = n·K, Var = ω²/n + σ²_w/B, so **when tasks are available, K = 1 on more tasks always gives the smallest variance**. Extra trials pay off only when tasks are scarce, as with the 42 research questions, or when pass^k or within-task variance has to be estimated, which needs K ≥ 2.

### McNemar, K = 1 (tasks needed, by discordance ψ)
| δ \ ψ | 0.10 | 0.20 | 0.30 | 0.40 |
|---|---|---|---|---|
| 5 pp | 312 | 626 | 940 | 1254 |
| 10 pp | – | 155 | 234 | 312 |
| 15 pp | – | 68 | 103 | 138 |
| 20 pp | – | – | 57 | 77 |

### Tasks needed vs. trials per task (variance-components model)
Assumptions: baseline pass rate p_A, candidate p_B = p_A − δ, and a share ICC of each system's Bernoulli variance is between-task. ρ is the correlation of the two systems' true per-task pass probabilities. These values are illustrative; **the pilot in Section 7 replaces them**.

p_A = 0.75, ICC = 0.5, ρ = 0.8 (moderately correlated systems):
| δ | K=1 | K=3 | K=5 | K=10 | K=∞ |
|---|---|---|---|---|---|
| 5 pp | 750 | 334 | 251 | 188 | 126 |
| 10 pp | 197 | 88 | 66 | 50 | 34 |
| 15 pp | 90 | 41 | 31 | 23 | 16 |
| 20 pp | 52 | 24 | 18 | 14 | 9 |

p_A = 0.75, ICC = 0.5, ρ = 0.5 (pessimistic): 10 pp needs 245 / 137 / 115 / 99 / 82 tasks for K = 1 / 3 / 5 / 10 / ∞, and 20 pp needs 65 / 36 / 31 / 26 / 22.
p_A = 0.75, ICC = 0.8, ρ = 0.8 (mostly deterministic tasks): 10 pp needs 119 / 75 / 67 / 60 / 54.
p_A = 0.5, ICC = 0.5, ρ = 0.8: 10 pp needs 231 / 103 / 77 / 58 / 39, and 20 pp needs 55 / 25 / 19 / 14 / 10.

### What Downshift's current sizes can detect (MDE in pp, p_A = .75 vs p_B = .65, ICC .5, ρ .8)
| n tasks | K=1 | K=2 | K=3 | K=5 | K=10 | K=∞ |
|---|---|---|---|---|---|---|
| 10 (dev) | 44 | 34 | 30 | 26 | 22 | 18 |
| 16-17 (held-out) | 34-35 | 26-27 | 23 | 20 | 17 | 14 |
| 25 | 28 | 21 | 19 | 16 | 14 | 12 |
| 50 | 20 | 15 | 13 | 12 | 10 | 8 |
| 100 | 14 | 11 | 9 | 8 | 7 | 6 |
| 150 | 11 | 9 | 8 | 7 | 6 | 5 |

With ρ = 0.5, every MDE grows by about 10-25%; for example, 16 tasks with K = ∞ gives 22.6 pp. **With 16 held-out tasks, a 10 pp difference cannot be detected even with infinitely many trials.** It needs roughly 50-100 held-out tasks at K = 3, or about 150-250 at K = 1.

### Estimating both variance components from a pilot (for example 16 tasks × 3 trials, both systems)
- Per system, the within-task variance is σ̂²_w = (1/n) Σ_i [K/(K−1)]·p̂_i(1−p̂_i), which is unbiased per task.
- The paired between-task variance is ω̂² = s²(d_i) − (σ̂²_wA + σ̂²_wB)/K, where s² is the sample variance of the d_i. Truncate it at 0. This is the one-way ANOVA method-of-moments estimator.
- With 16 tasks, ω̂² is very imprecise: a χ²₁₅ interval spans about 0.55× to 2.4× the point estimate. For planning, **use the upper end** or a pilot of at least 30 tasks.
- Also report the ICC, ω²/(ω² + σ²_w). A high ICC means tasks are near-deterministic and extra trials buy little; a low ICC means trials help.

---

## 3. Nondeterminism at temperature 0

**He, H. & Thinking Machines Lab (2025-09-10). *Defeating Nondeterminism in LLM Inference*. https://thinkingmachines.ai/blog/defeating-nondeterminism-in-llm-inference/**
- The main cause is **lack of batch invariance**: kernel results depend on batch size, and batch size changes with server load. The usual "concurrency + floating point" explanation is incomplete.
- Qwen3-235B-A22B at temperature 0 produced **80 unique completions out of 1,000**. They diverged at token 103 (992 continued "Queens, New York", 8 "New York City"). Batch-invariant kernels made all 1,000 identical, at a cost of 26 s → 42-55 s.
- *Implication*: a hosted Nemotron MoE (on Ollama Cloud or Token Factory) at temperature 0 should be treated as stochastic. Agent trajectories amplify small token differences through tool calls.

**Atil, B., et al. (2024, rev. 2025). *Non-Determinism of "Deterministic" LLM Settings*. arXiv:2408.04667. https://arxiv.org/abs/2408.04667**
- Five LLMs and eight tasks (BBH, MMLU), run 10 times each at temperature 0 with a fixed seed. Accuracy varied by **up to 15%** across runs, and the gap between best and worst possible accuracy reached **70%**. Raw-string agreement (TARr@10) was usually low, and parsed-answer agreement (TARa@10) was higher but far from 100%. Longer outputs gave lower agreement. A local Llama-3-8B without serving optimizations was deterministic, pointing to batching and serving as the cause.
- They recommend reporting the max-min spread across runs, and they give no minimum number of runs.

**Bjarnason, B. H., Silva, A., Monperrus, M. (2026). *On Randomness in Agentic Evals*. arXiv:2602.07150. https://arxiv.org/abs/2602.07150**
- 60,000 SWE-bench Verified trajectories (3 models × 2 scaffolds). Single-run pass@1 varies by **2.2-6.0 pp** depending on which run is picked, and the SD is **above 1.5 pp even at temperature 0** on a benchmark of 500 tasks. Trajectories diverge "often within the first few percent of tokens", so gains of 2-3 pp may be noise.
- **Unverified (secondary source)**: their power analysis says about 9 runs per agent are needed to detect 2 pp.
- *Implication*: on 16 tasks instead of 500, run-to-run swings are far larger. Swings of 3 tasks, as Downshift observed, are expected.

**Ariño de la Rubia, E., Pafka, S. (2026). *Identical Runs, Different Results: Benchmarking AI Coding Agents on Open-Weight Models*. arXiv:2609.33812. https://arxiv.org/abs/2609.33812**
- One ML task. Run-to-run SD was larger than the differences between pairings. Three-run comparisons put the weaker pairing ahead **28-44%** of the time, and the observed gaps needed about 39-113 runs per arm.
- They recommend evaluating the model and harness together as a *pairing*, over repeated attempts.

**Typical trial counts**: τ-bench uses at least 3 trials. Kapoor et al. use 5 runs. Atil et al. use 10. Epoch AI runs 16× on GPQA Diamond and AIME and 8× on MATH L5 (Section 6). Inspect supports `epochs` with reducers `mean`, `pass_at_k`, `pass_k_k` and `at_least_k`. Agents typically report the average of k (pass^1 estimated from k trials), and reliability-focused work adds pass^k.

**Replays vs. fresh runs.** This is not a statistics paper, but it matters. Downshift's replay serves tool results from the recording, which is a different measurement from a fresh run. Its error is *systematic*, not random: if the candidate's trajectory leaves the recording, how does the replay respond? That gap can only be measured with fresh runs, so keep fresh-run validation as a separate, reported check.

---

## 4. Selecting the best candidate on a dev set, then reporting on test

**Winner's curse, computed for Downshift's sizes.** If k candidates have equal true quality, the dev score of the winner is inflated by about SE × E[max of k N(0,1)]. That factor is 0.57 for k = 2, 0.85 for 3, 1.03 for 4, 1.16 for 5 and 1.54 for 10 (Monte Carlo). With 10 dev tasks, K = 1 and p ≈ 0.65, SE = 15 pp, so the best of 3-4 equal candidates looks about **13-15 pp better than it is** on dev. Ranking error is large too: if two candidates truly differ by 10 pp, the worse one wins on dev with probability **26%** (n = 10, K = 1), 17% (n = 10, K = 3), 6.7% (n = 25, K = 3) and 1.7% (n = 50, K = 3), using the ρ = 0.8 variance model from Section 2.
- The held-out score is *not* biased by selection because it was never used to choose. It is only noisy. The selection noise costs you something else: the candidate you picked is often not the best one.

**Cawley, G. C., Talbot, N. L. C. (2010). *On Over-fitting in Model Selection and Subsequent Selection Bias in Performance Evaluation*. JMLR 11:2079-2107. https://jmlr.org/papers/v11/cawley10a.html**
- The classic result: optimising a selection criterion on a small validation set overfits the criterion, and the selected model's validation score is optimistically biased. The fixes are nested cross-validation or an untouched test set, plus fewer or regularised selection choices.
- *Implication*: keep the held-out split untouched, which Downshift already does. Keep the number of candidates small, and treat the dev score as a screening tool, not an estimate.

**DSPy MIPROv2 (Opsahl-Ong et al. 2024, arXiv:2406.11695; docs https://dspy.ai/learn/optimization/overview, https://dspy.ai/api/optimizers/MIPROv2/)**
- By default it scores candidates on minibatches of 35 examples, then fully evaluates the best-so-far on the whole validation set every 5 trials. When no valset is given, it uses **80%** of the trainset as validation. The DSPy docs recommend a **20% train / 80% validation** split for prompt optimizers, "often the opposite of what one does for DNNs", because the scarce resource is reliable selection, not training signal.
- *Implication*: Downshift splits 60% optimization / 40% held-out and replays only a sample of the 60%. Use most of the optimization set for *scoring* candidates, and spend proposal context on only a few examples.

**Agrawal, L. A., et al. (2025). *GEPA: Reflective Prompt Evolution Can Outperform Reinforcement Learning*. arXiv:2507.19457. https://arxiv.org/abs/2507.19457**
- It splits the training data into D_feedback, minibatches of 3 used for reflection, and D_pareto, used for selection. Candidates are kept if they are best on at least one D_pareto instance, and the final candidate has the best D_pareto average. The splits are large: train/val/test are 150/300/300 for HotpotQA and HoVer, 150/300/294 for IFBench and 111/111/221 for PUPA, and AIME test questions are repeated 5×. Most of the rollout budget goes to validation scoring. Results are single runs with no CIs. The headline is +10 pp over MIPROv2.
- *Implication*: published optimizers select on about **300** validation items, roughly 30× Downshift's 10. Even so, they report no CIs.

**Small-set overfitting evidence**
- OPRO (Yang et al. 2023, arXiv:2309.03409): optimized instructions score 5-20 pp higher on train than on test. Their fixes are a bigger training set and early stopping.
- Schneider et al. (2024/ICML 2025, *HbBoPs*, arXiv:2412.07820): validation evaluation is the cost bottleneck. Hyperband and successive halving give candidates more validation instances adaptively.
- Singh (2026, *MAGE*, arXiv:2607.11944): with N_train = 30, "well-designed fixed prompts outperform all reflective optimizers".
- **Unverified**: a 2026 case study of GEPA on a Datasette agent reportedly had train accuracy rise from 90% to 95% while held-out dropped from 95% to 85%. It used only 10 test items and comes from a secondary news source.

**Recommended protocol**
1. Use racing or successive halving on dev: start all candidates on about 10 tasks × 1 trial, drop clear losers, then give the survivors more tasks or trials.
2. Pre-register **one** primary comparison per target on held-out: the chosen candidate vs the baseline (non-inferiority), and the chosen candidate vs the plain swap (superiority).
3. If several targets are reported (Super, Nano, mix), apply Holm correction over them, or label the extra comparisons as exploratory.
4. Repeated random splits or cross-validation are possible but expensive for an optimizer. A single large untouched holdout is simpler and more honest.

---

## 5. LLM-as-a-judge reliability and validation

**Zheng, L., et al. (2023). *Judging LLM-as-a-Judge with MT-Bench and Chatbot Arena*. NeurIPS 2023 D&B. arXiv:2306.05685. https://arxiv.org/abs/2306.05685**
- Position bias: when positions were swapped, GPT-4 was consistent only **65%** of the time (30% favoured the first position). GPT-3.5 was consistent 46.2% and Claude-v1 23.8%.
- Verbosity bias: under a "repetitive list" attack the judge failed 91.3% of the time for GPT-3.5 and Claude-v1, and 8.7% for GPT-4.
- Self-enhancement: GPT-4 gave its own answers about +10% win rate and Claude-v1 about +25%, though the evidence is limited.
- Agreement with humans: GPT-4 vs humans 66% (with ties) and 85% (no ties), against 63% and 81% between humans.
- Fixes: judge both orders and count an inconsistent verdict as a tie. Reference-guided judging cut the math failure rate from 70% to 15%.

**Panickssery, A., Bowman, S. R., Feng, S. (2024). *LLM Evaluators Recognize and Favor Their Own Generations*. arXiv:2404.13076. https://arxiv.org/abs/2404.13076**
- GPT-4 and Llama 2 recognise their own outputs better than chance. Fine-tuning shows a **linear correlation between self-recognition and self-preference**.

**Wataoka, K., Takahashi, T., Ri, R. (2024). *Self-Preference Bias in LLM-as-a-Judge*. arXiv:2410.21819. https://arxiv.org/abs/2410.21819**
- Self-preference shows up as a preference for text with lower perplexity to the judge, whoever wrote it. GPT-4 shows high self-preference.

**Spiliopoulou, E., et al. (2025). *Play Favorites: A Statistical Method to Measure Self-Bias in LLM-as-a-Judge*. arXiv:2508.06709. https://arxiv.org/abs/2508.06709**
- A framework that separates self-bias from real quality differences by using an independent (human) rating. Over 5,000 prompt-completion pairs and 9 judges, GPT-4o and Claude 3.5 Sonnet favoured their own outputs **and their own family's**. **Unverified (secondary source)**: inflation of about +0.42 points for self and +0.28 for family.

**Awuni, D. A., et al. (2026). *Who Judges Matters: Measuring Family-Conditioned Preference in LLM-as-Judge Panels*. arXiv:2609.17857. https://arxiv.org/abs/2609.17857**
- Llama, Qwen, Gemma and Yi all showed a same-family lift of **3.4-8.4 pp**. **55.4% of AB/BA pairs reversed**, so position bias is a separate failure mode. The study did not include Nemotron.

**Thakur, A. S., et al. (2024/2025). *Judging the Judges: Evaluating Alignment and Vulnerabilities in LLMs-as-Judges*. GEM² 2025. arXiv:2406.12624. https://arxiv.org/abs/2406.12624**
- 13 judges were tested. Only the largest judges aligned reasonably with humans, and even they stayed well below human-human agreement, with scores up to 5 points off. Judges were lenient. "Judges with high percent agreement can still assign vastly different scores", so report Cohen's κ or another chance-corrected measure, not only percent agreement.

**Dubois, Y., Galambosi, B., Liang, P., Hashimoto, T. (2024). *Length-Controlled AlpacaEval*. COLM 2024. arXiv:2404.04475. https://arxiv.org/abs/2404.04475**
- They fit a GLM of the judge's preference on the length difference and predict at zero length difference. Spearman correlation with Chatbot Arena rose from **0.94 to 0.98**.
- *Implication*: rewritten harnesses that add "verify" steps or few-shot formatting change answer length. Regress judge preference on the length difference to check for this.

**Boyeau, P., Angelopoulos, A. N., Yosef, N., Malik, J., Jordan, M. I. (2024). *AutoEval Done Right: Using Synthetic Data for Model Evaluation*. ICML 2025. arXiv:2403.07008. https://arxiv.org/abs/2403.07008**
- Prediction-powered inference: a small human-labelled set estimates the judge's bias, which is then corrected on the large judge-labelled set. This gives valid CIs and up to **50%** more effective sample size. Code: `ppi_py`.

**Nemotron self-preference.** I found **no published study** of whether Nemotron-family judges favour Nemotron outputs (searched 2026-10-29). The Nemotron 3 Super technical report uses Qwen models as judges in its data pipeline, which does not address the question. Based on the general findings, expect two effects:
- Self-bias from Ultra judging Ultra's own baseline answers. This would *penalise* candidates, so it is conservative for "within the bar".
- Family bias, which affects all arms about equally because every arm is Nemotron, so it mostly cancels.

The risk to "rewrite beats swap" is mainly **length and format bias**, not self-bias. All of this is **unverified for Nemotron** and should be measured as in Section 7e.

**Sample sizes for validating a judge.**
- To estimate agreement p within ±10 pp at 95% (n = 1.96²·p(1−p)/0.1²): **35** items at p = 0.9, **62** at 0.8, **81** at 0.7 and **97** at 0.5. Within ±5 pp needs 139 / 246 / 323 / 385.
- To estimate Cohen's κ within ±0.10 with p_o = 0.8 and p_e = 0.5 (SE(κ) ≈ sqrt(p_o(1−p_o)/n)/(1−p_e)): **about 250** items.
- If items are clustered (several outputs per question), use clustered SEs, which shrink the effective n.
- When the positive class is near 94% (as in the README's success rates), κ becomes unstable (the "kappa paradox"). Report sensitivity and specificity, i.e. the judge's false-pass and false-fail rates, alongside κ.

---

## 6. Reporting standards and examples

- **Epoch AI Benchmarking Hub** (https://epoch.ai/benchmarks): most models run 16× on GPQA Diamond and AIME and 8× on MATH L5. Error bars are ±1 SE, computed following Miller 2024. Token counts are shown in the log viewer.
- **UK AISI Inspect** (https://inspect.aisi.org.uk/metrics.html): `stderr()` gives the SE of the mean, with clustered SEs via `stderr(cluster=...)`. There are `ci()` and `ci_wilson()` intervals. `epochs=Epochs(5, "mode")` runs repeated trials, with reducers `mean`, `median`, `mode`, `majority`, `max`, `pass_at_{k}`, `pass_k_{k}` (all k succeed) and `at_least_{k}`.
- **lm-evaluation-harness**: reports a `stderr` per task metric, with bootstrap for non-mean aggregations (`--bootstrap_iters`). Details are **unverified** here.
- **HAL** (Kapoor et al. 2025): accuracy-cost Pareto frontiers, logged tokens and cost per run, and a reliability dashboard.
- **SWE-bench** leaderboards mostly show single-run % resolved without CIs, which Bjarnason et al. 2026 criticise. This is a counter-example to avoid.

**A trustworthy Downshift results table should show:**
| Column | Content |
|---|---|
| Split | held-out, with n tasks, K trials per task and whether runs were fresh or replays |
| Success | pass^1 with 95% Wilson/Bayes interval, plus pass^K |
| Δ vs baseline | paired Δ and 95% CI (90% CI for non-inferiority), with the margin M and a verdict: non-inferior / inferior / inconclusive |
| Δ vs plain swap | paired Δ and 95% CI, with a verdict |
| Quality (judge) | mean and CI, the judge model, position-swap consistency and the judge's validated agreement |
| Cost / run | mean and bootstrap CI over tasks, the paired cost ratio with CI, and tokens |
| Selection | number of candidates tried, dev size × K, and the selection rule |
| Pre-registration | margin, α, primary comparisons and multiplicity correction |

---

## 7. Proposed protocol for Downshift

The tables in Section 2 assume ICC = 0.5 and ρ = 0.8. **Replace these assumptions with your pilot estimates.**

**(a) Pilot to estimate variance**
- On each agent with ground truth (text2sql, plus any other graded agent), run the baseline and the plain swap, **fresh**, on **30 tasks × 3 trials** per system. That is 180 agent runs per target.
- Compute per-system σ̂²_w, ω̂² for the pair, the ICC, ρ, discordance ψ, and the replay-vs-fresh gap on the same tasks.
- Then compute n(K) with the formula in Section 2 and plan using the upper end of the ω̂² CI.

**(b) Sizes for a 10 pp target**
- **Dev (selection):** use racing.
  - Round 1: every candidate on 20 tasks × 1 trial.
  - Keep the top 2 plus the plain swap. Round 2: give them another 30 tasks × 2 trials.
  - That totals about 50 tasks. With K = 3 at n = 50, the chance of keeping a candidate that is truly 10 pp worse falls to about 2%.
- **Held-out (reporting):** at least **80-100 tasks × 3 trials**, which gives a 10 pp MDE of about 9.4-11.7 pp at n = 100 and K = 3. If tasks are cheap to add, use **200 tasks × 1 trial** instead.
  - text2sql: Spider has over 1,000 dev questions with gold SQL, so going from 40 to 150-250 tasks is easy and is the single biggest improvement.
  - Research agent: 42 questions is too few for a 10 pp claim; the best achievable with 17 held-out tasks is 14-23 pp at any K. Either add questions with verifiable answers or state the MDE honestly, for example "this comparison can detect only ≥ 25 pp gaps".
- **Cost:** roughly 300 runs × (number of candidates + 2) per target. On a flat-rate subscription the cost is wall-clock time, not dollars. On Token Factory, estimate from models.yaml before running, because the $15 cap applies (CLAUDE.md).

**(c) Tests**
- **"Rewrite beats plain swap"** (superiority, pre-registered, two-sided α = 0.05 or one-sided 0.025):
  - Compute the paired per-task difference in mean success over K trials.
  - Test with a sign-flip permutation test over tasks or a paired t-test. With K = 1, use exact McNemar.
  - Report Δ with a 95% cluster-bootstrap or paired-Bayes CI, resampling tasks and keeping each task's trials together.
  - Keep the rewrite only if the lower CI bound is above 0. Otherwise recommend the plain swap, because it is simpler at equal evidence.
- **"Candidate within M of baseline"** (non-inferiority):
  - H₀: p_cand − p_base ≤ −M against H₁: > −M, at one-sided α = 0.05.
  - Declare non-inferior if the **lower bound of the 90% two-sided CI of the paired Δ is above −M**.
  - Sample sizes with a true Δ of 0, p = 0.75 and ICC 0.5:
    - M = 10 pp: 140-174 tasks at K = 1, 62-97 at K = 3, 35-70 at K = 10.
    - M = 5 pp: 557-696 at K = 1, 248-387 at K = 3.
    - M = 15 pp: 62-78 at K = 1, 28-43 at K = 3.
  - The current rule, "one-run drop allowed", is a point-estimate rule: it passes even when the CI reaches −30 pp. Replace it with this test, and add a third verdict, **inconclusive**, for when the CI crosses −M but the point estimate is above −M.
- **Several targets** (Super, Nano, mix): apply Holm over the 3 non-inferiority tests, or name one primary target.

**(d) Reporting**
- Use the table in Section 6.
- Always print n, K, fresh vs replay, the CI, the verdict, the MDE, the number of candidates tried and the dev size.
- Show pass^K next to pass^1.
- Show cost per run with a bootstrap CI and the paired cost ratio.
- Never present a dev score as a result.
- Keep periodic **fresh-run audits** (two or more trials) of the chosen harness, and report replay vs fresh side by side.

**(e) Validating the Ultra judge on the research agent**
1. Write a short reference answer and 2-5 required key facts for each of the 42 questions. This takes a few hours of human work.
2. For each question, collect 3-4 outputs: the baseline, the swap and the chosen rewrite, from existing runs. That gives about **126-168 outputs**.
3. A human labels each output correct or incorrect against the reference, and labels pairwise preference for one pair per question. This meets the ±10 pp agreement target of about 62-97 items. Estimating κ to ±0.1 would need about 250 items.
4. Run the judge **in both orders** on every pair. Report:
   - position-flip consistency;
   - agreement and κ with the human pairwise label;
   - judge false-pass and false-fail rates for "correct" (rubric correct ≥ threshold) against human correctness;
   - clustered SEs by question.
5. **Self-preference check**: re-judge the same pairs with a judge from a different model family. Compare how often each judge prefers the Ultra baseline *among pairs where the human called it a tie or preferred the candidate*, following the Play Favorites logic.
6. **Length check**: logistic regression of the judge's preference on the length difference, as in LC-AlpacaEval.
7. **Acceptance bar** (team choice, not from literature): position consistency ≥ 80%, human agreement ≥ 75% with a lower CI bound ≥ 65%, and no significant self or length effect. If the judge fails, prefer reference-guided judging, since Zheng et al. cut math failures from 70% to 15% that way, or use prediction-powered inference (ppi_py) to correct the judge-based success rate with the labelled subset.

---

## Top 10 takeaways

1. With 16 held-out tasks and one replay, a single pass rate has a 95% CI of about ±21-24 pp, and the smallest paired difference detectable at 80% power is about 34 pp. The observed swings of 3 tasks (18.75 pp) are ordinary noise.
2. Even with infinitely many trials, 16 tasks cannot resolve 10 pp (MDE about 14-23 pp), because between-task variance only falls with more tasks. **Add tasks first, trials second.** For a fixed run budget, more tasks at K = 1 is always the most efficient choice when tasks are available.
3. For a 10 pp paired difference at 80% power, plan about 200-250 tasks × 1 trial, or about 90-140 tasks × 3 trials. Confirm this with a pilot (30 tasks × 3 trials, fresh) that estimates ω² and σ²_w (Miller 2024 formula).
4. Always compare on the *same* tasks with paired differences. Pairing cuts variance by 2·Cov/n.
5. At n < 100, CLT intervals under-cover; even at N = 100, a nominal 95% covers only 92.5% (Bowyer et al. 2025). Use Wilson or Beta intervals and paired Bayesian or permutation tests.
6. Temperature 0 is not deterministic on served models: 80 of 1,000 completions were unique (Thinking Machines 2025), accuracy varied up to 15% (Atil et al.), and SWE-bench single-run swings were 2.2-6.0 pp even on 500 tasks (Bjarnason et al. 2026). Run K ≥ 3 and report pass^1 together with pass^k (τ-bench).
7. Picking the best of 3-4 candidates on 10 dev tasks inflates the winner's dev score by about 13-15 pp and picks a truly 10 pp worse candidate 26% of the time. Use racing or successive halving, make dev sets of 50 or more, and never report dev scores. GEPA selects on about 300 validation items, and DSPy recommends 80% of data for validation.
8. Replace the "one-run drop allowed" bar with a pre-registered **non-inferiority test**: the lower bound of the 90% CI of the paired Δ must be above −M. Make "inconclusive" an allowed verdict. M = 10 pp needs roughly 60-100 tasks at K = 3.
9. "Rewrite beats plain swap" should be a pre-registered paired superiority test. Default to the plain swap unless the rewrite's CI excludes 0, and apply Holm across targets.
10. The Ultra judge has never been validated, and no published study covers Nemotron self-preference. Label about 130-170 outputs from the 42 research questions against reference answers. Measure position-flip consistency, agreement and κ (±10 pp needs about 62-97 items; κ ±0.1 needs about 250), self or family bias with a judge from another family, and length bias. Then use reference-guided judging or PPI to correct the judge's estimates.
