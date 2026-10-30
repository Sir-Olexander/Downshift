# Nemotron 3 Nano / Super / Ultra: what the technical reports and model cards say, for harness writing

Compiled 2026-10-29. No model APIs were called. Sources are the NVIDIA technical reports, the Hugging Face (HF) model cards and chat templates, the vLLM, Ollama and TensorRT-LLM code and issues, Unsloth guides, and (for Q5) a read-only look at Downshift's own stored replays in `server/data/downshift.sqlite3`.
"Unverified" means I could not confirm it from a primary source. Benchmark numbers are as reported by the source, and harnesses differ between sources, so compare them only within one source.

---

## Q1. Reports, model cards, architecture, inference settings

### Sources

| Model | Technical report | HF model card |
|---|---|---|
| Nano | "Nemotron 3 Nano: Open, Efficient Mixture-of-Experts Hybrid Mamba-Transformer Model for Agentic Reasoning", arXiv **2512.20848**, PDF dated 2025-12-23 ([abs](https://arxiv.org/abs/2512.20848)). Family overview: "NVIDIA Nemotron 3: Efficient and Open Intelligence", arXiv **2512.20856** ([abs](https://arxiv.org/abs/2512.20856)) | [nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16](https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16), released 2025-12-15 |
| Super | "Nemotron 3 Super: Open, Efficient …", arXiv **2604.12374** (submitted 2026-04-14) ([html](https://arxiv.org/html/2604.12374v1), [NVIDIA PDF](https://research.nvidia.com/labs/nemotron/files/NVIDIA-Nemotron-3-Super-Technical-Report.pdf)) | [nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-BF16](https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-BF16), released 2026-03-11 |
| Ultra | "Nemotron 3 Ultra: Open, Efficient …", arXiv **2606.15007** (submitted 2026-06-12) ([abs](https://arxiv.org/abs/2606.15007), [NVIDIA PDF dated 2026-6-9](https://research.nvidia.com/labs/nemotron/files/NVIDIA-Nemotron-3-Ultra-Technical-Report.pdf)) | [nvidia/NVIDIA-Nemotron-3-Ultra-550B-A55B-BF16](https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Ultra-550B-A55B-BF16), released 2026-06-04 |

Note: NVIDIA has since released Nemotron **3.5** models (Lightning, Bolt, Super VL; see [Unsloth](https://unsloth.ai/docs/models/nemotron-3.5)), and Artificial Analysis lists Nemotron 3 Super as deprecated in favour of 3.5 Super VL ([AA](https://artificialanalysis.ai/models/nvidia-nemotron-3-super-120b-a12b)). This report covers only the Nemotron 3 models that Downshift uses.

### Architecture

| | Nano | Super | Ultra |
|---|---|---|---|
| Params | 31.6B total, 3.2B active (3.6B with embeddings) ([paper §2.1](https://arxiv.org/html/2512.20848)); the card says "30B total, 3.5B active" | 120.6B total, 12.7B active (12.1B without embeddings) ([paper §2.1](https://arxiv.org/html/2604.12374v1)) | 550B total, 55B active ([report §2.1](https://research.nvidia.com/labs/nemotron/files/NVIDIA-Nemotron-3-Ultra-Technical-Report.pdf)) |
| Layers | 52: 23 Mamba-2, 23 MoE, 6 GQA attention (2 KV heads) ([card](https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16)) | 88 layers: Mamba-2 + LatentMoE, a few attention "anchor" layers, 2 shared-weight MTP layers | 108 layers: Mamba-2 + LatentMoE + attention, 2 shared-weight MTP layers (report Table 1) |
| Experts | 128 routed + shared, top-6 | 512 per layer, top-22, latent size 1024 | 512 per layer, top-22, latent size 2048 |
| Context | Up to 1M; the HF config defaults to 256k ([card](https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16)) | Up to 1M; default 256k ([card](https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-BF16)) | Up to 1M; default 256k ([card](https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Ultra-550B-A55B-BF16)) |

`sdk/downshift/models.yaml` lists the context of Nano and Super as 262144. That is the serving default, not the model maximum. What Token Factory actually serves is unverified.

### Agent-relevant training

- **Nano** ([paper §3.1–3.2](https://arxiv.org/html/2512.20848))
  - SFT data: synthetic multi-turn conversational tool use (simulated user, agent and tools, filtered by an LLM judge); terminal-use trajectories; SWE trajectories (OpenHands, SWE-Agent, Mini-SWE-Agent); IFEval/IFBench-style instruction following. 18M samples.
  - RLVR environments include structured outputs (9K tasks, rewarded only on an exact JSON-schema match) and agentic tool use: "Workplace Assistant" (26 tools, 690 tasks) and a multi-turn banking environment (~1K tasks).
  - The paper does not use BFCL or tau-bench as RL environments.
  - Appendix C: a DPO experiment cut hallucinated tool calls (calls made when no tools are declared) from 8.33% to 0.7% on GPQA. The released model uses RL instead of DPO.
- **Super** ([paper §3](https://arxiv.org/html/2604.12374v1))
  - Conversational tool use was scaled to 279,116 conversations across 838 domains, against 15,588 across 5 domains for Nano.
  - 1.5M simulated general tool-calling trajectories; search-agent trajectories averaging 12 tool calls each; 84,864 terminal-use samples.
  - **Text-to-SQL SFT: 96.5k records.** NVIDIA's Data Designer note says this data raised Super's BIRD-dev score from 26.77% to 41.80% EX. Nano is not mentioned. The SQL prompt it used says "Return only the final SQL" ([NVIDIA](https://docs.nvidia.com/nemo/datadesigner/v0.8.0/dev-notes/text-to-sql-for-nemotron-super)).
  - RL: 21 environments and 37 datasets, plus SWE-RL and PivotRL (turn-level RL for agentic programming, search, terminal and conversational tool use).
- **Ultra** ([report §3](https://research.nvidia.com/labs/nemotron/files/NVIDIA-Nemotron-3-Ultra-Technical-Report.pdf))
  - SFT, then RLVR, then multi-teacher on-policy distillation (MOPD) from more than 10 specialised teachers.
  - The terminal SFT data (~370K conversations) is "a mixture of reasoning and non-reasoning trajectories". This is the only Nemotron 3 report that says this explicitly for agentic data.
  - The conversational tool-use teacher was trained on "sequential and dependent multi-step actions to discourage premature termination".
  - Structured-output training covers JSON, YAML, XML, TOML and CSV.
  - SWE RL penalises "malformed reasoning and tool calls".

### Reasoning on/off training (explains why "off" is weaker)

| Model | Reasoning-off training | Effort modes | Budget training |
|---|---|---|---|
| Nano | Traces stripped from a random **10%** of SFT samples ([§3.1.5](https://arxiv.org/html/2512.20848)) | None | 3% of traces truncated |
| Super | Traces stripped from only **3%** of samples ([§3.1.3](https://arxiv.org/html/2604.12374v1)) | low-effort (2% of SFT data) | 12% of traces truncated (350-step stage) |
| Ultra | Trained "for three reasoning modes: reasoning-off, regular and medium-effort" (§3.5); fraction not stated | medium-effort: ~2.5× fewer tokens for ~7% lower AA Intelligence Index | Truncated samples, with `</think>` masked |

None of the three reports gives reasoning-off scores on agentic benchmarks. The papers do not say how tool calling was trained in non-reasoning mode.

### Recommended sampling and max_tokens

| | Nano card | Super card | Ultra card |
|---|---|---|---|
| Reasoning on | temp 1.0, top_p 1.0 | temp 1.0, top_p 0.95 "across all tasks and serving backends" | temp 1.0, top_p 0.95 |
| Tool calling | **temp 0.6, top_p 0.95** | same 1.0 / 0.95 (no separate setting) | 1.0 / 0.95 |
| Reasoning off | Example uses greedy decoding | 1.0 / 0.95 | 1.0 / 0.95 |
| max_tokens | vLLM section: use a high value "such as 10,000" with reasoning on | Examples use 16000; OpenCode config uses 32000 | 16000; OpenCode 32000 |

Card links: [Nano](https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16), [Super](https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-BF16), [Ultra](https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Ultra-550B-A55B-BF16).

Unsloth's Super guide says temp 0.6 / top_p 0.95 for tool calling ([Unsloth](https://unsloth.ai/docs/models/nemotron-3/nemotron-3-super)). That conflicts with NVIDIA's Super card and looks copied from Nano. Prefer NVIDIA's card.

### How thinking is controlled (read from the chat templates themselves)

- **`enable_thinking`** (default True) is the only on/off switch in all three HF templates.
  - Off: the generation prompt ends `<|im_start|>assistant\n<think></think>`.
  - On: it ends `<think>\n`.
  - Templates: [Nano](https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16/raw/main/chat_template.jinja), [Super](https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-BF16/raw/main/chat_template.jinja), [Ultra](https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Ultra-550B-A55B-BF16/raw/main/chat_template.jinja).
- **Effort kwargs differ per model:**
  - Nano has none.
  - Super has `low_effort: true`, which appends `\n\n{reasoning effort: low}` to the last user message.
  - Ultra has `medium_effort: true`, which appends `\n\n{reasoning effort: efficient}`.
- **`/think` and `/no_think`:** the HF templates do not scan the system prompt for them. `/think` appears only inside the cards' budget example.
  - NVIDIA's RAG Blueprint says Super is switched with `/think` / `/no_think` in the system prompt ([RAG docs](https://docs.nvidia.com/rag/latest/enable-nemotron-thinking.html)). That is a Blueprint convention and is not in the HF template (unverified for NIM).
  - **Ollama's `nemotron3nano` renderer does scan user and system messages for `/think` and `/no_think` in its pre-v35 path** ([source](https://raw.githubusercontent.com/ollama/ollama/main/model/renderers/nemotron3nano.go)). On Ollama, a harness prompt that contains these strings can flip thinking.
- **Reasoning budget:** the cards describe a client-side `ThinkingBudgetClient` that works in two steps: generate up to `reasoning_budget`, close at the next newline (or at budget+500), then continue on the completions endpoint. It is not a request parameter on a plain chat endpoint.
  - Newer vLLM has `thinking_token_budget`. It was reported enforced on v0.30.0 ([vllm#39103](https://github.com/vllm-project/vllm/issues/39103)). Whether Token Factory supports it is unverified.
- **`reasoning_effort` is ignored by vLLM for Nemotron 3.**
  - [vllm#39581](https://github.com/vllm-project/vllm/issues/39581) (Super FP8, vLLM 0.19): `"low"` had "no meaningful effect", and `"none"` only hid the reasoning while still generating it (~315 vs ~372 tokens).
  - A vLLM contributor replied: "we currently do not support reasoning_effort, instead we support low_effort for Super through chat_template_kwargs … do not use reasoning_effort."
  - Both fix PRs were closed unmerged: [#39587](https://github.com/vllm-project/vllm/pull/39587), and [#39597](https://github.com/vllm-project/vllm/pull/39597) (auto-closed 2026-10-29).
  - **So on Token Factory the `low`/`medium`/`high` → `reasoning_effort` mappings in `models.yaml` probably do nothing** (unverified on Token Factory itself; Downshift has only verified `enable_thinking=false`).
- **History handling:** `truncate_history_thinking` (default True) drops reasoning from assistant turns before the last user message, but keeps reasoning between tool steps inside the current turn ([Nano paper Fig. 4](https://arxiv.org/html/2512.20848)).

### Tool-calling format and parsers

- **Format** (same template in all three): Qwen3-Coder-style XML, `<tool_call>\n<function=NAME>\n<parameter=ARG>\nVALUE\n</parameter>\n</function>\n</tool_call>`. Tool results are wrapped in `<tool_response>` inside a user turn.
- **Instruction text the template injects:**
  - "If you choose to call a function ONLY reply in the following format with NO suffix"
  - "You may provide optional reasoning for your function call in natural language BEFORE the function call, but NOT after"
  - "If there is no function call available, answer the question like normal … and do not tell the user about function calls"
  - Source: [Nano template](https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16/raw/main/chat_template.jinja). The paper chose XML "to reduce character escaping".
- **vLLM flags:**
  - All three: `--enable-auto-tool-choice --tool-call-parser qwen3_coder`.
  - Reasoning parser: Nano card uses the plugin `--reasoning-parser-plugin nano_v3_reasoning_parser.py --reasoning-parser nano_v3` (vllm ≥ 0.12). Super and Ultra use the built-in `--reasoning-parser nemotron_v3`. NVIDIA calls `nano_v3` deprecated in favour of `nemotron_v3` ([NVIDIA docs](https://docs.nvidia.com/nemo/labs-voice-agent/build-voice-agents/model-serving/v-llm-plugins/)).
  - Recipes: [vLLM Nano](https://github.com/vllm-project/recipes/blob/main/NVIDIA/Nemotron-3-Nano-30B-A3B.md), [vLLM Super](https://recipes.vllm.ai/nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-BF16).
- **Parser fallbacks:**
  - The `nano_v3` / `super_v3` parsers move text from reasoning into content when `enable_thinking` is False (or `force_nonempty_content` is True) and no content was parsed ([nano_v3](https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16/raw/main/nano_v3_reasoning_parser.py), [super_v3](https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-BF16/raw/main/super_v3_reasoning_parser.py)).
  - The Super and Ultra cards say to add `chat_template_kwargs: {force_nonempty_content: true}` "for coding agents". It is a parser flag, not a template variable.
- **Argument format:** the template needs tool-call `arguments` as a dict, not a JSON string. NVIDIA's advice is to `json.loads` them first ([HF discussion #51](https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16/discussions/51)).

### Stated limitations

- **Nano card:** with reasoning off there is "a slight decrease in accuracy for harder prompts that require reasoning". English and code are primary, with some other languages.
- **No card or report says "do not call tools with thinking off".** I found no such statement anywhere.
- **Super paper:** an FP16 Mamba cache raises verbosity by up to 40%. Super lags Qwen3.5-122B on several agentic benchmarks.
- **Ultra report §3.3.5:** MOPD for long-horizon agentic tasks is an open problem, and most agentic training used single-turn rollouts.

---

## Q2. Known issues

| Issue | What happens | Status / workaround |
|---|---|---|
| [HF Nano #3](https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16/discussions/3) "Tool calling with reasoning parsing broken" (vLLM 0.12) | Reasoning and `</think>` leak into content; tool calls unreliable | NVIDIA: "It's possible your completion token budget … is inadequate". Fixed by a nightly / [vLLM PR #30671](https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16/discussions/3). Users still saw hallucinated `str_replace_editor` tool names. The last question there (Apr 2026) is unanswered |
| [ai-dynamo/frontend-crates #381](https://github.com/ai-dynamo/frontend-crates/pull/381) | With thinking on, the model sometimes starts `<tool_call>` without closing `</think>`. A DeepSeek-R1-style parser then keeps the whole call in reasoning, giving an "empty stop". Seen in **27/1000** live responses | Fixed in Dynamo by treating `<tool_call>` as the end of reasoning. vLLM's `nemotron_v3` is DeepSeek-R1-based; whether vLLM has the same gap is unverified |
| [TRT-LLM #14502](https://github.com/NVIDIA/TensorRT-LLM/issues/14502) | Super with `enable_thinking=false`: 5–15% of responses have empty `content`, with the answer in `reasoning_content` | Open; [PR #14576](https://github.com/NVIDIA/TensorRT-LLM/pull/14576). Workaround: `force_nonempty_content: true` |
| [vllm#39581](https://github.com/vllm-project/vllm/issues/39581) | `reasoning_effort` is ignored; `none` hides the reasoning but still pays for it | Closed, not planned. Use `chat_template_kwargs` |
| [vllm#39103](https://github.com/vllm-project/vllm/issues/39103) | `--reasoning-config` gives `content: null` (Super) | Reported gone on v0.30.0 |
| [vllm#37362](https://github.com/vllm-project/vllm/issues/37362) | Nano with thinking on **plus** guided JSON (guidance backend): 8192 tokens generated, visible output `{` | Closed, not planned. Structured output works with thinking off |
| [llama.cpp #19765](https://github.com/ggml-org/llama.cpp/pull/19765) | Maintainer: `:\n\n` is a single token before tool calls. Re-fed history that tokenises differently can make the model "at some point get confused and stop doing tool calls" | Disputed; the real cause was traced to Responses-API message splitting (#19773). Lesson: history replay fidelity matters for Nemotron's multi-turn tool use |
| [llama.cpp #26737](https://github.com/ggml-org/llama.cpp/issues/26737) | `tool_choice: "required"` breaks the grammar for Nemotron-3 XML tool calls | Closed; `auto` works |
| [crewAI #4117](https://github.com/crewAIInc/crewAI/issues/4117) | Nano on Ollama "ignore[s] instructions entirely" and fails tool calls | Closed by stale bot. A commit merging system messages into user messages is referenced but unconfirmed |
| [ollama #13509](https://github.com/ollama/ollama/issues/13509) | Nano "loses chat history" | Cause: a 21k-token tool result overflowed `num_ctx`. Truncate tool output |
| [LM Studio #1865](https://github.com/lmstudio-ai/lmstudio-bug-tracker/issues/1865) | Nano 4B: tool calls trapped inside thinking; "chdir works the first time, then the respective tool is not called anymore" | Open. A user says disabling thinking helps; another reproduced the failure with thinking off |
| [NVIDIA forum](https://forums.developer.nvidia.com/t/tool-calling-not-working-with-nemotron-3-super-120b-a12b-nvfp4-on-dgx-spark-sm12-1/364804) | Super printed tool calls as raw JSON | Caused by the frontend (Open WebUI native function calling was off) |
| [NVIDIA-NeMo/Nemotron #386](https://github.com/NVIDIA-NeMo/Nemotron/issues/386) (2026-10-26) | Super told to make exactly 12 calls made 8–11, then `finish` claimed 12 | Open. A harness should count calls in code, not trust the model's claim |

I found no primary-source report that Nemotron 3 on vLLM turns tool calls into plain text **because of** `enable_thinking=false`. The parser path for thinking-off is designed to put the output into content, and the tool parser then runs on that.

---

## Q3. Benchmarks: where a swap should fail

### NVIDIA self-reported, reasoning on

Cards: [Nano](https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16), [Super](https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-BF16), [Ultra](https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Ultra-550B-A55B-BF16). The Ultra card often uses different benchmark versions.

| Benchmark | Nano | Super | Ultra |
|---|---|---|---|
| AIME25 (no tools) | 89.1 | 90.2 | — |
| GPQA (no tools) | 73.0 | 79.2 | 87.0 |
| LiveCodeBench | 68.3 (v6) | 81.2 (v5) | 89.0 (v6) |
| IFBench (prompt) | 71.5 | 72.6 | 81.7 (loose) |
| Multi-Challenge | 38.5 | 55.2 | 63.8 |
| SWE-Bench (OpenHands) | 38.8 | 60.5 | 70.7 (Verified) |
| Terminal Bench hard | 8.5 | 25.8 | TB 2.1: 56.4 |
| TauBench V2 average | 49.0 | 61.2 | V3 average 70.9 |
| BFCL v4 | 53.8 | — | — |
| BIRD (text-to-SQL) | — | 41.8 | — |
| AA-LCR (long context) | 35.9 | 58.3 | 65.4 |
| RULER @1M | 86.3 | 91.8 | 94.7 |
| HLE (no tools) | 10.6 | 18.3 | 26.7 |

### Artificial Analysis (independent), reasoning vs non-reasoning

Taken from AA via the graysoft.dev mirror, because AA's own pages did not render: [Nano reasoning](https://graysoft.dev/benchmarks/nvidia-nvidia-nemotron-3-nano-30b-a3b-reasoning.html), [Nano non-reasoning](https://graysoft.dev/benchmarks/nvidia-nvidia-nemotron-3-nano-30b-a3b.html), [Super](https://graysoft.dev/benchmarks/nvidia-nvidia-nemotron-3-super-120b-a12b.html), [Ultra](https://graysoft.dev/benchmarks/nvidia-nvidia-nemotron-3-ultra-550b-a55b.html). I could not check these against AA directly.

| AA metric | Nano, thinking OFF | Nano, thinking ON | Super ON | Ultra ON |
|---|---|---|---|---|
| τ²-Bench Telecom (tool use) | **25.4** | 40.9 | 67.8 | 83.3 |
| IFBench (format following) | **37.5** | 71.1 | 71.5 | 81.4 |
| Terminal-Bench Hard | 12.1 | 13.6 | 28.8 | 36.4 |
| AA-LCR (long context) | 10.7 | 38.0 | 65.7 | 79.3 |
| GPQA | 39.9 | 75.7 | 80.0 | 86.7 |
| LiveCodeBench | 36.0 | 74.1 | — | — |
| AIME25 | 13.3 | 91.0 | — | — |

### Reading

- **Nano is close to Super** on single-shot math and short instruction following (AIME, IFBench), but only with thinking on.
- **Nano falls far behind** on:
  - multi-turn tool use (τ²: 41 vs 68)
  - terminal and SWE agents (8.5 vs 25.8; 38.8 vs 60.5)
  - multi-turn instruction following (Multi-Challenge: 38.5 vs 55.2)
  - long-context reasoning (AA-LCR: 36–38 vs 58–66)
- **Nano with thinking off** loses about half its score on τ² and IFBench. That is far more than the card's "slight decrease".
- **Super also trails Ultra** on τ² (68 vs 83), so "close to Ultra" holds only for knowledge and math.
- **Expected swap failures:** long agent loops, multi-source synthesis, long context, and anything that needs format adherence with thinking off.

---

## Q4. Prompting guidance from NVIDIA and Unsloth

- **System prompt:** NVIDIA gives no system-prompt conventions beyond the template. The template appends tool instructions after the user's system text ([template](https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16/raw/main/chat_template.jinja)).
  - An external PR found that Nano made no tool call (0/5) until the system prompt explicitly said to use the tool ([AJMCS/Dockt #7](https://github.com/AJMCS/Dockt/pull/7); third-party).
- **Few-shot:** no NVIDIA guidance found (unverified). Few-shot given as user/assistant text turns shows the model plain-text answers. See Q5 for how this broke Downshift's Nano harness.
- **Structured output:** Nano was RL-trained for exact JSON-schema adherence ([Nano §3.2](https://arxiv.org/html/2512.20848)), and Ultra on JSON, YAML, XML, TOML and CSV.
  - Do not combine guided decoding with thinking on in vLLM ([#37362](https://github.com/vllm-project/vllm/issues/37362)).
- **Long context:** NoPE (no positional embeddings) means no YaRN is needed ([Unsloth](https://unsloth.ai/docs/models/nemotron-3)). Nano's RULER is strong at 1M (86.3), but AA-LCR reasoning is weak (35.9).
  - Ollama users hit context overflow from big tool results ([#13509](https://github.com/ollama/ollama/issues/13509)). Truncate tool outputs.
- **Effort and budget values:**
  - Nano: on/off plus a client-side budget.
  - Super: on/off, `low_effort`, budget.
  - Ultra: on/off, `medium_effort`, budget.
  - There is no "high" mode beyond default thinking.
  - NVIDIA's RAG Blueprint recommends `max_thinking_tokens` of 8192 for most uses and 1024–4096 for simple questions ([RAG docs](https://docs.nvidia.com/rag/latest/enable-nemotron-thinking.html)). Those are NIM/Blueprint parameters (unverified on vLLM or Token Factory).
- **Prefill:** thinking-off is a template prefill of `<think></think>`. I found no other documented prefill tricks.
- **Model migration guidance:** none found from NVIDIA (unverified). The Super blog only says Nano is suited to "executing targeted, individual steps within an agentic workflow", while complex tasks go to Super ([NVIDIA blog](https://developer.nvidia.com/blog/introducing-nemotron-3-super-an-open-hybrid-mamba-transformer-moe-for-agentic-reasoning/)).

---

## Q5. Is "never turn thinking off for Nano tool-calling steps" right?

### New evidence: Downshift's own stored replays

Source: `replays` table, Nano options of `opt_4dba6d045f4f` and `opt_10b7f3486f2d`, rounds 1–2, all with `reasoning: off`, temp 0.6, max_tokens 2000, Token Factory. The text2sql adapter renders `few_shot` as plain user/assistant text turns (`examples/text2sql/downshift_agent.py:_to_openai`).

| Rewrite | What its few-shot showed | What Nano did (8 tasks each) |
|---|---|---|
| opt_4dba r1 | Assistant turns containing tool calls **as text**: `{"tool": "execute_sql", "args": {...}}` lines, then the SQL | 0 real tool calls in 8/8. 5/8 copied the `{"tool": …}` text format. 3/8 answered SQL directly with guessed names |
| opt_4dba r2 | Same JSON-text examples | 7/8 wrote `{"tool": …}` text. 1/8 made 5 real calls (and passed) |
| opt_10b7 r1 | Assistant turns that answer **immediately** with a SQL block (no exploration) | 3/8 answered at once with guessed names (`players`, `continent_id`, `enrollment`). 2/8 made 1 real call, then gave a prose answer. 1/8 made 4 real calls and passed. 2/8 ran 50 real calls without stopping |
| opt_10b7 r2 | Same immediate-answer examples | 5/8 answered at once with no tool call. Others made 1–2 real calls. 1/8 ran 50 calls |

### Conclusions

1. **The "tool calls written as text" failure was copied from the rewriter's own few-shot examples.** It is not a thinking-off parser bug. Nano reproduced the exact invented `{"tool":…,"args":…}` syntax.
   - With thinking off, Nano did make real, parsed XML tool calls on Token Factory: 1 to 50 per run in opt_10b7.
   - So `enable_thinking=false` does not break tool-call parsing on Token Factory. This matches the coordinator's single-turn probe on Ollama.
2. **The other failures are behavioural:**
   - skipping the exploration the system prompt requires (and the few-shot shows skipping)
   - stopping after one call with a prose answer
   - looping until the 50-call cap
   
   These fit the weaker multi-turn tool use and instruction following with thinking off in the AA data (τ² 25 vs 41, IFBench 38 vs 71), and the small share of reasoning-off training data (10%).
3. **The 12.5% vs 56–62.5% comparison is confounded.** Every thinking-off run also had the misleading few-shot (plus temp and max_tokens changes). **No run tested thinking off alone.** The size of the pure thinking-off effect on text2sql is unknown.
4. **On the multi-turn vs single-turn question:**
   - Single-turn tool selection with thinking off works (coordinator probe; real calls in the replays).
   - The evidence that loops degrade is indirect: AA τ² (multi-turn) halves with thinking off; Ultra was specifically trained against "premature termination", which implies smaller models have that tendency; LM Studio #1865 and llama.cpp #19765 report tools stopping being called later in a conversation.
   - No primary source shows a Token-Factory-specific `enable_thinking=false` template bug.

### Verdict on the hypothesis

The evidence does not support the absolute "never". It supports this narrower rule:

- **Thinking off is fine** for a step that makes no tool call and has a pinned output format: classify, label, extract to a schema, rewrite (Nano is RL-trained for JSON-schema adherence).
- **Thinking off is also plausible** for a single, obvious tool call (one call, then stop). That is unverified beyond the probe.
- **Keep thinking on for Nano** in multi-turn tool loops where the model must decide what to explore and when to stop (text2sql, search loops). Turn it off there only if a controlled A/B shows no loss.
- **Never use few-shot that shows tool calls as text,** in any mode. Never use few-shot whose assistant turn skips steps the system prompt requires.

### Is "fix the guidance, then re-run Nano on text2sql" worth it?

Yes, as a cheap controlled experiment rather than another optimization.

- **Arms** (original text2sql prompt, no few-shot, same 16 held-out tasks, 2 trials each):
  - (a) thinking on, no max_tokens cap
  - (b) thinking off
  - (c) thinking on, plus one added rule that pins the final message ("End with only a ```sql block, no prose answer").
- **Cost:** Nano costs about $0.001–0.002 per task with thinking on, so 3 × 16 × 2 runs ≈ **$0.10–0.20**.
- **What it settles:** (b) vs (a) isolates thinking off; (c) tests the taxonomy's claim that a format fix gets 12–14/16.

### What the guidance should say

Draft for `MODEL_NOTES["nemotron-3-nano"]`:

> "Tool-loop steps: keep reasoning on, with max_tokens unset or ≥ 8000. Reasoning off is only for steps with no tool call and a pinned output format. Few-shot examples must never show tool calls as text (the API's tools field is the only way to call a tool) and must not skip steps the system prompt requires. Pin the final message format with an explicit closing rule. Count tool calls in code."

### MODEL_NOTES / GENERAL_TIPS / models.yaml: inaccuracies and omissions

1. **Nano, "Thinking can be switched off … makes short mechanical steps much cheaper":** this omits the large accuracy cost. AA: τ² 40.9→25.4 and IFBench 71.1→37.5 with thinking off. Only 10% of SFT data was non-reasoning. A tool-loop step is not "mechanical".
2. **Nano, "Strong for its cost on tool use":** only with thinking on. Its τ² is 49.0 (NVIDIA) and 40.9 (AA), against Super's 61.2 and 67.8.
3. **Nano sampling:** temp 0.6 / top_p 0.95 is right for tool calling (card). The note leaves out that reasoning tasks use 1.0 / 1.0, and that the reasoning-off example uses greedy decoding.
4. **Nano active params:** "~3B" should be 3.2B (3.6B with embeddings, paper) or 3.5B (card). Minor.
5. **Super, "temperature 0.6, top_p 0.95 for tool calling": wrong.** NVIDIA's card says 1.0 / 0.95 for all tasks including tool calling. The 0.6 comes from Unsloth.
6. **Super, "off is fine for planning and search steps":** unsourced. Super had only 3% reasoning-off SFT data and no published reasoning-off agentic numbers. Prefer `low_effort` for cheap Super steps.
7. **Super, "close to Ultra on well-specified tasks":** only for knowledge and math. On agentic benchmarks the gap is large (AA τ² 67.8 vs 83.3; Terminal-Bench Hard 28.8 vs 36.4).
8. **Missing for Super:**
   - the `low_effort` mode (the real "low")
   - `force_nonempty_content` for agents
   - 1M context
   - the BIRD 41.8 text-to-SQL data point
9. **Missing for Ultra:**
   - `medium_effort` (~2.5× fewer tokens, ~7% lower AA index)
   - sampling 1.0 / 0.95
   - 1M context
   - weaker-than-peer areas: SWE-Bench Verified 70.7, BrowseComp 44.4, TauBench V3 Banking 22.6
10. **GENERAL_TIPS, "2000+ for synthesis":** too low. Nano used 1,673–3,721 output tokens per text2sql task with thinking on (taxonomy doc). The cards use 10k–16k. Every rewrite set 2000.
11. **GENERAL_TIPS, "one or two few-shot examples of the exact output":** in a tool loop this is harmful (Q5). Restrict it to final-format steps, and show only the final message.
12. **GENERAL_TIPS, "moving reasoning off for mechanical steps":** needs the exception for tool loops.
13. **models.yaml: `low`/`medium`/`high` → `reasoning_effort` on Token Factory probably has no effect** (vLLM ignores it, #39581). Suggested mapping:
    - Super `low` → `chat_template_kwargs: {low_effort: true}`
    - Ultra `medium` → `{medium_effort: true}`
    - Nano: no effort levels, so the rewriter should not offer them.
    - Verify with token counts before relying on this.
14. **Missing everywhere:**
    - tool-call format (XML; the API `tools` field only)
    - history truncation
    - the Ollama `/think` / `/no_think` scanning gotcha
    - guided JSON plus thinking breaking in vLLM

Also seen: the text2sql runtime let some Nano runs reach 50 tool calls while the harness said `max_tool_calls: 8–10`. Check that the budget is enforced (`_recorded` returns a message but does not stop the loop).

---

## Q6. Harness-writing guides (for the rewriter)

### Nemotron 3 Nano (30B-A3B)

1. Thinking is controlled only by `enable_thinking` (default on). Off prefills `<think></think>`. There is no low or medium effort. [template](https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16/raw/main/chat_template.jinja)
2. Thinking off costs a lot: AA τ² 40.9→25.4, IFBench 71.1→37.5, AA-LCR 38→10.7. [AA mirror](https://graysoft.dev/benchmarks/nvidia-nvidia-nemotron-3-nano-30b-a3b.html)
3. Keep thinking ON for multi-turn tool loops. OFF only for steps with no tool call and a pinned format (JSON schema, label, one line). (Inference from 2 and Q5.)
4. Tool calls go through the API `tools` field. The model emits XML `<tool_call><function=…><parameter=…>`. Never describe or demonstrate tool calls as text in prompts or few-shot. (Q5 evidence; [template](https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16/raw/main/chat_template.jinja))
5. Few-shot is rendered as plain chat turns. Show only the final-answer format, and never skip steps the system prompt requires. (Q5)
6. Sampling: tool calling at temp 0.6, top_p 0.95; reasoning at 1.0 / 1.0. [card](https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16)
7. Thinking tokens count against max_tokens. With thinking on, leave max_tokens unset or ≥ 8000; NVIDIA suggests ~10,000. Nano used up to ~3.7k output tokens per text2sql task. [card](https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16); NVIDIA reply in [#3](https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16/discussions/3)
8. Pin the final message with an explicit closing rule, e.g. "End with exactly one ```sql block; no prose answer". With thinking on, Nano tends to report results in prose. (taxonomy doc)
9. Make the tool budget explicit and enforce it in code. Do not trust the model's own count. ([Nemotron #386](https://github.com/NVIDIA-NeMo/Nemotron/issues/386), shown for Super)
10. Truncate large tool outputs. Context overflow looks like "lost history". [ollama #13509](https://github.com/ollama/ollama/issues/13509)
11. Weak areas: long agent loops (Terminal Bench hard 8.5), SWE (38.8), multi-turn instructions (Multi-Challenge 38.5), long-context reasoning (AA-LCR 35.9). [card](https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B-BF16)
12. Strong areas: math, code and short instruction following with thinking on; JSON-schema adherence (RL-trained). [paper](https://arxiv.org/html/2512.20848)
13. On Ollama, avoid the literal strings `/think` and `/no_think` in prompts; the renderer may act on them. [renderer](https://raw.githubusercontent.com/ollama/ollama/main/model/renderers/nemotron3nano.go)

### Nemotron 3 Super (120B-A12B)

1. Modes: `enable_thinking` on/off; `low_effort: true` ("significantly fewer reasoning tokens"); client-side budget. [card](https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-BF16)
2. `reasoning_effort` is ignored by vLLM. Use `chat_template_kwargs`. [vllm#39581](https://github.com/vllm-project/vllm/issues/39581)
3. For cheap steps, prefer `low_effort` over off. Only 3% of SFT data was reasoning-off, and there are no published reasoning-off agentic scores (unverified effect). [paper §3.1.3](https://arxiv.org/html/2604.12374v1)
4. Sampling: temp 1.0, top_p 0.95 for all tasks, including tool calling. [card](https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-BF16)
5. max_tokens: NVIDIA uses 16000 for chat and 32000 for coding agents. Thinking counts against it. [card](https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-BF16)
6. For agents, add `force_nonempty_content: true`. It guards against empty `content` when the answer lands in reasoning. [card](https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Super-120B-A12B-BF16), [TRT-LLM #14502](https://github.com/NVIDIA/TensorRT-LLM/issues/14502)
7. Tool format and few-shot rules are the same as Nano's (same template). [paper](https://arxiv.org/html/2604.12374v1)
8. Trained on 96.5k text-to-SQL records; BIRD-dev 41.8% EX. [NVIDIA](https://docs.nvidia.com/nemo/datadesigner/v0.8.0/dev-notes/text-to-sql-for-nemotron-super)
9. Strong areas: long context (RULER@1M 91.8, AA-LCR 58), tool use (AA τ² 67.8).
10. Weaker than Ultra: τ² (67.8 vs 83.3), Terminal-Bench Hard (28.8 vs 36.4), HLE. [AA mirror](https://graysoft.dev/benchmarks/nvidia-nvidia-nemotron-3-super-120b-a12b.html)
11. May over-claim completed tool calls. Verify counts in code. [Nemotron #386](https://github.com/NVIDIA-NeMo/Nemotron/issues/386)

### Nemotron 3 Ultra (550B-A55B)

1. Modes: on/off; `medium_effort: true` (~2.5× fewer tokens, ~7% lower AA index); budget. No `low_effort`. [report §3.5](https://research.nvidia.com/labs/nemotron/files/NVIDIA-Nemotron-3-Ultra-Technical-Report.pdf), [template](https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Ultra-550B-A55B-BF16/raw/main/chat_template.jinja)
2. Trained for reasoning-off as a named mode, with mixed reasoning and non-reasoning agentic (terminal) trajectories. Off is better supported than on Nano (the off-mode size of effect is unverified). [report](https://research.nvidia.com/labs/nemotron/files/NVIDIA-Nemotron-3-Ultra-Technical-Report.pdf)
3. Sampling: temp 1.0, top_p 0.95 everywhere; max_tokens 16000 (32000 for coding agents). [card](https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Ultra-550B-A55B-BF16)
4. Add `force_nonempty_content: true` for agents. The card says SGLang tool calls need it. [card](https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Ultra-550B-A55B-BF16)
5. Tool format: same XML template. [template](https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Ultra-550B-A55B-BF16/raw/main/chat_template.jinja)
6. Trained against premature termination in multi-step tool use; JSON/YAML/XML/TOML/CSV structured output; citation formatting. [report §3.3](https://research.nvidia.com/labs/nemotron/files/NVIDIA-Nemotron-3-Ultra-Technical-Report.pdf)
7. Strong areas: τ² (AA 83.3), AA-LCR 79.3, IFBench 81.4, low hallucination (OmniScience non-hallucination 78.7).
8. Weaker than peers: SWE-Bench Verified 70.7, BrowseComp 44.4, TauBench V3 Banking 22.6. [card](https://huggingface.co/nvidia/NVIDIA-Nemotron-3-Ultra-550B-A55B-BF16)

---

## Top 10 takeaways

1. **The "tool calls as text" failure came from the harness.** Downshift's Nano rewrite showed `{"tool": …, "args": …}` text in its few-shot, and Nano copied it. With thinking off, Nano still made real, parsed tool calls on Token Factory.
2. **No run has tested thinking off alone on text2sql.** Every thinking-off run also had misleading few-shot. The 12.5% vs 56–62% gap is confounded.
3. **Thinking off still costs Nano a lot** in independent data: τ² 41→25, IFBench 71→38, AA-LCR 38→11. Only 10% of Nano's SFT data was non-reasoning. Keep it on for multi-turn tool loops.
4. **The rule should be narrower than "never":** off is fine for steps with no tool call and a pinned format, plausibly fine for one obvious call, and on (or A/B-tested) for loops.
5. **The re-run is worth doing as a controlled A/B,** not another optimization: original prompt, no few-shot; thinking on vs off vs on plus a format rule; 16 tasks × 2 trials; about $0.10–0.20.
6. **On vLLM, `reasoning_effort` does nothing for Nemotron 3.** Downshift's `low`/`medium`/`high` mappings on Token Factory are probably inert. Use `low_effort` (Super) and `medium_effort` (Ultra); Nano has neither.
7. **Super's NVIDIA sampling is temp 1.0 / top_p 0.95 for everything, including tools.** The 0.6 in MODEL_NOTES comes from Nano and Unsloth.
8. **Thinking tokens count against max_tokens.** NVIDIA uses 10k–16k. The rewriter's 2000 is too low for thinking-on steps.
9. **Few-shot is rendered as plain chat turns.** Never show tool calls as text, and never skip required steps in examples. Use few-shot only to pin the final format.
10. **Nano is close to Super only on math and short instruction following** (thinking on). It is far behind on multi-turn tool use, SWE and terminal agents, multi-turn instructions and long-context reasoning. Expect swaps to fail there.
