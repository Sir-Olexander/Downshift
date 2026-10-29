# Outside agents and test beds for Downshift (research, 2026-10-29)

Scope: which open-source agents and benchmarks with correct answers Downshift should run on next,
what is known about small-vs-large model gaps on them, who has already tried "swap to a cheaper model
and rework the harness", and three concrete next test beds.

Method and limits:
- Web sources only (WebSearch, WebFetch), plus reading, not running, the local copies in `demo_agents_2/`.
- No model API was called and no downloaded code was run.
- Facts come from three research passes. These I re-checked myself:
  - the tau2-bench grading rules and task counts, in local source v2.0.0 (`demo_agents_2/tau2-bench-main`);
  - the Nemotron 3 Nano model card;
  - BFCL's remote-endpoint setup;
  - the arXiv 2604.27082 findings.
- **unverified** marks anything not confirmed against a primary source.
- Vendor model-card numbers are self-reported, and harnesses differ between cards.

**Budget context.** CLAUDE.md caps the Token Factory key at $15. `demo_agents_2/_eval/RESULTS.md` puts
the running total at about $10.60, so about **$4.40 is left**. Section 4 is costed against that.

---

## 1. Candidate test beds

Ease scores run from 1 (hard) to 5 (easy):
- **Adapter**: writing a `downshift_agent.py` that sends model calls through `run.chat`.
- **Proxy**: pointing the agent's `base_url` / `OPENAI_API_BASE` at an OpenAI-compatible recording
  proxy hosted by Downshift, with no adapter code.

Costs are per task for a 30B-class model at Token Factory prices. "est." means my estimate from token
counts, not a published figure.

