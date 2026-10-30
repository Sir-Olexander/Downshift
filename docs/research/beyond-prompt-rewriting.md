# Beyond prompt rewriting: what else could close the Nano gap?

Literature review, 2026-10-29. No model calls were made. Sources were read on the web. Numbers that come
only from an abstract, a summary or a secondary source are marked **unverified**.

## Starting point

- **Plain model swaps on text-to-SQL** (Spider dev, 40 tasks, graded by executing the SQL):
  - Ultra→Super: 77.5% → 76%, no loss.
  - Ultra→Nano: 56%, about −21 pp.
  - Prompt rewrites recovered none of the Nano loss.
- **Why Nano fails.** Our own taxonomy
  ([text2sql-failure-taxonomy.md](text2sql-failure-taxonomy.md)) shows Nano's failures are mostly
  *format*: it often runs the right query through `execute_sql`, then reports the result in prose.
  - In 5 of 7 and 3 of 7 format failures (trials 1 and 2), the prose contains every gold value.
  - With thinking off, the failure type changes: tool calls are written as text, and table names are
    guessed.
- **Cost.** With thinking on, Nano costs about $0.0009–0.0019 per task, against $0.0028–0.0034 for Super.
  That is only about 2–3× cheaper, because Nano writes 3–6× more output tokens.
- **Sample size.** At n=40 and p≈0.56, one trial has a standard error of about **±8 pp**. On 16 held-out
  tasks it is about ±12 pp. Any gain under about 10 pp needs two or more trials before it means anything.

---

## Q1. NVIDIA: "Small Language Models are the Future of Agentic AI" and follow-ups

- **Belcak, Heinrich, Diao, Fu, Dong, Muralidharan, Lin, Molchanov (NVIDIA Research), 2025** (v1 June
  2025, latest v3 Sept 2026). https://arxiv.org/abs/2506.02153
  - **What it is.** A position paper ("a value statement") with **no experiments of its own**.
  - **The LLM-to-SLM conversion algorithm (Sec. 6):**
    - S1. Securely log every non-human-facing agent call: prompt, output, tool-call contents, and
      optionally latency.
    - S2. Curate the data: remove PII/PHI and paraphrase entities. Rule of thumb: **"10k–100k
      examples"**.
    - S3. Cluster prompts and actions into recurring tasks with an unsupervised method. No algorithm is
      named.
    - S4. Pick candidate SLMs per task, judged on instruction following, reasoning, context length,
      licence and footprint.
    - S5. Fine-tune each task's SLM with **LoRA/QLoRA**, or full fine-tuning; distilling from the LLM is
      optional.
    - S6. Retrain the SLMs and "the router model" periodically.
  - **Evidence.**
    - Case-study estimates of the share of queries an SLM could take over: MetaGPT ~60%, Open Operator
      ~40%, Cradle ~70%. These are guesses with no method behind them.
    - All other evidence is borrowed: Phi-2, Nemotron-H, xLAM-2-8B ("beats GPT-4o on tool calling"),
      Toolformer, and "10–30× cheaper" serving.
  - **Implication for Downshift.** Downshift already does S1 and part of S3/S4 (step analysis, per-step
    model). The step NVIDIA treats as essential, fine-tuning (S5), is exactly what Downshift lacks.
    NVIDIA does *not* claim that prompt changes alone convert an agent.
- **NVIDIA Technical Blog, "Build Efficient AI Agents Through Model Distillation With NVIDIA's Data
  Flywheel Blueprint", 2025-06-11.**
  https://developer.nvidia.com/blog/build-efficient-ai-agents-through-model-distillation-with-nvidias-data-flywheel-blueprint
  - Llama-3.3-70B tool calling was replaced by a LoRA-tuned Llama-3.2-1B reaching **"98% of the
    tool-calling accuracy"**.
  - LoRA settings: adapter_dim 32, 2 epochs, lr 1e-4. Blueprint defaults: `min_total_records: 50`,
    `eval_size: 20`. The actual dataset size is not reported.
  - A related HR/IT routing case used 685 examples to reach 94–96% (**unverified**, secondary summary).
  - **Implication for Downshift.** This is the closest product analogue: production logs, then LoRA,
    then evaluation. It hints that hundreds of examples, not 10k, can be enough for one narrow step.
- **Belcak, "How Small Language Models Are Key to Scalable Agentic AI", NVIDIA blog, 2025-08-29.**
  https://developer.nvidia.com/blog/how-small-language-models-are-key-to-scalable-agentic-ai/
  - The same loop, mapped to NeMo Curator, NeMo Customizer and the Data Flywheel. No new numbers.
