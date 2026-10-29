# Can prompt and harness rewriting lift a small model? Literature review for Downshift

_Written 2026-10-29. Desk research only: no model calls and no runs of Downshift._

## How this review was done

**Sources.** Numbers come from arXiv abstract or HTML pages, model cards and vendor docs. Most were read
directly. Items seen only in search summaries, or not traced to a primary table, are marked
**unverified**. "pp" means absolute percentage points.

**The problem being studied.** On Spider dev (40 questions, graded by execution accuracy, EX):

| Harness | EX |
|---|---|
| Nemotron 3 Ultra | 77.5% |
| Plain swap to Super | 76% |
| Plain swap to Nano | 56% |
| Downshift's rewritten Nano harnesses | 12.5% to 50% |

Nano's failures are mostly format failures:
- it answers in prose instead of SQL;
- it writes tool calls as text instead of making real tool calls, especially when thinking is off.

**Downshift's loop today.**
- Ultra rewrites the whole harness.
- 2 rounds, each scored on about 10 replayed tasks.
- The best candidate is checked once on the held-out 40%.

---

## 1. Automatic prompt and agent optimizers

### DSPy compiling and BootstrapFewShot

**Source.** Khattab et al., *DSPy: Compiling Declarative Language Model Calls into Self-Improving
Pipelines*, 2023. https://arxiv.org/abs/2310.03714

**What they did.**
- Optimizes **few-shot demos**. BootstrapFewShot runs a teacher, keeps the traces that pass the metric, and
  uses them as demos. Search is random, and results can be ensembled.
- BootstrapFinetune changes the model weights instead.
- Data: GSM8K and HotPotQA, each with 200 train and 300 dev examples.
- Cost: compiling takes minutes to tens of minutes, or a few thousand program runs.
- No reflective feedback.

**Key numbers.**
- GSM8K test, GPT-3.5: 25.2 zero-shot → 81.6 with CoT, bootstrapped demos and an ensemble.
- GSM8K test, Llama2-13b: 9.4 → 46.9.
- The "T5-770M is competitive with GPT-3.5" result (39.3% EM on HotPotQA) came from **fine-tuning** on
  200 labelled and 800 unlabelled questions. It is not a prompt-only result.
- Baselines were weak hand-written prompts.

**Implication for Downshift.** DSPy's large gains come from adding CoT and demos to weak prompts. Downshift
starts from a good Ultra harness, so this headroom is not there. The demo lever, though, is directly
applicable: Downshift has Ultra's successful traces.

### MIPROv2

**Source.** Opsahl-Ong et al., *Optimizing Instructions and Demonstrations for Multi-Stage Language Model
Programs*, EMNLP 2024. https://arxiv.org/abs/2406.11695

**What they did.**
- A larger model proposes **instructions and demos** for each module.
- Bayesian search (TPE) over combinations. Each trial is scored on a minibatch; the best candidates are
  periodically re-scored on the full set.
- Task model: **Llama-3-8B**.
- Data: typically 500 train / 500 dev / 1,200–2,000 test.
- Budget: 20–50 full-evaluation trials, about 300 minibatch trials, 5 runs per method.

**Key numbers.**
- "Up to 13%"; MIPRO is best on 5 of 7 programs.
- HotPotQA: 46.4 with MIPRO, 36.8 with 0-shot instruction-only MIPRO, 45.8 with bootstrap random search.
  Demos did most of the work.
- On Iris and Heart Disease, which have 75–120 training examples, plain bootstrap beat MIPRO (94.1 vs 88.6).
- The authors report "high variation" across demo sets.
- Small model to large model: not shown.

**Implication for Downshift.** For an 8B-class task model, **bootstrapped demos beat instruction
rewriting**. Rewriting instructions mainly helps on tasks with conditional rules.

### GEPA (the design closest to Downshift's)

**Source.** Agrawal et al., *GEPA: Reflective Prompt Evolution Can Outperform Reinforcement Learning*, 2025.
https://arxiv.org/abs/2507.19457

**What they did.**
- Optimizes instructions only.
- A reflection LM reads each module's prompt, the full traces, and a **natural-language feedback string**
  from a task-specific feedback function. Examples of that feedback: which gold documents were missed, or
  which constraints failed.
- It mutates one module at a time.
- **Pareto selection over training instances.** Every candidate that is best on at least one instance is
  kept, and parents are sampled in proportion to how many instances they win. This beat both "always take
  the best" and beam search.
- Minibatch size: **3**.
- Splits: 150 train / 300 val / about 300 test (HotpotQA, HoVer, IFBench), and 111/111/221 (PUPA).
- Budget: 1,839–7,051 rollouts per task, matched to MIPROv2 "heavy". Most of it goes to validation
  scoring; counting train rollouts only, it needs 79–737 to reach its best. GRPO used 24,000 rollouts.

**Key numbers.**

| Model | Baseline | MIPROv2 | GRPO | TextGrad | Trace | GEPA |
|---|---|---|---|---|---|---|
| Qwen3-8B, aggregate | 45.2 | 47.8 | 48.9 | — | — | **54.9 (+9.6)** |
| GPT-4.1-mini, aggregate | 53.0 | 58.7 | — | 59.1 | 56.3 | **65.2 (+12.2)** |

- Abstract: GEPA beats GRPO by about 10% on average with up to 35× fewer rollouts.
- Gains concentrate on tasks with rich feedback. HotpotQA rose 42.3 → 62.3 and HoVer 35.3 → 52.3, but
  IFBench rose only 36.9 → 38.6 and AIME 27.3 → 32.0.