| Test bed | What is graded, how | Tasks | Cost/task (30B class) | Model calls / proxy path | Licence · status 2026 | Adapter | Proxy |
|---|---|---|---|---|---|---|---|
| **tau2-bench** (Sierra) | Final DB state (`DB`), device/env assertions (`ENV_ASSERTION`) and required actions are deterministic. `COMMUNICATE` uses an LLM judge (gpt-5.5) only when a task lists `communicate_info`. `NL_ASSERTION` uses gpt-5.4-mini (local `config.py`, `evaluator_communicate.py`). **Judge-free test tasks (local count): telecom 40/40, airline 19/20, retail 29/40.** An LLM user simulator is always needed. [eval doc](https://github.com/sierra-research/tau2-bench/blob/main/docs/evaluation.md) | Test splits: retail 40, airline 20, telecom 40 (plus a 2,285-task telecom "full"). New banking_knowledge domain: 97 tasks. [splits](https://raw.githubusercontent.com/sierra-research/tau2-bench/main/data/tau2/domains/telecom/split_tasks.json), [CHANGELOG](https://github.com/sierra-research/tau2-bench/blob/main/CHANGELOG.md) | **Measured here (retail):** Nano $0.008, Super $0.029, Ultra $0.137–0.199 agent cost per task, plus the user simulator (RESULTS.md) | LiteLLM `completion(**llm_args)` with `--agent-llm openai/<id>`. The local run used `OPENAI_API_BASE`. Passing `api_base` in `--agent-llm-args` should send only the agent to a proxy (inferred from code, **unverified**) | MIT · very active (2.0.0, Oct 2026) | 3 | **4** |
| tau-bench (original) | DB state plus outputs | retail ~115, airline 50 (**unverified**) | ≈ tau2 | LiteLLM | MIT · **deprecated** in favour of tau2/τ³ [repo](https://github.com/sierra-research/tau-bench) | 2 | 3 |
| **BFCL v3/v4** (Berkeley) | Single-turn: AST match. **Multi-turn: backend state checker plus call-path response checker**, deterministic, no user simulator. Web search: exact match, needs SerpAPI. Memory: exact match. [v3 blog](https://gorilla.cs.berkeley.edu/blogs/13_bfcl_v3_multi_turn.html), [README](https://github.com/ShishirPatil/gorilla/tree/main/berkeley-function-call-leaderboard) | Multi-turn base / miss_func / miss_param / long_context: 200 each. web_search 100–200; memory ~155 ([3rd-party count](https://huggingface.co/datasets/tuandunghcmut/BFCL_v4_information/blob/main/BFCL_v4_dataset_guide.md)) | Single-turn: hundreds to a few thousand tokens. Multi-turn: est. 20–40k input tokens per entry, so ~$0.002 Nano, ~$0.035 Ultra (**unverified**) | `bfcl-eval` handlers. `REMOTE_OPENAI_BASE_URL` plus `--skip-server-setup`. A new model needs a handler or `model_config.py` entry [README](https://github.com/ShishirPatil/gorilla/tree/main/berkeley-function-call-leaderboard) | Apache-2.0 · last CHANGELOG entry 2025-10 [CHANGELOG](https://github.com/ShishirPatil/gorilla/blob/main/berkeley-function-call-leaderboard/CHANGELOG.md) | 3 | 3 (concurrent entries need a task header) |
| AppWorld | Unit tests on the final DB state (TGC/SGC) | 750 (test_normal 168, test_challenge 417) [paper](https://arxiv.org/pdf/2407.18901) | GPT-4o ReAct ~$0.70 per task (long code-agent runs) [paper](https://arxiv.org/html/2407.18901v1) | Configurable `base_url` [repo](https://github.com/StonyBrookNLP/appworld) | Apache-2.0; test data must stay encrypted | 3 | 3 |
| ToolSandbox (Apple) | Milestone/minefield DAG, snapshot similarity / exact match / ROUGE-L; GPT-4o user simulator | 1,032 scenarios [paper](https://arxiv.org/html/2408.04682) | n/a | `OPENAI_BASE_URL` [repo](https://github.com/apple/ToolSandbox) | licence **unverified** · effectively unmaintained since 2024 | 3 | 3 |
| NESTFUL (IBM) | Executed nested call sequences; F1 and full accuracy | 1,861 [paper](https://arxiv.org/html/2409.03797) | small | Local HF/vLLM harness [repo](https://github.com/IBM/NESTFUL) | Apache-2.0 · reported archived (**unverified**) | 2 | 1 |
| ToolBench / StableToolBench | **Pass rate graded by a GPT-4 judge**; APIs simulated by an LLM or cache | I1–I3 groups | n/a | `OPENAI_API_BASE` [repo](https://github.com/THUNLP-MT/StableToolBench) | Apache-2.0 · last update 2024-09 | 1 | 2 |
| API-Bank | API-call correctness | 314 dialogues, 753 calls [arXiv](https://arxiv.org/abs/2304.08244) | small | Custom (**unverified**) | 2023, unmaintained | 2 | 1 |
| MINT | Answers with feedback simulated by GPT-4 | **unverified** | n/a | Custom [repo](https://github.com/xingyaoww/mint-bench) | Apache-2.0 | 2 | 1 |
| AgentBench (OS / DB / KG) | Success rate. OS and DB deterministic (**unverified**). KG needs an online Freebase service | OS test 144, DB test 300 [PreAct](https://arxiv.org/pdf/2402.11534) | small | YAML configs plus Docker; function-calling version 2025-10 [repo](https://github.com/THUDM/AgentBench) | Apache-2.0 | 2 | 3 |
| GAIA | Quasi-exact match on short answers | 165 validation tasks with answers [HF](https://huggingface.co/datasets/gaia-benchmark/GAIA) | ~50k tokens per task ([aggregator](https://benchmarkingagents.com/cost-per-eval/), **unverified**) | No reference harness | Gated, no resharing; >350/466 questions need browsing [paper](https://arxiv.org/pdf/2311.12983) | 2 | 2 |
| HotpotQA / 2Wiki / MuSiQue + ReAct | EM/F1 against gold strings (deterministic but sensitive to formatting) | Dev: 7,405 / 12,576 / 2,417 [FlashRAG](https://github.com/RUC-NLPIR/FlashRAG) | est. 3–10k tokens | Our own agent (e.g. `react-from-scratch`, which is Vertex-Gemini text ReAct: `src/llm/gemini.py`), or FlashRAG | MIT | 4 | 4 |
| GSM8K / MATH + calculator | Exact numeric match | 1,319 / 5,000 | <2k tokens | Our own | MIT | 5 | 5 |
| SWE-bench Lite / Verified via **mini-SWE-agent** | Unit tests in Docker | 300 / 500 | est. $0.3–1 per instance on Ultra, $0.02–0.06 on Nano (**unverified**) | LiteLLM; config-only `api_base` [docs](https://mini-swe-agent.com/latest/models/local_models/) | MIT · active [repo](https://github.com/SWE-agent/mini-swe-agent) | 4 | **5** |
| WebShop | Attribute-match reward; success = 1.0 | 500 test [repo](https://github.com/princeton-nlp/WebShop) | small | Gym environment; our loop | MIT · old stack (Java, py3.8) | 3 | n/a |
| ALFWorld | Binary success | 134 unseen [CoPS](https://arxiv.org/pdf/2410.16670) | est. 10–30k tokens | Gym environment; our loop | MIT | 4 | n/a |
| BabyAI-text (BALROG) | Binary success per episode | 5 tasks × 25 seeds = 125 [paper](https://arxiv.org/html/2411.13543v1) | small | `client.base_url` [repo](https://github.com/balrog-ai/BALROG) | MIT | 4 | 5 |
| Spider 2.0 (Lite/Snow) | Execution-result match | Lite 547 (only 135 SQLite) [repo](https://github.com/xlang-ai/Spider2) | high | Spider-Agent | MIT · Snowflake evaluation account suspended since 2026-08 [repo](https://github.com/xlang-ai/Spider2) | 2 | 2 |
| **BIRD mini-dev** | Execution accuracy (EX), deterministic | 500 (SQLite / MySQL / Postgres; V2 780) [repo](https://github.com/bird-bench/mini_dev) | est. 1.5–2× Spider, so Ultra ~$0.02–0.03 per question | Reuse the **existing text2sql adapter** | CC BY-SA 4.0 · annotations corrected 2026-10-28 | **5** | 4 |
| BIRD-Interact | Test cases, but the user simulator is an LLM | 600 / Lite 300 [arXiv](https://arxiv.org/abs/2510.05318v2) | high | **unverified** | **unverified** | 3 | 3 |
| DS-1000 | Execution tests | 1,000 [repo](https://github.com/xlang-ai/DS-1000) | small, single-shot | Scripts | CC BY-SA 4.0 · low activity | 4 | 3 |
| DA-Code | Scripted checks per task type (**unverified**) | 500 [paper](https://arxiv.org/html/2410.07331v2) | medium | DA-Agent, Docker | **unverified** | 3 | 3 |
| LiveCodeBench | Hidden tests, pass@1 | v6: 1,055 [repo](https://github.com/LiveCodeBench/LiveCodeBench) | small, single-shot, **not an agent** | `lcb_runner` | MIT | 4 | 3 |
| TheAgentCompany | Checkpoints, partly **LLM-graded** | 175 [repo](https://github.com/TheAgentCompany/TheAgentCompany) | high | OpenHands config | MIT · heavy (≥30 GB of services) | 2 | 3 |
| OSWorld-Verified | Execution scripts per task | 369 [leaderboard](https://yutori.com/leaderboards/osworld-verified) | high | `OPENAI_BASE_URL` [repo](https://github.com/xlang-ai/OSWorld) | Apache-2.0 · needs a VM and a vision model; Nemotron 3 is text-only | 1 | 2 |

### tau2-bench details (from the local source, v2.0.0)

- **Default models.**
  - `DEFAULT_LLM_AGENT` and `DEFAULT_LLM_USER` are both `gpt-4.1`, at temperature 0.
  - The COMMUNICATE judge is `gpt-5.5`; the NL-assertion judge is `gpt-5.4-mini` (`src/tau2/config.py`).
  - Token Factory serves none of these, so every role must be overridden.
- **When the judges run.**
  - The communicate judge is called only when a task's `communicate_info` is non-empty. With no
    criteria, the code says "absent criteria are neutral and make no LLM calls" (`evaluator_communicate.py`).
  - `--communicate-scorer substring` replaces the judge with substring matching.
  - The NL judge runs only when `NL_ASSERTION` is in `reward_basis` and the task has assertions.
  - That gives the 11 judge-graded retail test tasks found in the earlier run (RESULTS.md).
- **Telecom is the cleanest domain.**
  - 28 test tasks are `ENV_ASSERTION`-only and 12 are `ACTION`+`ENV_ASSERTION`, with no judge.
  - The user simulator also operates a simulated phone (dual control). Its competence therefore
    matters more than in retail.
- **The simulator is the main source of noise.** It ended a call early in retail task 9 and looped to
  100 steps in task 65 (RESULTS.md).

### Adapter or recording proxy

The local tau2 run reached Token Factory purely through `OPENAI_API_BASE`, so a proxy would attach to
it with no code. The same holds for mini-SWE-agent (`api_base`), BFCL (`REMOTE_OPENAI_BASE_URL`),
BALROG (`client.base_url`), OSWorld and ToolSandbox (`OPENAI_BASE_URL`).

What a proxy can do:
- record every request and response;
- rewrite the system prompt and tool descriptions;
- inject few-shot turns;
- set temperature and max_tokens;
- toggle thinking (`chat_template_kwargs.enable_thinking`);
- swap the model.

What a proxy cannot do without help:
- **Know which task a call belongs to.** Use a per-task path, e.g. `api_base=http://proxy/v1/t/<task_id>`
  with one task per process, or a header, which needs a small code change.
- **Tell the agent apart from the user simulator or judge.** Give them separate base URLs. tau2 can
  do this with per-role `--agent-llm-args` / `--user-llm-args`.
- **Replay recorded tool results.** Tools run inside the agent, so every replay is live and pays for
  the user simulator again. That is acceptable for these stateful environments, which already need
  `reuse_tool_results = False`.
- **Get the grade.** The benchmark's own result file must be ingested after the run.

Recommendation: build the proxy as a second integration path for tau2 and mini-SWE-agent, where it
removes most adapter work. Keep the in-process adapter for agents with their own Python loop (text2sql,
BFCL handlers).

---

## 2. What is known about small-vs-large gaps

Published numbers. Gap = large − small, in points.

| Pair | Benchmark | Small → Large | Gap | Source |
|---|---|---|---|---|
| **Nemotron 3 Nano → Super** | τ²-bench V2 telecom | 42.2 → 64.36 | **+22** | [Nano card](https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16) (re-checked), [Super card](https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-BF16) |
| | τ²-bench V2 airline / retail / average | 48.0→56.25 / 56.9→62.83 / 49.0→61.15 | +8 / +6 / +12 | same |
| | SWE-bench (OpenHands) | 38.8 → 60.47 | **+22** | same |
| | Terminal-Bench hard subset | 8.5 → 25.78 | **+17** | same |
| | IFBench / AIME25 (no tools) | 71.5→72.56 / 89.1→90.2 | ≈0 | same |
| | BFCL v4 | Nano 53.8; Super not reported | n/a | same |
| Nemotron 3 Ultra | τ-bench **V3** average 70.9; SWE-bench Verified 70.7 | not comparable to the V2 numbers above | n/a | [Ultra card](https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Ultra-550B-A55B-BF16) (not re-checked) |
| **This team's own runs** (Token Factory, thinking on) | Spider-40 via text2sql | Nano 56.2, Super 76.2, Ultra 77.5 | **Nano −21; Super ≈ Ultra** | `demo_agents_2/_eval/RESULTS.md` |
| | τ²-bench retail, 20 tasks, 1 trial | Nano 70, Super 70, Ultra 45 | ≈0 (Ultra worse; p=0.125) | same |
| Qwen3-30B-A3B → 235B-A22B (Instruct-2507) | τ² retail / airline / telecom | 57.0→74.6 / 38→50 / 12.3→32.5 | **+18 / +12 / +20** | [30B](https://huggingface.co/Qwen/Qwen3-30B-A3B-Instruct-2507), [235B](https://huggingface.co/Qwen/Qwen3-235B-A22B-Instruct-2507) |
| Qwen3 (original, non-thinking) | τ² retail / airline | 31.6→64.9 / 18→36 | **+33 / +18** | [30B card](https://huggingface.co/Qwen/Qwen3-30B-A3B-Instruct-2507) |
| Qwen3-2507 30B → 235B | BFCL v4 multi-turn (FC / prompt mode) | 30.0→45.4 / 23.5→44.6 | **+15 / +21** | [BFCL CSV](https://gorilla.cs.berkeley.edu/data_overall.csv) |
| | BFCL v4 web search | 22.5→54.0 | **+31** | same |
| | BFCL non-live AST / live | 88.9→90.3 / 78.4→78.7 | **≈0** | same |
| | BFCL v3 overall (Thinking) | 72.4 vs 71.9 | **≈0** | Qwen cards |
| gpt-oss-20b → 120b | SWE-bench Verified / τ-bench retail | 60.7→62.4 / 54.8→67.8 | ≈2 / +13 | [model card](https://arxiv.org/pdf/2508.10925) |
| Llama 3.1 8B → 70B | BALROG BabyAI | 30.0 → 73.2 | **+43** | [BALROG](https://arxiv.org/html/2411.13543v1) |
| | Nexus / BFCL / API-Bank | 38.5→56.7 / 76.1→84.8 / 82.6→90.0 | +18 / +9 / +7 | [card](https://huggingface.co/meta-llama/Llama-3.1-8B-Instruct) |
| Llama 3 8B → 70B | BIRD mini-dev EX (SQLite) | 24.4 → 40.8 | **+16** | [mini_dev](https://github.com/bird-bench/mini_dev) |
| Llama 3.1 8B / 70B / 405B | NESTFUL full accuracy | 0.16 / 0.07 / 0.07 | **inverted** | [paper](https://arxiv.org/html/2409.03797) |
| Qwen2.5 7B → 72B | GSM8K / HumanEval | 91.6→95.8 / 84.8→86.6 | ≈0–4 (saturated) | [Qwen2.5 blog](https://qwenlm.github.io/blog/qwen2.5-llm/) |

**Gaps of 15+ points, where a rewrite has room to recover:**
- τ² telecom (published Nano→Super +22);
- BFCL v4 multi-turn and web search;
- SWE-bench and Terminal-Bench (Nano→Super);
- BIRD mini-dev;
- BALROG BabyAI;
- this team's Spider run (Nano −21, mostly prose instead of SQL, which is a harness-fixable failure).

**Swap already free, where Downshift should say "just swap":**
- Spider, Super vs Ultra (measured here);
- τ² retail, Super/Nano vs Ultra (measured here, 20 tasks only);
- BFCL single-turn AST and live categories;
- GSM8K, IFEval / IFBench.

**Caveats:**
- The τ-bench 2.0 release replaced 50 retail and 50 telecom tasks and says its scores are not
  comparable with 1.x ([CHANGELOG](https://github.com/sierra-research/tau2-bench/blob/main/CHANGELOG.md)).
- The cards do not state the user simulator or trial counts.
- NVIDIA's own harness gives gpt-oss-20b 34.0 on SWE-bench, against OpenAI's 60.7.

---

## 3. Prior work: who has done what Downshift does

| Work | What it did | Reported | What it did **not** prove |
|---|---|---|---|
| **arXiv 2604.27082** "When Your LLM Reaches End-of-Life" (Apr 2026) | Production QA migration from Claude 3 Haiku to Qwen3-32B (thinking off) / Nova 2 Lite. Tried manual rewrites, the Bedrock optimizer and DSPy MIPROv2 | "Automatic and manual adaptation failed to produce prompts that are clearly better than the original." DSPy gains "don't replicate in the HotpotQA test set where accuracy decreased" ([html](https://arxiv.org/html/2604.27082v1), re-checked) | Single-turn QA, not agents; n = 200 / 200 / 51. **The strongest independent evidence that the plain swap is hard to beat** |
| GEPA (ICLR 2026) | Reflective instruction evolution for DSPy programs | Qwen3-8B aggregate 45.2 → 54.9, beating MIPROv2 (47.8) and GRPO (48.9), on held-out splits ([arXiv](https://arxiv.org/html/2507.19457v2)) | Optimizes on one model, with no big→small migration and no plain-swap comparison. Pipelines rather than open agents. Seed count not given |
| DSPy agents tutorial | MIPROv2 on a ReAct agent (HoVer) with Llama-3.2-3B | Recall 8.0% → 41.7% for about $5 ([dspy.ai](https://dspy.ai/current/tutorials/agents/)) | Dev set of 100 only, a single run, no large-model reference |
| PromptBridge (Dec 2025) | Learns a source→target prompt mapping ("model drifting") | HumanEval on Llama-3.1-70B 68.7 → 79.9; SWE-bench / Terminal-Bench gains mostly relative ([arXiv](https://arxiv.org/html/2512.01420v1)) | Downgrades barely tested; Terminal-Bench baselines tiny (15→18.75%); run counts unclear |
| Tursio prompt migration ([arXiv](https://arxiv.org/html/2507.05573v1)) | GPT-4-32k → GPT-4.1, manual fixes | 98% → 100% on a 110-question suite | No held-out set; an upgrade, not a downgrade |
| Databricks + GEPA ([blog](https://www.databricks.com/blog/building-state-art-enterprise-agents-90x-cheaper-automated-prompt-optimization)) | Optimized gpt-oss-120b vs Opus 4.1 on information extraction | +2–3 points over unoptimized Opus, ~90× cheaper, held-out set | No unoptimized gpt-oss score (so no plain swap); extraction, not agents |
| Arize prompt learning on Cline / Claude Code ([blog](https://arize.com/blog/optimizing-coding-agent-rules-claude-md-agents-md-clinerules-cursor-rules-for-improved-accuracy.md)) | Rules-file optimization on SWE-bench Lite, 150/150 split | Headline "10–15%" | Sonnet 4.5 test gain only +0.67 points; GPT-4.1 test numbers not shown |
| Quesma on τ² telecom ([blog](https://quesma.com/blog/tau2-benchmark-improving-results-smaller-models/)) | Policies rewritten for GPT-5-mini | pass^1 0.55 → 0.675 | 20 scenarios × 2 trials, no held-out set. **Closest agentic analogue, and it is on the same domain recommended below** |
| AWS Bedrock Advanced Prompt Optimization (May 2026) ([AWS](https://aws.amazon.com/blogs/aws/amazon-bedrock-introduces-new-advanced-prompt-optimization-and-migration-tool/)) | Migration product: baseline model plus up to 4 candidates, rewritten prompts, score / cost / latency | NESTFUL on Nova 2 Lite 0.267 → 0.647 | Run on 5 samples, "illustrative, not a benchmark"; prompt template only; no held-out set. A third party found an older version's gain came from failures scored as zero ([dev.to](https://dev.to/aws-builders/bedrock-prompt-shortening-6-optimizations-0-changes-a-fake-45-6ec)) |
| OpenAI prompt optimizer and guides ([docs](https://developers.openai.com/api/docs/guides/prompt-optimizer), [GPT-4.1 guide](https://developers.openai.com/cookbook/examples/gpt4-1_prompting_guide)) | Dataset/grader-driven prompt rewriting; agentic prompting advice | GPT-4.1: "close to 20%" SWE-bench gain from three reminders (internal) | No n or variance. The dataset mode goes away with Evals (read-only 31 Oct 2026). The GPT-5.2 guide advises swapping first as a baseline |
| Google Vertex prompt optimizer ([docs](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/learn/prompts/prompt-optimizer)), Meta llama-prompt-ops ([PyPI](https://pypi.org/project/llama-prompt-ops/)), Anthropic prompt improver ([post](https://www.anthropic.com/news/prompt-improver)) | Model-to-model prompt rewriting | Vertex: no published migration numbers. Meta: "substantial improvements" (**unverified**). Anthropic: "+30%" on one classification task | No methodology or held-out results published |
| NVIDIA Data Flywheel ([blog](https://developer.nvidia.com/blog/build-efficient-ai-agents-through-model-distillation-with-nvidias-data-flywheel-blueprint)) | Fine-tunes a 1B model on 70B tool-calling logs | "98% of the 70B's accuracy" | Fine-tuning, not prompts; LLM-judged; relative; no n |
| Not Diamond Prompt Adaptation ([blog](https://www.notdiamond.ai/blog/the-open-source-shift)) | Prompt adaptation for the target model | HotpotQA: Sonnet 4.5 82%; Kimi K2 with the same prompt 49.5%; adapted 87% (n=200) | **Does report the plain swap** (good), but vendor-run, single-turn, no held-out set or variance |
| RouteLLM ([paper](https://arxiv.org/html/2406.18665v3)); Martian, Portkey, OpenRouter Auto | Per-query routing | >85% cost cut at 95% of GPT-4 quality on MT-Bench (LLM-judged); Martian / Portkey claims have no methodology | Routing, not harness adaptation; single-turn. Humanloop shut down in Sep 2025 ([W&B](https://wandb.ai/wandb_fc/product-announcements-fc/reports/Humanloop-is-sunsetting-Migrate-to-Weights-Biases-as-an-alternative--VmlldzoxMzk4ODc1Nw)); Unify's pivot is **unverified** |

**The gap Downshift can fill.** I found no published work that does all of these at once:
- optimizes the full harness of a **multi-step tool-using agent** for a **downgrade**;
- grades against ground truth on a **held-out split**;
- **always reports the plain swap**;
- **re-checks with fresh repeated runs**.

The one rigorous independent study (2604.27082) found that adaptation did not beat the plain swap.
Downshift's own text2sql result is the same story: every Nano rewrite was worse than the swap. The
credible pitch is honest measurement, not large gains.

---

## 4. Recommended next test beds (ordered by value/effort)

The same rule applies to all three. Use **fresh runs of the real agent on the held-out tasks, 2 trials
each**, for: the baseline, the plain swap, and every recommended harness.

- **Proves the optimizer:**
  - the plain Nano swap is ≥15 points below the baseline in both fresh trials;
  - the rewrite recovers ≥10 points over the swap in both trials;
  - the paired task-level test against the swap reaches p < 0.1;
  - Downshift's replay estimate is within about 1 task of the fresh mean.
- **Disproves it:**
  - the rewrite is ≤ the swap in fresh runs, or its replay claim does not hold up; or
  - Downshift recommends a harness that falls below its bar in fresh runs, or says "just swap" where the swap fails.
- **Statistical power:** with 16 held-out tasks, p < 0.05 needs at least 6 one-directional discordant
  tasks. Prefer 30–40 held-out tasks where the cost allows.
- **Budget:** the plans below do not all fit in the ~$4.40 that is left. **Ask the user before any of them**, per CLAUDE.md.

### 1. tau2-bench **telecom** (highest value: published +22-point Nano→Super gap, judge-free, outside code, already vetted locally)

- **Interception, proxy path:**
  - Run `tau2 run --domain telecom --task-ids <id>` once per task, with
    `--agent-llm openai/<model> --agent-llm-args '{"api_base":"http://<proxy>/v1/t/<task_id>", ...}'`.
  - Point the user simulator straight at Token Factory, pinned to Super with thinking off at temperature 0.
  - Read the reward from tau2's results JSON.
- **Interception, adapter path:** a custom `HalfDuplexAgent` subclass whose `generate` calls `run.chat`,
  with tau2 tools going through `run.tool` and `reuse_tool_results = False`
  ([agent guide](https://github.com/sierra-research/tau2-bench/blob/main/src/tau2/agent/README.md)).
- **Tasks and answers:** the 40 telecom test tasks. `expected` is tau2's own ENV_ASSERTION/ACTION check,
  so there is no judge and no `communicate_info`.
- **Cost (estimated from the retail runs):**
  - Baseline should be **Super, not Ultra**: Ultra costs ~$0.14–0.20 per task, and on retail it scored
    *below* Super.
  - Per task: Super ~$0.04, Nano ~$0.02, user simulator included.
  - Total for 40 tasks: record ~$1.6, optimize ~$0.8, verify (16 held-out × 2 trials × 3 options) ~$2.6.
    That is **~$5**. A minimal version on the 20-task `small` split is ~$2.5.
  - Telecom conversation lengths are unmeasured, so run a **3-task smoke test (~$0.15) first**.
- **What would prove or disprove it:**
  - Proof: Nano swap ~40–45 vs Super ~60+ (as published), and a rewrite (tool descriptions, few-shot
    troubleshooting order, thinking on) recovering most of the gap.
  - Failure modes to watch: user-simulator noise (pass^k variance) or rewrites no better than the swap.

### 2. BFCL v4 **multi-turn** (deterministic, no user simulator, 15–21-point open-model gap, independent harness)

- **Interception:** prefer an adapter that subclasses BFCL's OpenAI-compatible function-calling handler
  and overrides the request call to use `run.chat`.
  - BFCL's own multi-turn executor runs the function calls (stateful, so `reuse_tool_results = False`).
  - The score is BFCL's state checker plus response checker.
  - Exact class and function names must be checked in `bfcl_eval` (**unverified**).
- **Proxy alternative:** `REMOTE_OPENAI_BASE_URL=<proxy>` with `--skip-server-setup`, single-threaded so
  calls can be matched to entries. This also needs a `model_config.py` entry for the Nemotron IDs.
- **Tasks:** 60 entries from `multi_turn_base` plus `multi_turn_miss_param`, split 36 / 24. `expected` is
  BFCL's ground-truth call path and final state.
- **Cost:** about 20–40k input tokens per entry (**unverified**), so Ultra ~$0.035, Super ~$0.01,
  Nano ~$0.002 per entry.
  - Ultra baseline: record ~$2.1, optimize ~$0.3, verify ~$2 (total ~$4.4).
  - Super baseline: total ~$1.2.
- **What would prove or disprove it:**
  - Proof: Nano swap ≥15 points below baseline on multi-turn, then recovered by tool-description and
    few-shot rewrites.
  - Control: run 40 `simple_python` entries (≈0 published gap, <$0.10). Downshift must answer "just swap" there.

### 3. BIRD mini-dev (SQLite) through the **existing text2sql adapter** (lowest effort; tests whether the one proven result generalises)

- **Interception:** unchanged (`examples/text2sql/downshift_agent.py`). It needs:
  - a per-task database path, since BIRD has 11 SQLite DBs rather than one merged DB;
  - a build script that appends BIRD's `evidence` to the question.
- **Tasks and answers:** 60–100 questions sampled across difficulty from the 500. `expected` is the gold
  SQL; scoring is BIRD's execution accuracy (row-set equality)
  ([mini_dev](https://github.com/bird-bench/mini_dev)).
- **Cost:** an estimated 1.5–2× Spider: Ultra ~$0.025, Super ~$0.005, Nano ~$0.004 per question.
  - 60 tasks with an Ultra baseline: record ~$1.5, optimize ~$0.4, verify 24 × 2 × 4 options ~$1.8
    (total ~$3.7).
  - With a Super baseline: ~$1.3.
- **What would prove or disprove it:**
  - Proof: Super is "just swap" again (as on Spider), and Nano's prose-instead-of-SQL failure is fixed by
    a rewrite that keeps thinking on (the Spider rewrites never managed this).
  - Disproof: Nano rewrites again ≤ the swap. That would be the second agent where the rewrite step
    adds nothing.

**Deferred:**
- mini-SWE-agent on 20 SWE-bench Verified instances. Best proxy fit (config-only `api_base`) and the
  largest published Nano→Super gap (+22), but Docker-heavy and ~$10–30 on Ultra.
- BALROG BabyAI-text. +43-point Llama gap and `base_url` config, but text actions rather than tool
  calls, and no Nemotron numbers published.

---

## Top 10 takeaways

1. **τ²-bench telecom is the best next test bed.** All 40 test tasks are graded without a judge (checked
   in the local v2.0.0 code), it is MIT and very active, and NVIDIA's own cards show Nano 42.2 vs Super 64.4.
2. **τ²'s judges are opt-in by data.** The judges (gpt-5.5 for communicate, gpt-5.4-mini for NL
   assertions) run only for tasks that list such criteria: 11/40 retail, 1/20 airline, 0/40 telecom.
3. **On τ² retail, Ultra scored below Super and Nano (9 vs 14 vs 14 of 20).** Downshift's "Ultra
   baseline" premise does not hold everywhere. Use Super as the baseline there; it is also ~5× cheaper.
4. **BFCL v4 multi-turn is the cleanest deterministic tool-calling bed:** state plus call-path checks, no
   user simulator, Qwen3 30B→235B gap of +15 to +21. Single-turn BFCL categories have ≈0 gap and
   serve as "just swap" controls.
5. **A recording proxy would attach to τ², mini-SWE-agent, BFCL, BALROG, OSWorld and ToolSandbox with
   no code changes.** It still needs per-task routing, separate URLs per role, live replays and
   ingestion of the benchmark's own results.
6. **Avoid as ground-truth beds:** StableToolBench (GPT-4 judge), MINT (GPT-4 feedback), TheAgentCompany
   (partly LLM-graded, heavy), OSWorld (VMs, vision), Spider 2.0 cloud tasks (Snowflake account
   suspended), GAIA (browsing, gated).
7. **15+-point small-vs-large gaps are published for:** τ² telecom and retail, BFCL multi-turn and web
   search, SWE-bench and Terminal-Bench (Nano→Super +22 / +17), BIRD mini-dev (+16), BabyAI (+43).
   Saturated with no headroom: GSM8K, IFEval, HumanEval, AIME. NESTFUL is inverted.
8. **The closest prior work does not support big rewrite gains.** The independent migration study
   (2604.27082) found that neither manual rewriting, nor the Bedrock optimizer, nor DSPy beat the original
   prompt. Arize's held-out gain was +0.67 points, and the vendor migration tools (AWS, Not Diamond,
   OpenAI) report n = 5–200 without held-out sets.
9. **Nobody publishes this combination:** agentic, downgrade, harness-wide rewrite, ground truth,
   held-out set, plain swap always shown, fresh-run re-check. That is Downshift's credible niche, and it
   also means reporting "the rewrite adds nothing" honestly, as on text2sql.
10. **Budget is the binding constraint.** About $4.40 is left of the $15 key. A proper τ² telecom run is
    ~$5 (or ~$2.5 minimal), BFCL ~$1.2–4.4, BIRD ~$1.3–3.7, so use Super baselines, smoke-test first, and
    get the user's go-ahead before each.