- **NVIDIA, "Nemotron 3 Nano Technical Report", Dec 2025.**
  https://research.nvidia.com/labs/nemotron/files/NVIDIA-Nemotron-3-Nano-Technical-Report.pdf
  - **Training data.** SFT includes synthetic multi-turn tool-use trajectories (simulated
    user/agent/tools, judge-filtered) and distilled SWE-agent trajectories. RL includes a Workplace
    Assistant environment (26 tools, 690 tasks).
  - **Reported scores, reasoning on:** TauBench V2 Retail **56.9**, Airline 48.0, Telecom 42.2;
    BFCL v4 53.8; SWE-Bench (OpenHands) 38.8.
  - **No text-to-SQL benchmark** is reported.
  - **Implication for Downshift.** Nano was trained heavily on tool use. That makes a missing skill an
    unlikely explanation for "tool calls written as text"; a template or parser problem (Q6) is more
    likely. Our tau2 retail 70% (20 tasks, one trial) is well above NVIDIA's own 56.9 and is probably
    noise.
- **2026 follow-ups (mostly unverified).**
  - Nemotron-Agentic-Tool-Use-v1 dataset: reported as 335k samples, of which 19k are multi-turn
    trajectories.
  - Nemotron-RL-Agentic-Conversational-Tool-Use-Pivot-v1: 170k RLVR samples for NeMo Gym.
  - Nemotron 3 Super (arXiv 2604.12374) and Ultra (arXiv 2606.15007) reports exist; their contents were
    not checked.
  - The Token Factory catalog lists a "Nemotron-3.5-Lightning" at Nano prices ($0.06/$0.24 per 1M
    tokens) with 1M context. It is not yet evaluated here.
  - No 2026 NVIDIA paper with *empirical* LLM→SLM agent-conversion results was found.

## Q2. Agent distillation: fine-tuning small models on large-model traces