- MIPROv2 *lowered* Qwen3-8B on AIME (27.3 → 20.0).
- **Small vs large (our comparison, not the paper's).** Optimized Qwen3-8B (54.9) only just passes
  *unoptimized* GPT-4.1-mini (53.0). Optimized GPT-4.1-mini gained more, so the gap stayed.

**Implication for Downshift.** Downshift's loop already looks like GEPA: an LLM reflects on failures and
proposes rewrites. But GEPA's gains need three things Downshift lacks:
- rich, specific feedback for each example;
- per-module mutations;
- Pareto selection over hundreds of validation items and thousands of rollouts.

### OPRO, and "Revisiting OPRO"

**Sources.**
- Yang et al., *Large Language Models as Optimizers*, 2023. https://arxiv.org/abs/2309.03409
- Zhang, Yuan, Avestimehr, *Revisiting OPRO: The Limitations of Small-Scale LLMs as Optimizers*, Findings of
  ACL 2024. https://arxiv.org/abs/2405.10276

**What they did (OPRO).**
- Optimizes the instruction only, from (prompt, score) pairs.
- Each step shows the top 20 past instructions and proposes 8 new ones, for about 200 steps.
- Data: about 260 GSM8K examples.

**Key numbers.**
- GSM8K: "up to 8%" (PaLM 2-L, 71.8 → 80.2). BBH: "up to 50%" over human prompts.
- With the smaller text-bison scorer there was no gain (64.4 vs 64.4).
- The authors note train accuracy is "often 5%-20% higher than test", and that the optimizer "does not
  effectively use error cases".
- Revisiting OPRO, with the same small model as optimizer and scorer:
  - Mistral-7B: 37.5 → 32.1.
  - LLaMA-2-70B: 39.4 → 28.0.
  - LLaMA-2-13B ranged from 10.4 to 31.2 depending on the meta-prompt.
  - Few-shot CoT beat OPRO on small models (48.7 vs 28.0).

**Implication for Downshift.** Score-only optimization overfits small dev sets and does little for small
models. Simple, explicit instructions plus demos is the baseline to beat.

### TextGrad

**Source.** Yuksekgonul et al., *TextGrad: Automatic "Differentiation" via Text*, 2024 (later in Nature).
https://arxiv.org/abs/2406.07496

**What they did.**
- Optimizes gpt-3.5-turbo's system prompt.
- **GPT-4o writes textual "gradients" from failures**, so the feedback is reflective.
- Batch size 3, 12 iterations. BBH splits are 50/100/100.
- A new prompt is accepted only if validation improves.

**Key numbers.** Object Counting 77.8 → 91.9; GSM8K 72.9 → 81.1. In SPO's later comparison, TextGrad was
roughly equal to CoT (63.9 vs 63.8).

**Implication for Downshift.** Accept a candidate only if it beats the incumbent on validation. Downshift
already requires a rewrite to beat the swap, and that rule is right.

### ProTeGi (APO)

**Source.** Pryzant et al., *Automatic Prompt Optimization with "Gradient Descent" and Beam Search*,
EMNLP 2023. https://arxiv.org/abs/2305.03495

**What they did.**
- Writes natural-language critiques of minibatch errors, then edits the prompt.
- Beam search (width 4) with UCB bandit selection.
- Minibatch 64, 6 steps.
- 50 dev and 150 test examples. Model: gpt-3.5-turbo. Four classification tasks only.

**Key numbers.** "Up to 31%" over the initial prompt. All learning curves **peak at about 3 steps, then
decline**, which the authors attribute to overfitting.

**Implication for Downshift.** Even with 50-example dev sets, iterating past a few rounds overfits. More
rounds will not fix Downshift's problem without more data.

### PromptAgent

**Source.** Wang et al., *PromptAgent: Strategic Planning with Language Models Enables Expert-level Prompt
Optimization*, 2023. https://arxiv.org/abs/2310.16427

**What they did.**
- MCTS over prompt edits. GPT-4 writes error feedback on GPT-3.5's failures (reflective).
- 60–2,000 training examples per task.

**Key numbers.**
- BBH: 0.802 vs 0.707 for CoT.
- Transfer of the GPT-3.5-optimized prompts:
  - to GPT-4: 0.839 vs 0.759 for the human prompt;
  - to PaLM 2: 0.441 vs 0.392, winning only 7 of 12 tasks, with some large drops.
- The authors expect small models "may not adeptly grasp" expert prompts. No small models were tested.

**Implication for Downshift.** Long expert-style prompts transfer **upward**, not downward. An Ultra-written
expert prompt is the wrong shape for Nano.

### EvoPrompt and Promptbreeder

**Sources.**
- Guo et al., *EvoPrompt*, ICLR 2024. https://arxiv.org/abs/2309.08532
- Fernando et al., *Promptbreeder*, 2023. https://arxiv.org/abs/2309.16797

**What they did.**
- **EvoPrompt:** GPT-3.5 runs genetic-algorithm and differential-evolution operators. Population 10 for 10
  iterations. Dev sets have 50–200 examples.
- **Promptbreeder:** PaLM 2-L, population 50, more than 2,000 evaluations per run.
- Neither uses failure feedback.

**Key numbers.**
- EvoPrompt, Alpaca-7b on 7 tasks: 71.07 → 77.05 (+6.0). BBH average: +3.5.
- Promptbreeder, GSM8K: 83.9 vs 80.2 for OPRO.

**Implication for Downshift.** Large prompt populations and thousands of evaluations buy a few pp. That is
not affordable on a $15 budget.

### Trace (OptoPrime)

**Source.** Cheng, Nie, Swaminathan, *Trace is the Next AutoDiff*, 2024.
https://arxiv.org/abs/2406.16218

**What they did.** Optimizes prompts and code from execution traces plus feedback. On BBH: 15 train and 5
validation examples.

**Key numbers.** BBH: 78.6 vs 71.6 for DSPy-COPRO. In GEPA's comparison it gave only +3.3 and *hurt* PUPA
(78.6 → 74.2).

**Implication for Downshift.** Small train and validation sets give fragile gains.

### Agent Symbolic Learning

**Source.** Zhou et al., *Symbolic Learning Enables Self-Evolving Agents*, 2024.
https://arxiv.org/abs/2406.18532

**What they did.** A natural-language "loss" and "gradients" are passed back through the agent pipeline to
update prompts, tools and the pipeline. This is reflective feedback.

**Key numbers.**
- MATH, GPT-3.5: 23.8 → 38.8.
- HotpotQA F1: 37.5 → 44.8.
- It lost to DSPy on HumanEval.
- No reporting of split sizes or variance.

**Implication for Downshift.** Proof of concept only. No evidence for lifting a small model to a large one.

### AFlow

**Source.** Zhang et al., *AFlow: Automating Agentic Workflow Generation*, ICLR 2025.
https://arxiv.org/abs/2410.10762

**What they did.**
- MCTS over workflow **code** built from operators: ensemble, review/revise, self-test.
- The optimizer is Claude-3.5-Sonnet; the executor is gpt-4o-mini.
- Split: 20% validation, 80% test. 20 iterations, each workflow run 5× on validation.

**Key numbers.**
- Average 80.3 vs 76.0 for the best hand-built workflow.
- HumanEval: gpt-4o-mini with its workflow scores 94.7, vs GPT-4o with plain prompting at 93.9.
- A workflow found with DeepSeek dropped to 90.8 on gpt-4o-mini: "different models need different
  workflows".
- The exact task behind the "4.55% of the cost" claim is **unverified**.

**Implication for Downshift.** The one clear case of "small model beats large model" in this literature
came from **extra test-time calls** (ensembling and self-tests), not from prompt wording.

### ADAS (Meta Agent Search)

**Source.** Hu, Lu, Clune, *Automated Design of Agentic Systems*, ICLR 2025.
https://arxiv.org/abs/2408.08435

**What they did.** A GPT-4 meta agent writes agent code, evaluated on GPT-3.5. ARC uses 20 validation and
60 test questions, 5 runs each.

**Key numbers.**
- DROP F1: 79.4 vs 65.8.
- Transfer of the discovered agents, best agent vs best baseline:
  - Claude-Sonnet 48.3 vs 39.3
  - GPT-4 37.0 vs 23.0
  - **Claude-Haiku 9.7 vs 6.3**
- Gains were small where model knowledge is the bottleneck (+1.7 to +2.0).

**Implication for Downshift.** A better agent design does not make a weak model strong; the weak model
stays weak in absolute terms.

### PromptWizard

**Source.** Agarwal et al. (Microsoft), *PromptWizard*, 2024. https://arxiv.org/abs/2405.18369

**What they did.** Critique and synthesis of instructions and in-context examples (reflective).
**25 training examples** by default, and about **69 API calls per task**.

**Key numbers.**
- GSM8K: Llama-70B 56.8 → 90.2; GPT-3.5 57.1 → 75.6. The paper also states 90 for GPT-3.5, which is
  internally inconsistent.
- With 5 instead of 25 examples, accuracy fell from 87.0 to 81.9.
- Llama-3-8B was poor *as the optimizer*.

**Implication for Downshift.** This is the only method in the cheap regime Downshift runs in (about 25
examples, about 70 calls). It still relies on demos plus critique, not just instruction rewriting.

### 2025–2026 successors

**ACE (Agentic Context Engineering).** Zhang et al., 2025. https://arxiv.org/abs/2510.04618
- Generator, Reflector and Curator roles make **incremental delta bullet edits** to a "playbook" instead of
  rewriting the whole prompt.
- Model: DeepSeek-V3.1.
- AppWorld: 42.4 → 59.4, close to a GPT-4.1 production agent at 60.3.
- Finance task: 81.9, vs 72.5 for GEPA and 70.9 for MIPROv2.
- 357 rollouts vs 1,434 for GEPA.
- Performance degrades without reliable feedback.
- **Implication for Downshift:** deltas avoid "context collapse", where full rewrites erase details that
  worked. That supports editing the harness rather than regenerating it.

**MASS.** Zhou et al. (Google), 2025. https://arxiv.org/abs/2502.02533
- Optimizes prompts per block, then the topology, then prompts again for the whole workflow.
- Validation sets of 50–100.
- Mistral-Nemo-12B: 55.9 vs 40.4 for CoT.
- About 11 of the 14.9 pp come from stage-1 prompt and demo optimization: "optimize agents locally before
  scaling topology".

**SPO.** Xiang et al., 2025. https://arxiv.org/abs/2502.06855
- Label-free and judge-based: 3 samples × 10 iterations, about $0.15.
- Average 66.9 vs 66.6 for OPRO and 63.8 for CoT.
- Cheap, but the gains are small.

**SIMBA (DSPy).** Docs only, no paper: https://dspy.ai/api/optimizers/SIMBA/
- Finds high-variance "hard" examples, then adds a successful demo or a self-reflective rule.
- Default minibatch size 32.
- No peer-reviewed numbers.

**Databricks GEPA post**, *Building State-of-the-Art Enterprise Agents 90x Cheaper with Automated Prompt
Optimization*, 2025. https://www.databricks.com/blog/building-state-art-enterprise-agents-90x-cheaper-automated-prompt-optimization
- gpt-oss-120b + GEPA beats *unoptimized* Claude Opus 4.1 by +2.2 pp on information extraction (IE Bench),
  at about 90× lower serving cost.
- Optimized Opus gained +6.4, so it stayed ahead.
- No sample sizes or variance reported. Vendor post.

**Myles, Schrempf, Harris-Birtill**, *Importance of Prompt Optimisation for Error Detection in Medical
Notes Using Language Models*, 2026. https://arxiv.org/abs/2602.22483
- GEPA, 2,189 train / 574 val / 597 test. Verified from the HTML table:

  | Model | Baseline | GEPA |
  |---|---|---|
  | GPT-5 | 0.669 | 0.785 |
  | Qwen3-32B | 0.578 | 0.690 |
  | Qwen3-14B | 0.606 | 0.683 |
  | Qwen3-8B | 0.568 | 0.631 |
  | Qwen3-4B | 0.544 | 0.619 |
  | **Qwen3-1.7B** | 0.539 | **0.515** |
  | **Qwen3-0.6B** | 0.513 | **0.514** |

- GPT-5 as the reflector for the 0.6B model was worse, possibly "overfitting … to the validation data".
- **Implication for Downshift:** a 14B–32B model with a few thousand examples can pass an *unoptimized*
  frontier baseline. Below about 2–4B the gain disappears. Nano has about 3B active parameters, so it sits
  near that boundary (an analogy by parameter count, not tested).

**p1.** Gao et al., *Better Prompt Optimization with Fewer Prompts*, 2026. https://arxiv.org/abs/2604.08801
- Verified from the abstract: optimization works only when "variance among system prompts" outweighs
  generation noise. Adding heterogeneous tasks can wash that signal out.
- Selecting a few high-variance tasks works better.
- The small-model numbers (GEPA flat on Qwen3-1.7B and 4B for AIME) come from a subagent's reading of the
  paper body and are **unverified** here.

**Zhou et al., 2025.** https://arxiv.org/abs/2505.08303
- EvoPrompt, ProTeGi and BPO give about 0.8–2.8% relative gains on frontier models.
- Gains **shrink with scale**: on SST-5, +12% for Qwen2.5-7B and +1.1% at 671B.
- The SST-5 numbers come from the subagent's reading and are **unverified** here.

### Answers to the Q1 sub-questions

**Which methods use reflective feedback from failing traces?**
- GEPA, TextGrad, ProTeGi, PromptAgent, PromptWizard, Agent Symbolic Learning, ACE, Trace and SIMBA.
- Score-only methods: OPRO, EvoPrompt, Promptbreeder, MIPROv2's instruction search.
- The reflective methods with the biggest gains (GEPA, ACE) give the reflector **specific diagnostic
  feedback per example**, not just a score.

**Validation protocols.**
- GEPA: train/val/test with minibatch 3 and Pareto selection on val.
- MIPROv2: minibatch trials plus periodic full-val evaluation.
- ProTeGi: beam search with a UCB bandit.
- TextGrad: accept only on val improvement.
- AFlow and ADAS: small validation sets with 5 repeats each.

**Small model lifted to a large model?**
- Shown only against an *unoptimized* large baseline, with a small starting gap of about 2–10 pp, on narrow
  tasks with a checkable metric: Databricks, the medical-notes study, AFlow HumanEval.
- When the large model is also optimized, the gap stays (GEPA tables, Databricks, medical-notes study).
- Very small models gain nothing or regress: Qwen3 0.6B and 1.7B, LLaMA-2 with OPRO, Haiku with ADAS.

---

## 2. Prompts do not transfer across models; migration guides; what small models need

### Sources

**Sclar et al., *Quantifying Language Models' Sensitivity to Spurious Features in Prompt Design*
(FormatSpread), ICLR 2024.** https://arxiv.org/abs/2310.11324
- Formatting alone moves accuracy by "up to 76 accuracy points" on LLaMA-2-13B.
- "Format performance only weakly correlates between models."
- **Implication for Downshift:** what works on Ultra predicts little about Nano. Format must be tuned on the
  target, with enough samples to see it.

**He et al., *Does Prompt Formatting Have Any Impact on LLM Performance?*, 2024.**
https://arxiv.org/abs/2411.10541
- GPT-3.5 swings up to 40% by format.
- Overlap of the best formats across model families has IoU often below 0.2. Within one family it is
  above 0.7.

**PromptBridge.** Wang et al., Dec 2025. https://arxiv.org/abs/2512.01420
- HumanEval: GPT-5's best prompt scores 99.39 on GPT-5 but **68.70 on Llama-3.1-70B**. Llama's own
  optimized prompt scores 79.47.
- PromptBridge transfer recovers 79.88.
- **Implication for Downshift:** carrying a prompt across models costs about 10 pp, even at 70B.

**MAPO.** Chen et al., *Model-Adaptive Prompt Optimization*. https://arxiv.org/abs/2407.04118
- Argues prompts should be adapted per model. The abstract gives no numbers.

**Mizrahi et al., *State of What Art? A Call for Multi-Prompt LLM Evaluation*, TACL 2024.**
https://arxiv.org/abs/2401.00595
- 6.5M instances, 20 LLMs. Rankings flip across paraphrases.
- **Implication for Downshift:** a single-prompt difference of a few pp on a few tasks is inside prompt
  variance.

**IFScale.** Jaroslawicz et al., *How Many Instructions Can LLMs Follow at Once?*, 2025.
https://arxiv.org/abs/2507.11538

| Model | 10 instructions | 50 instructions |
|---|---|---|
| gpt-4.1-nano | 94% | 72.8% |
| gpt-4o-mini | 94% | 65.6% |
| llama-4-scout | 100% | 54.4% |

- Later instructions are dropped first.
- **Implication for Downshift:** every rule an Ultra rewriter adds costs a small model accuracy.

**Shen et al., *Small LLMs Are Weak Tool Learners: A Multi-LLM Agent* (α-UMi), 2024.**
https://arxiv.org/abs/2401.07324
- One small model struggles to plan, call tools and summarize at once. Splitting the roles helps, though
  each role was fine-tuned.

**Vendor model-migration guides.** All say prompts need to be re-tuned when you change model:
- **OpenAI GPT-4.1 guide:**
  https://developers.openai.com/cookbook/examples/gpt4-1_prompting_guide
  - "existing prompts optimized for other models may not immediately work".
  - Passing tools only through the `tools` field, not described in the prompt, gave +2% on SWE-bench.
- **OpenAI GPT-5 guide:** https://developers.openai.com/cookbook/examples/gpt-5/gpt-5_prompting_guide
  - With minimal reasoning, results "can vary more drastically depending on prompt".
  - Contradictory instructions do the most damage.
- **Anthropic best practices:**
  https://platform.claude.com/docs/en/build-with-claude/prompt-engineering/claude-4-best-practices
  - Remove "CRITICAL/MUST" over-prompting.
  - Say what to do, not what to avoid.
  - Match the prompt's style to the output you want.
- **Google Gemini 3 guide:**
  https://docs.cloud.google.com/vertex-ai/generative-ai/docs/start/gemini-3-prompting-guide
  - Keep temperature at 1.0; lower values can cause looping or degraded output.

**NVIDIA model cards (decision-relevant).**
- **Nemotron 3 Nano 30B-A3B:** https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16
  - Recommended sampling:
    - reasoning on: T=1.0, top_p=1.0;
    - **tool calling: T=0.6, top_p=0.95;**
    - reasoning off: greedy decoding.
  - Reasoning is toggled with `chat_template_kwargs.enable_thinking` and is on by default.
  - Recommends high `max_tokens` (for example 10k) with reasoning on.
  - Turning reasoning off gives "a slight decrease in accuracy for harder prompts".
  - BFCL v4 53.8; τ²-bench average 49.0.
  - A HF discussion (https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16/discussions/3)
    traces broken tool parsing to a **too-low token budget** (truncation) and to parser configuration
    (`qwen3_coder` tool parser plus the `nano_v3` reasoning parser).
- **Nemotron 3 Nano tech report:** https://arxiv.org/abs/2512.20848
  - The reasoning-off mode was trained by stripping reasoning from **only a random 10% of samples**.
  - Tool calls use XML-style tags.
- **Nemotron 3 Super:** https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-BF16
  - T=1.0, top_p=0.95 for all tasks.
  - Has a `low_effort` mode.
  - Examples use max_tokens 16k.

**Belcak et al. (NVIDIA), *Small Language Models are the Future of Agentic AI*, 2025.**
https://arxiv.org/abs/2506.02153
- Position paper. Its recipe for replacing an LLM with a small model is: log → curate 10k–100k
  examples → cluster → **LoRA fine-tune**.
- Prompting is treated as a starting point.

### What matters for small models specifically

The evidence points to:
1. a single explicit output format, enforced at the API level where possible;
2. demos taken from successful runs;
3. shorter instructions with fewer constraints;
4. one narrow role per step;
5. the vendor's sampling settings.

It does **not** support long "expert" prompts written by a large model.

---

## 3. Text-to-SQL

| Source | What they did | Key numbers (Spider dev EX unless noted) | Implication for Downshift |
|---|---|---|---|
| Rajkumar, Li, Bahdanau, *Evaluating the Text-to-SQL Capabilities of LLMs*, 2022. https://arxiv.org/abs/2204.00498 | Codex, zero-shot, different prompt formats | Question only: 8.3% EX, with **only 14% valid SQL**. CREATE TABLE schema: 59.9. Plus 3 sample rows: 67.0. | Output validity is the first bottleneck; schema format is worth about 10 pp. |
| Gao et al., *Text-to-SQL Empowered by LLMs: A Benchmark Evaluation* (DAIL-SQL), VLDB 2024. https://arxiv.org/abs/2308.15363 | Prompt representation, few-shot and fine-tuning across open models | Representation alone, zero-shot: **CodeLlama-34B 40.3–68.5 (28 pp swing)**; LLaMA-2-70B-chat 28.6–46.2. Few-shot: LLaMA-13B 20.3 → 38.8 (5-shot). The rule "with no explanation" improves every model (up to about +3 EX). GPT-4: 72.3 → 83.5 with DAIL few-shot. | Prompt changes move small models 10–28 pp **in either direction**, depending on the model. A "SQL only, no explanation" rule is a documented cheap gain. |
| Pourreza & Rafiei, DIN-SQL, NeurIPS 2023. https://arxiv.org/abs/2304.11015 | Decomposition plus self-correction | GPT-4: 64.9 → 74.2. Codex-davinci: 61.5 → 69.9. Weaker Codex-cushman: 43.1 → 47.6. Self-correction: +0.9 (GPT-4), +2.6 (davinci); the effect depends on the prompt's wording. | Gains from decomposition shrink for weaker models. |
| Wang et al., MAC-SQL, COLING 2025. https://arxiv.org/abs/2312.11242 | Selector, Decomposer and Refiner agents | Refiner, which executes the SQL and fixes it: +4.6 on BIRD with GPT-4. SQL-Llama 7B: 65.5 alone, 76.3 inside MAC-SQL, after **fine-tuning on agent traces**. | Execution feedback is the largest single component. The 7B model needed fine-tuning to use the agent setup. |
| Li et al., OmniSQL, VLDB 2025. https://arxiv.org/abs/2503.02240 | Many open models evaluated under one prompt | Greedy zero-shot: **Qwen2.5-Coder-7B 73.4, 14B 78.1, 32B 77.7**; Llama-3.1-8B 61.8; GPT-4o-mini 70.4; GPT-4o 70.9; DeepSeek-V3 73.1. Fine-tuned OmniSQL-7B: 81.2. Majority vote over 8 samples: +0.4 to +0.6 on Spider. | **Prompted models of very different sizes reach about 70–78% on Spider dev.** Ultra and Super are at that ceiling. Capable 7B models reach about 73, so Nano at 56 is under-performing, which points to format failures. |
| Li et al., CodeS, SIGMOD 2024. https://arxiv.org/abs/2402.16347 · Pourreza & Rafiei, DTS-SQL, 2024. https://arxiv.org/abs/2402.01117 | Fine-tuned 1B–15B models | CodeS-7B 85.4. DTS-SQL with DeepSeek-7B 85.5. | Fine-tuning beats any prompted small model. |
| Scholak et al., PICARD, EMNLP 2021. https://arxiv.org/abs/2109.05093 | Constrained decoding to the SQL grammar | T5-Base 57.9 → 68.4 (**+10.5**); T5-3B 71.4 → 76.3. Unusable outputs fell to about 2%. | **The smallest model gained the most** from forcing valid output. |
| Chen et al., *Teaching LLMs to Self-Debug*, ICLR 2024. https://arxiv.org/abs/2304.05128 | Execution feedback on Spider | Codex 81.3 → 84.1. GPT-4 73.2 → 73.6. **StarCoder-15B 64.7 → 64.9.** | Self-debugging gives weak models almost nothing. |
| Pourreza et al., CHASE-SQL, 2024. https://arxiv.org/abs/2410.01943 · Sun et al., SQL-PaLM, 2023. https://arxiv.org/abs/2306.00739 · Lee et al., MCS-SQL, 2024. https://arxiv.org/abs/2405.07467 | Multiple candidates, chosen by execution result | Self-consistency over execution results: +5.8 (CHASE-SQL, BIRD) and +5.4 (SQL-PaLM). MCS-SQL: majority vote 89.2 vs 89.5 for its best selector. | Voting on executed results gives +2 to +6 pp and needs no rewriter. The gain shrinks near the Spider ceiling. |
| Gurajada et al., *Effectiveness of Prompt Optimization in NL2SQL Systems*, 2025. https://arxiv.org/abs/2505.20591 | Prompt optimization on BIRD with GPT-4o | MIPROv2 50.7 → 57.9 (+7.2). | The only rigorous DSPy text-to-SQL result found, and it used a strong model. |
| Amity blog, *Boosting Text-to-SQL Accuracy 7x with GEPA*, 2026. https://www.amity.co/ai-labs/gepa-text-to-sql | GEPA on a private set | 5.7% → 41.3%, starting from a deliberately naive one-line prompt. Model and sample size not disclosed. | Weak evidence. |

**Summary for text-to-SQL.**
- Prompting alone moves a small open model on Spider dev by roughly ±10–28 pp, mostly by fixing schema
  format and output format.
- Execution feedback (retry with the error message) is worth +1 to +5 pp for strong models and about 0
  for weak ones.
- The large recoverable gains for small models come from **turning invalid or missing output into valid
  SQL**: constrained decoding, a strict format, and retrying on unparsable output.
- Spider dev has been public since 2018 and is likely in training data, so it is not a great test. See
  Ranaldi et al., Findings ACL 2024 (https://arxiv.org/abs/2402.08100), and SPENCE, ACL 2026
  (https://arxiv.org/abs/2604.17771): Spider shows the "highest likelihood of training leakage".

---

## 4. Format and tool-calling failures; constrained decoding; thinking off

### Sources

**Qwen3 Technical Report, 2025.** https://arxiv.org/abs/2505.09388

| Model | BFCL v3, thinking / non-thinking | IFEval strict, thinking / non-thinking |
|---|---|---|
| 4B | 65.9 / 57.6 | 81.9 / 81.2 |
| 8B | 68.1 / 60.2 | 85.0 / 83.0 |
| **30B-A3B** | **69.1 / 58.6** | 86.5 / 83.7 |

- Qwen3-30B-A3B model cards, thinking vs non-thinking: TAU1-Airline 32.0 vs 18.0; TAU2-Airline 36.0 vs 18.0.
- Qwen then stopped shipping hybrid thinking, in favour of separately trained Instruct and Thinking models.
- **Implication for Downshift:** turning thinking off in a 30B-A3B hybrid model costs about 10 pp on tool
  calling and halves multi-turn agent success.

**Nemotron 3 Nano 4B model card (a sibling of the 30B model, not the 30B itself).**
https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Nano-4B-BF16

| Benchmark | Reasoning off | Reasoning on |
|---|---|---|
| BFCL v3 | 61.1 | 61.1 |
| IFEval | 82.8 | 87.9 |
| τ² Airline | 28.0 | 33.3 |
| τ² Retail | 34.8 | 39.8 |
| τ² Telecom | 24.9 | 33.0 |

- **Implication for Downshift:** single tool calls are unchanged, but **multi-turn tool use and
  instruction following drop** with thinking off.

**DeepSeek-V3.1 model card.** https://huggingface.co/deepseek-ai/DeepSeek-V3.1
- Tool calls are supported in **non-thinking** mode. Its agent benchmarks are reported for non-thinking.
- **Implication for Downshift:** a counter-example. Model families differ.

**Li et al., *When Thinking Fails: The Pitfalls of Reasoning for Instruction-Following*, NeurIPS 2025.**
https://arxiv.org/abs/2505.11423
- CoT *prompting* lowers IFEval: Llama-3-8B 75.2 → 59.0.
- These are non-hybrid models with prompted CoT, not native thinking toggles.

**Yin et al., *The Reasoning Trap*, 2025/2026.** https://arxiv.org/abs/2510.22977
- Thinking increases hallucinated tool calls when no suitable tool exists. With distractor tools, Qwen3-8B
  goes from 36.2% to 56.8%.

**BFCL "FC" vs "Prompt" modes.** https://gorilla.cs.berkeley.edu/leaderboard
- These are distinct evaluation modes: native tool-call support vs calls written as text.
- The size of the gap between them for the same model is **unverified**.

**vLLM tool-calling docs.** https://docs.vllm.ai/en/latest/features/tool_calling/
- A named `tool_choice` or `required` uses structured outputs, so the call is guaranteed to parse ("not a
  high-quality one").
- With `auto`, calls are extracted from raw text and "may occasionally be malformed".
- **Implication for Downshift:** forcing the tool call removes the "tool call written as text" failure.

**Nebius Token Factory docs.** https://docs.tokenfactory.nebius.com/ai-models-inference/function-calling.md
and https://docs.tokenfactory.nebius.com/ai-models-inference/json.md
- Function calling documents `auto` and a named-function `tool_choice`. `required` and `strict` are not
  documented.
- `response_format` supports `json_schema` and `json_object` on models tagged "JSON mode".
- **Implication for Downshift:** the fixes are available on the project's provider. Whether Nemotron 3 Nano
  is tagged "JSON mode" there has not been checked.

**Practitioner reports on tool tags ending up in `content`.**
- LiveKit blog, 2026: https://livekit.com/blog/your-model-isnt-bad-at-tool-calling (it names Nemotron 3).
- vLLM issue #42021: https://github.com/vllm-project/vllm/issues/42021
- Dynamo issue #6822: https://github.com/ai-dynamo/dynamo/issues/6822
- **Implication for Downshift:** they trace this mostly to parser and template mismatches. "If the tag lands
  in content, changing the prompt … won't help." It may be a **test-setup failure**, not a model limit.

**Geng et al., JSONSchemaBench, 2025.** https://arxiv.org/abs/2501.10868
- Llama-3.2-1B schema compliance: 0.65 → 0.96 with constrained decoding (Guidance).
- Llama-3.1-8B GSM8K: 80.1 → 83.7.

**Tam et al., *Let Me Speak Freely?*, 2024.** https://arxiv.org/abs/2408.02442
**dottxt rebuttal, *Say What You Mean*.** https://blog.dottxt.ai/say-what-you-mean.html
- Tam et al.: JSON mode hurt GSM8K (Llama-3-8B 74.7 → 48.9). Part of the cause was putting the answer key
  before the reasoning.
- dottxt: with matched prompts and a proper schema there is no loss (0.77 → 0.78).
- **Implication for Downshift:** put a reasoning field *before* the `sql` field. Constraining the format is
  then roughly neutral for accuracy.

### Does thinking off break tool calling for small hybrid models?

There is no paper that measures exactly "tool call written as text" against the thinking flag. The
indirect evidence is fairly consistent:
- **Turning thinking off hurts agentic tool use and instruction following in small hybrid models.**
  - Qwen3-30B-A3B: −10.5 BFCL and τ-Airline halved.
  - Nemotron 3 Nano 4B: −5 IFEval and −5 to −8 on τ².
  - Nemotron 3 Nano was trained on the off mode with only 10% of samples.
- The counter-evidence is narrower:
  - thinking increases hallucinated calls when no tool fits;
  - prompted CoT hurts constraint-following in non-reasoning models;
  - DeepSeek-V3.1 calls tools in non-thinking mode.
- Downshift's observation fits the main finding. Parser, template and `max_tokens` truncation are confounds
  that must be ruled out first.

---

## 5. Avoiding overfitting: candidate selection and sample sizes

### How the strongest optimizers select candidates

**GEPA.**
- Pareto set over instances: diverse candidates are kept, and none is chosen on an average over a tiny set.
- Validation of 111–300 items; minibatch 3 for proposing.

**MIPROv2.**
- Minibatch scoring, with the leaders periodically re-scored on the full validation set.
- 5 seeds. The authors still report "high variation".

**DSPy docs.** Verified from the docs source
(https://github.com/stanfordnlp/dspy/blob/main/docs/docs/learn/optimization/overview.md and
`optimizers.md`):
- "you can often get substantial value out of 30 examples, but aim for at least 300 examples".
- For prompt optimizers, "20% for training, 80% for validation … since prompt-based optimizers often
  overfit to small training sets".
- BootstrapFewShot for "around 10" examples.
- MIPROv2 needs "200 examples or more to prevent overfitting".

**Other methods.**
- ProTeGi: overfits after about 3 steps, even with a 50-example dev set.
- OPRO: train accuracy 5–20 pp above test.
- TextGrad: accept only if validation improves.
- AFlow and ADAS: 5 repeated runs per candidate on validation.
- p1: pick tasks where candidate prompts *disagree*. Averaging over heterogeneous tasks buries the signal.

**The smallest budgets with reported gains.**
- PromptWizard: 25 examples and about 69 calls.
- SPO: 3 samples × 10 iterations, single-turn tasks only.
- Trace: 15 train and 5 validation, with fragile results.
- None of them showed a small model catching up with a large one.

### Downshift's numbers, worked out

These are my calculations: SE = √(p(1−p)/n).

**Candidate selection on about 10 tasks.**
- At p = 0.5, SE ≈ **15.8 pp**.
- Picking the best of 3 equally good candidates on 10 tasks inflates the winner by about **13 pp** on
  average. The expected maximum of 3 normal draws is about 0.85 σ.
- The "best" round is therefore largely noise, and the held-out drop is the expected winner's curse.

**Held-out results on 40 tasks.**

| Harness | SE |
|---|---|
| Nano, 56% | ±7.8 pp (95% CI ±15 pp) |
| Ultra, 77.5% | ±6.6 pp |

- Ultra vs Super (1.5 pp apart): noise.
- Ultra vs Nano (21.5 pp): likely real, z ≈ 2.1.
- Swap to Nano (56) vs the best rewrite (50): not distinguishable.
- The 12.5% rewrite is clearly worse.
- With 40 tasks per arm, the minimum detectable unpaired difference at 80% power is about 30 pp. A paired
  test (McNemar on the same tasks) is tighter.

**Verdict.** 10–24 training examples is in the range where the literature reports gains *only* for
demo-based methods (BootstrapFewShot, PromptWizard). Every instruction-search method that reported stable
gains used 50–500 validation items, and GEPA and MIPRO used thousands of rollouts.

---

## 6. Changes to the optimizer loop that the literature supports

### Fix the measurement first

These are cheap and need no extra model calls.
- **Select candidates on more tasks, and use paired statistics.**
  - Score candidates on the union of train and val, or follow DSPy's 20/80 split.
  - Report McNemar or bootstrap confidence intervals against the plain swap on the *same* tasks.
  - Keep a rewrite only if the lower bound beats the swap.
- **Use a GEPA-style Pareto set instead of a single best.**
  - Keep every candidate that is best on at least one task.
  - Propose from those, and test the final pick on held-out.
  - This protects small-model fixes that matter on a few tasks.
- **Rule out serving-stack failures before blaming Nano.** Check the tool and reasoning parsers, the chat
  template, and truncation from `max_tokens`. NVIDIA attributes Nano 3's broken tool calls to these
  causes. Under CLAUDE.md these count as test-setup failures.

### Change what the rewriter is allowed to do

- **Pin the vendor's sampling settings.** Do not let the rewriter choose temperature freely.
  - Nano: tool calling T=0.6 / top_p 0.95; reasoning on T=1.0 / top_p 1.0; reasoning off greedy.
  - Super: T=1.0 / top_p 0.95 everywhere.
  - Keep `max_tokens` high: about 10k for Nano with reasoning on.
- **Default to thinking on for Nano's tool-calling and SQL steps.** Allow reasoning off only on pure-text
  steps, and only when an A/B test supports it. Qwen3-30B-A3B shows −10.5 BFCL with thinking off, and
  Nemotron 3 Nano trained the off mode on only 10% of samples. For Super, use `low_effort` before turning
  reasoning off.
- **Enforce format at the API level instead of in prose.**
  - A named `tool_choice` on tool steps.
  - `response_format: json_schema` for the final answer, e.g. `{"reasoning": …, "sql": …}`, with
    reasoning first.
  - Tools passed only through `tools`.
  - A deterministic SQL extractor, plus one retry when the output does not parse.
  - This is the strongest evidence-backed lever for format failures: PICARD +10.5 pp on the smallest
    model; JSONSchemaBench compliance 0.65 → 0.96.
- **Make demos the main lever.** Add 2–5 of Ultra's *successful* recorded traces as few-shot demos for
  Nano, chosen by similarity (DAIL-style) or bootstrapped. This is the BootstrapFewShot or DAIL approach.
  - MIPRO found demos beat instruction rewriting on 8B models.
  - Few-shot CoT beat OPRO on small models.
  - DAIL few-shot: LLaMA-13B 20 → 39.
- **Shorter, edit-based rewrites, not full regeneration.**
  - Limit instruction count and length, since IFScale shows small models dropping rules.
  - Apply ACE-style delta edits, one module at a time as GEPA does, rather than proposing a whole new
    harness each round.
  - Ban "CRITICAL/MUST" stacking.
- **Give richer per-example feedback to the rewriter.** For each failure, include:
  - the failure category (prose instead of SQL, text tool call, SQL error, wrong result);
  - the actual vs gold result;
  - the step where it failed.

  GEPA's gains came mostly where feedback was this specific.
- **Add test-time compute as a harness option.**
  - Execution-guided retry: +1 to +5 pp for strong models.
  - Majority vote over executed candidates: +2 to +6 pp.
  - These are the AFlow-style ways a small model passes a large one.
  - They still have to be compared on cost: k Nano calls vs one Super call.

### Where rewriting cannot close the gap

- When the large model is optimized too, the gap persists. Small models only pass *unoptimized* large
  baselines, and only when the starting gap is about 2–10 pp.
- Models below about 2–4B (Qwen3 0.6B and 1.7B) gain nothing from GEPA. Nano's 3B active parameters put it
  near that boundary; this is an analogy, not tested.
- Weak models do not benefit from self-debugging (StarCoder +0.2) or from better agent designs (Haiku
  9.7%).
- For 7B-class text-to-SQL, fine-tuning beats prompting by about 8–12 pp: 85 fine-tuned vs about 73
  prompted. NVIDIA's own position paper recommends LoRA on logged traces.
- On Spider, Super already matches Ultra within noise. The swap to Super is the honest recommendation, and
  no rewrite can show a significant gain over it on 40 tasks.

---

## Top 10 takeaways

1. **Downshift's result matches the literature.** No paper shows prompt-only optimization lifting a model
   with about 3B active parameters to a frontier model. Optimized small models only pass *unoptimized*
   large baselines when the gap is small, and very small models gain nothing (Qwen3-1.7B: 0.539 → 0.515
   with GEPA).
2. **The selection step is mostly noise.** Scoring on 10 tasks gives an SE of about 16 pp per candidate,
   and choosing the best of a few adds about 13 pp of winner's-curse inflation. Successful optimizers used
   111–500 validation items (GEPA, MIPRO) and DSPy recommends 80% of data for validation.
3. **Nano's 56% is below what a prompted 7B model reaches on Spider** (Qwen2.5-Coder-7B: 73.4). That points
   at format and serving-stack failures, not missing SQL knowledge.
4. **Fix format at the decoding/API level, not in prose.** Use a named `tool_choice`, `json_schema` with
   reasoning before the SQL, and retry on parse failure. PICARD gave +10.5 pp to its smallest model.
5. **Check the serving stack before blaming the model.** Nano 3's broken tool calls are linked to parser
   and template mismatches and to `max_tokens` truncation. NVIDIA's guidance covers this.
6. **Keep thinking on for Nano's tool and SQL steps.** Qwen3-30B-A3B shows −10.5 BFCL and τ-Airline
   halved with thinking off. Nemotron 3 Nano trained its off mode on only 10% of samples. The rewriter
   should not be allowed to turn it off by default.
7. **Pin NVIDIA's recommended sampling settings**: Nano tool calls T=0.6 / top_p 0.95, Super T=1.0 /
   top_p 0.95. The rewriter should stop choosing temperature.
8. **Demos taken from Ultra's successful traces are the best-supported lever for small models**
   (MIPRO, DAIL-SQL, Revisiting OPRO). Long expert instructions written by a large model transfer poorly
   downward (PromptAgent, IFScale, FormatSpread).
9. **If you keep the rewriter, make it GEPA/ACE-shaped.**
   - Pareto set per task.
   - Edits to one module at a time instead of a full new harness.
   - Specific diagnostics for each failure.
   - Accept a candidate only if it beats the swap on a paired test over enough tasks.
10. **Prompting has a limit.** On Spider, Super ≈ Ultra already, so recommend the swap. For Nano, the
    levers that can close the gap are more test-time compute (voting, execution retry) or LoRA fine-tuning
    on recorded traces (85 vs 73 for 7B text-to-SQL), not better prompts.