| Paper | Student / teacher | Traces | Method | Gain |
|---|---|---|---|---|
| FireAct, Chen et al. 2023, https://arxiv.org/abs/2310.05915 | Llama-2-7B / GPT-4 | **500** (HotpotQA ReAct) | full fine-tune | "77% HotpotQA performance increase" (relative) |
| AgentTuning, Zeng et al. 2023, https://arxiv.org/abs/2310.12823 | Llama-2-7/13/70B / GPT-4 | **1,866** (of 35k) + ShareGPT mixed at η=0.2 | full fine-tune | 7B held-in 0.19→1.96, held-out 0.38→0.67; agent-only data drops 7B held-out to **0.09** |
| Agent-FLAN, Chen et al. 2024, https://arxiv.org/abs/2403.12881 | Llama-2-7B | ~34k | full fine-tune | +3.5% over prior agent tuning. Format following is learned fast and is entangled with reasoning in agent corpora; negative samples cut hallucination |
| Distilling step-by-step, Hsieh et al. 2023, https://arxiv.org/abs/2305.02301 | T5-770M / PaLM-540B | task data plus rationales | full fine-tune | beats few-shot 540B with 80% of the data |
| Agent Distillation, Kang et al. 2025 (NeurIPS'25), https://arxiv.org/abs/2505.17612 | Qwen2.5-0.5–7B / Qwen2.5-32B | **~2,000** | **LoRA r=64** | 8-task average vs CoT distillation: 7B 33.5→39.9, 3B 27.7→33.6. **LoRA beat full fine-tuning** (29.1 vs 26.2 at 1.5B). Sampling several actions at test time adds 0–2 pts |
| SWE-Gym, Pan et al. 2024/ICML'25, https://arxiv.org/abs/2412.21139 | Qwen2.5-Coder-7/14/32B / GPT-4o + Claude | **491** | full fine-tune | SWE-bench Verified 32B 7.0→20.6 (**+13.6 pp**), 7B 1.8→10.6. Adding a verifier: Best@8 29.8, Best@16 32.0 |
| SWE-smith, Yang et al. 2025, https://arxiv.org/abs/2504.21798 | Qwen2.5-Coder-32B / Claude 3.7 | **5,016** | full fine-tune (unverified) | 40.2% pass@1 on Verified; "improves with more data" |
| ToolLLM, Qin et al. 2023, https://arxiv.org/abs/2307.16789 | LLaMA-7B / ChatGPT | ~126k (unverified) | full fine-tune | "comparable to ChatGPT" on ToolBench |
| SFT or RL for Tool-Calling Agents?, Laskar et al. 2026, https://arxiv.org/abs/2609.17848 | Qwen3-0.6–32B | n/a | LoRA vs full, SFT vs GRPO | **"SFT with LoRA is the strongest in-distribution method"** (15/18 settings); GRPO better cross-domain by under 1 pt |
| MAC-SQL / SQL-Llama, Wang et al. COLING'25, https://arxiv.org/abs/2312.11242 | Code Llama 7B / GPT-4 agent traces | ~10k (unverified) | full fine-tune | BIRD 43.9 vs GPT-4's 46.4 |
| OmniSQL, Li et al. 2025, https://arxiv.org/abs/2503.02240 | Qwen2.5-Coder-7B | **2.5M synthetic** | full fine-tune (7/14B), LoRA (32B) | Spider dev greedy 73.4→**81.2** (+7.8), BIRD dev 50.9→63.9; beats GPT-4o (70.9 on Spider dev) |
| PA-Tool, Lee et al. 2025 (ACL'26), https://arxiv.org/abs/2510.07248 | SLMs, **no training** | none | renames tool schemas to names the model finds familiar | up to **+17%** tool-use accuracy, **−80%** schema-misalignment errors |

### What these papers agree on

- **Trace count.** Narrow agent tasks gain **+9 to +20 pp** from **~500–2,000** filtered teacher
  trajectories. NVIDIA's blueprint starts at 50 records. Text-to-SQL state of the art used millions of
  synthetic samples.
- **LoRA is enough.** In three independent results it *beat* full fine-tuning: Agent Distillation,
  Laskar 2026, and the SWE-Gym verifier.
- **Mix in general data.** Agent-only fine-tuning damages generalisation (AgentTuning).
- **Format is the part fine-tuning fixes first** (Agent-FLAN). That matches Nano's failure profile. It
  also suggests a runtime format fix (Q6) captures much of the same gain without training.

**Implication for Downshift.** Fine-tuning is the best-evidenced lever in this literature, but it does
not fit Downshift today:

- **Data.** Downshift has 25–40 recorded runs per agent, one to two orders of magnitude fewer than any
  recipe above.
- **Budget.** Recording 1,000 Ultra traces at about $0.011 per text2sql task (the README's $0.45 for 40)
  costs about **$11**, most of the $15 limit.
- **Provider.** Token Factory cannot fine-tune Nemotron (Q3).

PA-Tool is a harness-only idea that could be tried now.

## Q3. Nebius Token Factory fine-tuning

- **Nebius docs, "Post-training: models".** https://docs.tokenfactory.nebius.com/post-training/models
  (fetched 2026-10-29)
  - **49 fine-tunable models. No Nemotron model is listed.**
  - **LoRA and full fine-tuning:**
    - Qwen3: 0.6B–32B, plus Base variants.
    - Qwen3-30B-A3B, including Instruct-2507 and Thinking-2507.
    - Qwen3-235B-A22B.
    - Qwen3-Coder-30B-A3B and 480B-A35B.
    - Qwen2.5: 0.5B–72B, plus Coder-32B.
    - Llama 3.1, 3.2 and 3.3: 1B–70B.
    - gpt-oss-20b and 120b.
  - **Full fine-tuning only:** DeepSeek-V3-0324, DeepSeek-V4-Flash, Gemma-4 (E2B, E4B, 31B), Qwen3.5-27B,
    Qwen3.6-27B.
  - **Context:** 8K by default, up to 131K.
  - **Deployment:** "Fine-tuned Meta models can currently be deployed only on Dedicated endpoints".
    LoRA adapters on MoE gpt-oss must be merged before a dedicated deployment.
  - The public catalog (https://tokenfactory.nebius.com/api/public/models_info) has no fine-tune field
    for any Nemotron 3 model.
- **API.** https://docs.tokenfactory.nebius.com/post-training/how-to-fine-tune.md and
  https://docs.tokenfactory.nebius.com/post-training/datasets.md
  - **OpenAI-style flow:** upload with `POST /v1/files` (`purpose=fine-tune`), create a job with
    `POST /v1/fine_tuning/jobs` (`lora: true|false`), then follow `/events` and `/checkpoints`.
  - **Defaults:** lora_r 8 (range 8–128), alpha 8, lr 1e-5, 3 epochs, batch 8, packing on.
  - **Dataset format:** JSONL `messages`, including `tool_calls`, `role: "tool"` turns and an optional
    `tools` field. Downshift's recorded runs map onto this almost one to one.
  - **Data Lab** (https://docs.tokenfactory.nebius.com/data-lab/chat-completions.md) can turn past
    chat-completion logs into a fine-tuning dataset, but only when Zero Data Retention is off.
- **Pricing and serving.**
  - Nebius blog, "Fine-tuning launches on Nebius AI Studio", 2025-03-05,
    https://nebius.com/blog/posts/fine-tuning-launches-on-nebius-ai-studio: you "pay only for the tokens
    processed during training", with "no hidden costs or additional charges for model deployment".
  - Nebius post-training page, https://nebius.com/services/token-factory/post-training: LoRA adapters
    are served serverless with per-token billing.
  - **The per-token training price was not found and is unverified.** For scale only, other providers
    charge $0.34–0.46 per 1M training tokens for LoRA on models of about 8B (Together AI, Ori).
  - **Rough cost:** 500 text2sql traces of about 8k tokens over 3 epochs is about 12M training tokens.
    At those comparison prices that would be about $4–6. This is an estimate; check the Nebius console
    before running anything.
- **Inference prices (catalog, per 1M input/output tokens):**

  | Model | Input | Output |
  |---|---|---|
  | Nemotron 3 Nano | $0.06 | $0.24 |
  | Nemotron 3 Super | $0.30 | $0.90 |
  | Nemotron 3 Ultra | $1.00 | $3.00 |
  | Qwen3-30B-A3B-Instruct-2507 (fine-tunable) | $0.10 | $0.30 |

- **Implication for Downshift.** Fine-tuning *on Token Factory* means leaving the Nemotron family; the
  closest Nano-class option is Qwen3-30B-A3B. That conflicts with the product's "cheaper Nemotron" story,
  so it should be treated as a later, optional target ("fine-tuned open model on Token Factory"). It is
  not a few-days task.

## Q4. Routing and cascades

| Paper | Escalation signal | Reported saving at matched quality | Needs training? | Runs from harness + `run.chat`? |
|---|---|---|---|---|
| FrugalGPT, Chen, Zaharia, Zou 2023, https://arxiv.org/abs/2305.05176 | learned DistilBERT answer scorer plus threshold | "up to 98% cost reduction" matching GPT-4 (single-turn QA/classification) | yes (scorer) | logic yes; scorer no |
| RouteLLM, Ong et al. 2024, https://arxiv.org/abs/2406.18665 | pre-call router (matrix factorisation, BERT, causal LLM) trained on Arena preferences | at 95% of GPT-4 quality: **>85%** on MT-Bench, **45%** on MMLU, **35%** on GSM8K | yes | no |
| Hybrid LLM, Ding et al. ICLR'24, https://arxiv.org/abs/2404.14618 | BERT router predicting the quality gap | "up to 40% fewer calls to the large model with no drop in response quality" | yes | no |
| AutoMix, Aggarwal, Madaan et al. NeurIPS'24, https://arxiv.org/abs/2310.12963 | small model self-verifies (8 samples), POMDP router on top | ">50%" cost reduction at comparable quality; authors call self-verification "often noisy and ill-calibrated" | no (few-shot) | **yes** |
| MoT cascade, Yue et al. ICLR'24, https://arxiv.org/abs/2310.03094 | agreement among k weak-model samples (CoT and PoT) | close to GPT-4 at **~40%** of its cost | no | **yes** |
| Gupta et al. 2024, "Language Model Cascades: Token-level uncertainty and beyond", https://arxiv.org/abs/2404.10136 | logprob-based deferral | sequence logprob "suffers from the length bias problem"; learned token-level rules do better | partly | only if the endpoint returns logprobs (unverified for Nemotron on Token Factory; Ollama: no) |
| R2V Agent, Hemadri et al. 2026, https://arxiv.org/abs/2605.16604 (preprint) | per-step process verifier plus calibrated router | TextWorld 64.6→98.2% at 41.7% escalation | yes (SLM, verifier, router) | structure only |
| AgentRouter, Paul and Nandy 2026 (ICML workshop), https://arxiv.org/abs/2609.22951 | 12M-param per-step classifier, 50k labelled steps | "72% cost reduction" at "97.3% of frontier quality"; warns that per-step errors compound (**unverified**, private data) | yes | no |
| Arch-Router, Tran et al. 2025, https://arxiv.org/abs/2506.16655 | 1.5B policy router | routing accuracy, not cost | yes | no |

**Implication for Downshift.**

- **Not usable.** Learned routers need far more labelled examples than a few dozen recorded runs. The
  headline savings (85–98%) come from chat and QA, not agents, and RouteLLM's own savings fall to 35–45%
  on reasoning tasks.
- **Usable today.** A cascade that escalates on a **deterministic check**:
  - for text2sql: the final reply has no SQL, the SQL does not run, or it returns no rows;
  - for any agent: a tool call fails to parse.
  
  This beats any LLM self-verification signal here and needs no training.
- **Cost, for text2sql (estimate).** Nano costs ≈$0.0014 and Super ≈$0.0031 per task. If 30% of tasks
  escalate, the cascade costs about $0.0014 + 0.3 × $0.0031 ≈ **$0.0023, only ~25% cheaper than plain
  Super**, which already loses nothing. A cascade pays off only if the escalation rate is low *and* Nano
  uses fewer tokens.

## Q5. Test-time compute

- **Self-Consistency.** Wang et al., ICLR 2023. https://arxiv.org/abs/2203.11171
  - Majority vote over sampled chain-of-thought answers: GSM8K **+17.9**, SVAMP +11.0, AQuA +12.2,
    StrategyQA +6.4 pts.
  - Cost grows linearly with the number of samples (5–40 in the paper).
  - **Implication for Downshift.** For SQL, vote on execution results, not on SQL strings.
- **Large Language Monkeys.** Brown et al., 2024. https://arxiv.org/abs/2407.21787
  - Coverage on SWE-bench Lite rises from 15.9% (1 sample) to 56% (250 samples).
  - Majority vote and reward models "plateau beyond several hundred samples".
  - Higher coverage turns into higher accuracy only with a good automatic verifier.
  - **Implication for Downshift.** SQL has a *partial* verifier (it runs, it returns rows). "Executes"
    is not "correct".
- **Scaling test-time compute optimally.** Snell et al., 2024. https://arxiv.org/abs/2408.03314
  - Compute-optimal allocation is ">4×" more efficient than best-of-N. A small model can beat a
    "14× larger" one, but only on problems where it "attains somewhat non-trivial success rates".
  - **Implication for Downshift.** Sampling helps Nano only on tasks it already sometimes gets right.
    Format failures must be fixed first.
- **Execution-Guided Decoding.** Wang et al., 2018. https://arxiv.org/abs/1807.03100
  - Drop candidates that error or return empty results. WikiSQL 83.8% execution accuracy; "universally
    improves" on ATIS and GeoQuery.
- **DIN-SQL.** Pourreza and Rafiei, NeurIPS 2023. https://arxiv.org/abs/2304.11015
  - Self-correction *without execution feedback*, Spider dev:

    | Model | No correction | "Gentle" prompt | "Generic" prompt |
    |---|---|---|---|
    | GPT-4 | 73.3 | 74.2 (+0.9) | **70.0 (−3.3)** |
    | CodeX | 67.3 | 68.7 (+1.4) | 69.9 (+2.6) |

  - **Implication for Downshift.** A generic "verify and fix" step is worth 1–3 pts at best and can
    hurt.
- **MAC-SQL Refiner.** Wang et al., COLING 2025. https://arxiv.org/abs/2312.11242
  - The Refiner executes the SQL and fixes it from the error message. BIRD dev with GPT-4: full system
    59.4, without the Refiner 54.8 (−4.6). There is no Spider ablation.
  - **Implication for Downshift.** In text2sql the `execute_sql` tool already returns errors to the agent
    loop, so most of this gain is already present. Nano's sql_error class is 0–1 of 16 tasks.
- **CHESS.** Talaei et al., 2024. https://arxiv.org/abs/2405.16755
  - BIRD test 71.1%. Schema selection adds about +2 pts and cuts tokens about 5×.
  - **Implication for Downshift.** Probably minor on Spider's small schemas (inference). Possibly more
    relevant here because text2sql uses an *80-table merged* database (unverified).
- **CHASE-SQL.** Pourreza et al., 2024. https://arxiv.org/abs/2410.01943
  - BIRD dev with Gemini 1.5 Pro: majority vote 68.8, trained selector 73.0, **oracle over 21
    candidates 82.8**. The query fixer adds +0.9 to +3.8.
  - **Implication for Downshift.** The selector is fine-tuned. An Ultra judge picking among Nano
    candidates would be the untrained version, and it is untested.
- **XiYan-SQL.** Gao et al., 2024. https://arxiv.org/abs/2411.08599
  - Multiple generators, a refiner and a fine-tuned selector: BIRD 75.6%, Spider test 89.7%.
- **Query and Conquer (execution-based MBR).** Borchmann and Wydmuch, 2025.
  https://arxiv.org/abs/2503.24364
  - Pick the candidate whose execution result agrees most with the other candidates. For 3–7B models,
    "often improving accuracy by 10 points or more with around 30 samples".
  - Qwen2.5-Coder-7B on BIRD: greedy 44.1 → about 51.5 at @10 → about 54.8 at @30. Cells were read from
    the table layout and are **unverified**.
- **OmniSQL voting ablation.** Li et al., 2025. https://arxiv.org/abs/2503.02240
  - Execution-based majority vote with K=8, **Spider dev**:

    | Model | Greedy | K=8 vote | Gain |
    |---|---|---|---|
    | Qwen2.5-Coder-7B | 73.4 | 77.1 | +3.7 |
    | Qwen2.5-Coder-14B | 78.1 | 80.6 | +2.5 |
    | Qwen2.5-Coder-32B | 77.7 | 77.9 | +0.2 |
    | GPT-4o | 70.9 | 70.7 | ≈0 |

  - On BIRD dev the 7B gains +10.4. Some cells came through a summariser and are partly **unverified**.
- **CSC-SQL.** arXiv 2505.13271, 2025: vote, then revise the top-2 groups; +0.7 to +5.5 over
  self-consistency (**unverified**, snippet only).

**Implication for Downshift.**

- **Gains on Spider are small.** Voting over executions gives **+0–4 pts on Spider** for 7–14B models,
  versus +7–10 on BIRD. That is far less than the 21-pt gap, which is mostly format failures that voting
  cannot fix.
- **Cost rules it out against Super.** Best-of-k over a *whole agent rollout* multiplies cost by k.
  Measured Nano-thinking-on costs 1/2 to 1/3 of Super, so **Nano best-of-3 already costs about as much as
  plain Super**, which has no gap to close.
- **Where it could still pay.** Only with a cheaper Nano configuration (fewer tokens), or by sampling
  just the final SQL-writing turn.

## Q6. Format repair and constrained generation

### What the endpoints support

- **Nebius Token Factory**, https://docs.tokenfactory.nebius.com/ai-models-inference/json.md and
  https://docs.tokenfactory.nebius.com/ai-models-inference/function-calling.md
  - `response_format`: `json_object` and `json_schema`, **per model**. Models carry a "JSON mode" tag
    on their card, and the Nemotron 3 cards do not show it, so it may not be enforced (**unverified**;
    needs a one-call probe).
  - `tool_choice`: `"auto"` and a **named function**, which "forces the model to call" it, are
    documented. `"required"` and `"none"` are **not documented** (unverified).
  - vLLM's `guided_json`, `guided_regex` and `guided_grammar` extras are not documented. Whether the
    backend is vLLM is unverified.
- **vLLM semantics, if that is the backend.** https://docs.vllm.ai/en/latest/features/tool_calling.html
  - A named tool is "guaranteed a validly-parsable function call - not a high-quality one".
  - `"required"` guarantees at least one tool call.
  - With `"auto"`, tool calls are parsed out of raw text and may be malformed.
- **Ollama Cloud (ollama.com/v1).** https://docs.ollama.com/api/openai-compatibility and
  https://github.com/ollama/ollama/issues/12362
  - `response_format`, `tools` and `reasoning_effort` are accepted. **`tool_choice`, `n` and `logprobs`
    are not supported.**
  - A maintainer (2025-12-10): "we don't currently support structured outputs on the cloud just yet".
    It was reproduced again on 2026-10-22: a schema request returned prose with HTTP 200.
  - **Implication for Downshift.** On Ollama Cloud, constraints are silently ignored. Only parse-and-retry
    in the SDK works there.
- **Server-side parsing bugs specific to Nemotron 3.**
  - ai-dynamo frontend-crates PR #381 (merged 2026-10-09),
    https://github.com/ai-dynamo/frontend-crates/pull/381: Nemotron v3 can emit
    `<tool_call><function=…>` *before* `</think>`, and the reasoning parser swallowed it. This happened
    in **27 of 1,000** stress responses.
  - Open vLLM issues #39103 and #39581: empty content, or `reasoning_effort: none` being ignored, with
    the nemotron_v3 reasoning parser.
  - **Implication for Downshift.** Some of Nano's "tool call written as text" failures may come from the
    server's parser, not the model. In both cases an SDK-side parser that recovers `<tool_call>` or
    `<function=` blocks from the content is a cheap fix.

### Evidence on whether constraints help

- **JSONSchemaBench.** Geng et al., 2025. https://arxiv.org/abs/2501.10868
  - Schema compliance varies widely by engine: Guidance 0.69–1.00, XGrammar 0.41–0.93, Outlines
    0.06–0.98, OpenAI 0.92–1.00.
  - Task accuracy on Llama-3.1-8B, unconstrained vs constrained: GSM8K 80.1 → 83.7–83.8, Last Letters
    50.7 → 51.2–54.0.
  - **Implication for Downshift.** Constraints make outputs valid and leave quality roughly unchanged:
    0 to +4 pts.
- **"Let Me Speak Freely?"** Tam et al., 2024. https://arxiv.org/abs/2408.02442
  - Strict formats hurt reasoning. LLaMA-3-8B on GSM8K: free text 75.1, JSON 64.7, JSON with a schema
    **48.9**.
  - The cause: the model put the answer field before the reasoning.
  - A simple *reformat-after* step fixed most parse errors.
  - **Implication for Downshift.** Never constrain a reasoning or tool-loop step. Constrain or repair
    only the final container.
- **"Say What You Mean".** Will Kurt, dottxt blog, about 2024. https://blog.dottxt.ai/say-what-you-mean.html
  - A rebuttal: with fixed prompts, structured output slightly beat free text.
  - Changing only the *scoring parser* moved Last Letter from 0.35 to 0.61.
  - **Implication for Downshift.** Extraction strictness alone can move scores by tens of points. Keep
    text2sql's own extraction rule as the contract and report it.
- **PICARD.** Scholak et al., 2021. https://arxiv.org/abs/2109.05093
  - Grammar-constrained SQL decoding on Spider dev: T5-Base 57.9 → 68.4, T5-3B 71.4 → 76.3. Invalid SQL
    from T5-3B fell from 12% to 2%.
  - **Implication for Downshift.** PICARD needs token-level control, which a hosted API does not give.
    The API-level equivalent is to parse, run EXPLAIN, and retry.
- **TTD-SQL** (EMNLP 2025): +17.7% executable SQL for CodeLlama on BIRD (**unverified**, abstract only).
- **Natural Language Tools.** Johnson, Pain, West, 2025. https://arxiv.org/abs/2510.14453
  - The model selects tools in plain text, and a parser maps that to calls.
  - Reported **+18.4 pts** tool-calling accuracy and 70% less variance, with the largest gains on
    open-weight models (**unverified**, abstract only).
  - **Implication for Downshift.** Accepting text-form tool calls and parsing them in the SDK is a tested
    pattern.
- **Our own data.** [text2sql-failure-taxonomy.md](text2sql-failure-taxonomy.md)
  - Nano's thinking-on failures are mostly "right answer, wrong container".
  - The taxonomy estimates that fixing only the final-message format would move Nano from **7/16 to
    about 12–14/16**, which is Ultra's 11–12/16 range. This is an estimate, not a measurement.

## Q7. Synthesis: what Downshift should try, ranked

The score combines expected gain on the Nano text-to-SQL gap with how feasible it is in a few days. Gains
are estimates for the 40-task Spider set, where ±8 pp is noise for a single trial.

| # | Intervention (harness.yaml + `run.chat`) | Expected gain on Nano | Evidence | Feasibility | Notes / risk |
|---|---|---|---|---|---|
| 1 | **Final-answer repair turn.** If the agent's final reply breaks its own output contract (here: no ```sql block or SELECT/WITH), send one short follow-up: "Reply with only the final SQL you ran, in a ```sql block". At most one retry. | **+10 to +20 pp** (format failures are 8–13 of 40; 3–5 of 7 already have the right rows) | own taxonomy; Agent-FLAN (format separable); Tam et al. (reformat-after fixes parse errors); NLT | **hours**; generic (contract = a regex or check declared in harness.yaml) | Costs one small call on ~20–30% of tasks. It must check the *agent's own* contract, not the grader. Report it as a runtime behaviour. Do not fall back silently to "last executed SQL": that changes the agent's answer rather than its format, and is too close to grading the trace |
| 2 | **Stop forcing `reasoning: off` on Nano tool loops, and set `max_tokens`.** | prevents the −10 to −40 pp collapse seen in rewrites (62.5% swap vs 12.5–25% with thinking off on 8-task samples) | own optimizer logs (`opt_10b7f3486f2d`, `opt_4dba6d045f4f`) | **hours** (guidance.py and rewrite rules) | Not a gain over the swap. It removes a self-inflicted loss. Leaves Nano's cost at about 2–3× cheaper than Super |
| 3 | **Text-form tool-call recovery.** If the content contains `<tool_call>`, `<function=…>` or JSON matching a tool schema, convert it to a real tool call. | small to medium (mainly the thinking-off failure mode) | Dynamo PR #381 (27/1000); NLT (+18.4, unverified); vLLM "auto" parsing caveat | **about a day** | Model-family-specific parsers. Low risk |
| 4 | **Deterministic-check cascade to Super.** Escalate the *task* when check #1 still fails after one repair, or when the SQL errors. | approaches Super accuracy (76%) | MoT (~40% of large-model cost), AutoMix (>50%); deterministic check beats self-verification | **1–2 days** | Saves only ~25% vs plain Super at a 30% escalation rate. Worth it only if the escalation rate falls below ~15% after #1 |
| 5 | **Forced named `tool_choice`** for steps that must end in a tool call (`run.chat(..., tool_choice=…)` from harness.yaml) | small for text2sql (the contract is a text reply); larger for tool-call agents | vLLM guarantee; Nebius docs | **hours** on Token Factory; **not supported on Ollama Cloud** | Guarantees a parsable call, not a good one. Never force a schema on a reasoning step (Tam et al.) |
| 6 | **Tool-schema renaming per model** (PA-Tool) as a rewrite option | small to medium on tool-selection errors (guessed table names are a related failure) | PA-Tool +17%, −80% schema errors | 1–2 days | Changes the tool names the agent's code dispatches on. Needs an SDK alias map |
| 7 | **Best-of-k with an execution vote** on the final SQL | **+0–4 pp on Spider** after format is fixed | OmniSQL K=8 (+3.7 at 7B, +0.2 at 32B); Query and Conquer (BIRD +7–10); Snell (needs non-trivial base success) | 2–3 days; full rollouts are k× cost; Ollama has no `n` | **Dominated by plain Super on cost**: Nano best-of-3 ≈ Super price |
| 8 | Error-feedback SQL repair (MAC-SQL style) | ~0–1 task of 40 | MAC-SQL −4.6 without Refiner on BIRD GPT-4; Nano sql_error is 0–1/16 | already present (the tool returns errors) | Little headroom |
| 9 | LoRA fine-tune on Ultra traces | **largest reported** (+8 to +20 pp) | FireAct, SWE-Gym, Agent Distillation, OmniSQL | **not feasible now**: no Nemotron fine-tuning on Token Factory; needs ~500–2,000 traces (≈$5–22 of Ultra calls against a $15 budget) | Possible later target on Qwen3-30B-A3B (LoRA, $0.10/$0.30) |
| 10 | Learned routers (RouteLLM, FrugalGPT, Hybrid LLM, AgentRouter) | unknown | need thousands of labels | not feasible | Too few runs to train |

### What the literature and our data say will likely NOT work

- **More prompt rewriting** for format failures. Our two optimizations show no gain. Agent-FLAN-style
  results show format is fixed by training or by enforcement, not by telling the model.
- **A generic "verify / self-correct" LLM step without an execution signal.** DIN-SQL's generic prompt
  went **−3.3** on GPT-4. AutoMix's authors call self-verification "noisy and ill-calibrated". The
  shipped harnesses already add a `verify` step.
- **Hard JSON-schema constraints on reasoning or tool-loop steps.** They cost up to −26 pts on GSM8K
  (Tam et al.), are possibly not enforced for Nemotron on Token Factory, and are ignored on Ollama Cloud.
- **Best-of-n and self-consistency as the main fix.** They are small on Spider (+0–4), cannot fix prose
  answers, and cost as much as Super.
- **Logprob-based escalation.** It has a length bias (Gupta et al.), Ollama does not return logprobs, and
  Token Factory support is unverified.
- **Learned routers or fine-tuning within a few days and $15.** The data and provider support are not
  there.

### How to test this honestly (per CLAUDE.md)

- **Runs.** Fresh runs, two trials, on the held-out tasks. Compare:
  - Ultra baseline;
  - plain Super swap;
  - plain Nano swap;
  - Nano with #1 + #3;
  - optionally the Nano→Super cascade (#4).
- **Report, per arm:**
  - the repair-turn trigger rate;
  - the escalation rate;
  - cost per task, *including* repair and escalation calls;
  - the number of tasks fixed by the repair that were already right in substance (rows in the prose).
- **Budget.** Nano runs cost about $0.001–0.002 per task, so 40 tasks × 2 trials × 2 Nano arms is about
  $0.30. Ultra is about $0.45 per 40-task trial.
- **Expected outcome to state up front.** Even if #1 lifts Nano to Super's level, Super already matches
  Ultra. The honest headline would be "Nano reaches Super's quality at about half of Super's cost". It
  would not be "Nano is free".

## Top 10 takeaways

1. The Nano gap on text2sql is mostly a *container* problem (prose instead of a ```sql block). The
   cheapest fix with evidence behind it is an SDK-level repair turn checked against the agent's own
   output contract. Expected +10–20 pp, a few hours of work.
2. The optimizer is making Nano worse by forcing `reasoning: off` on tool loops (62.5% swap vs 12.5–25%
   in rewrites). Fix the guidance before anything else.
3. Some "tool call written as text" failures are documented Nemotron-v3 server parser bugs (Dynamo PR
   #381: 27/1000). Recover text-form tool calls in the SDK.
4. The NVIDIA SLM paper is a position paper without experiments. Its own recipe depends on fine-tuning
   (LoRA, "10k–100k examples"). Prompt-only conversion is not what it claims.
5. Agent-trace fine-tuning gives +9–20 pp from about 500–2,000 traces, and LoRA is enough (it often beats
   full fine-tuning). But it is out of reach now.
6. **Token Factory fine-tunes 49 models (Qwen3, Qwen2.5, Llama, gpt-oss, Gemma, DeepSeek) but no
   Nemotron.** The training price was not found (unverified). Fine-tuning would mean leaving Nemotron
   (closest option: Qwen3-30B-A3B with LoRA).
7. Best-of-n with execution voting adds only 0–4 pp on Spider for 7–14B models (+7–10 on BIRD). With
   Nano at 1/2–1/3 of Super's cost, best-of-3 Nano is as expensive as plain Super.
8. Cascades help only with a cheap, reliable escalation signal. For SQL that is deterministic (no SQL,
   error, empty result), not self-verification or logprobs. At a 30% escalation rate a Nano→Super cascade
   saves only about 25% vs plain Super.
9. Do not constrain reasoning steps with JSON schemas (−26 pts on GSM8K in Tam et al.). Forced *named*
   `tool_choice` is documented on Token Factory. Nothing is enforced on Ollama Cloud (no `tool_choice`,
   no `n`, structured outputs ignored).
10. Noise dominates the current evidence: ±8 pp on 40 tasks and ±12 pp on 16. The tau2 result "Nano 70%
    > Ultra 45%" contradicts NVIDIA's own Nano score (56.9 on tau2 retail). Every claimed gain needs two
    or more fresh trials and a plain-swap control.
