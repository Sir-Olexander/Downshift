# Ollama Cloud models for Downshift: research and 7 picks

Checked on 2026-10-29. The research used web pages only: Ollama library, docs and pricing pages, Hugging Face cards, vendor docs, arXiv, the Nebius Token Factory catalog and OpenRouter's public endpoint listings. No model API was called for this report.

The "probe" findings come from a separate live probe the team ran today: six tiny requests per model on `https://ollama.com/v1`, as reported by the coordinator. I did not run it myself.

Conventions:
- "TF" means Nebius Token Factory.
- Prices are USD per 1M tokens, shown as input / cached input / output.
- "unverified" means no first-party source confirmed the fact.

Main sources used throughout:
- TF catalog (it names `/api/public/models_info` as authoritative; the page has no date): https://tokenfactory.nebius.com/model-catalog.md
- Ollama per-token prices: https://ollama.com/pricing
- Ollama OpenAI-compatible endpoint: https://docs.ollama.com/api/openai-compatibility

---

## 1. Every non-Nemotron model on the account

The table covers all 20 non-Nemotron ids. Thinking control is described two ways: the vendor's documented control, then what the probe saw with `reasoning_effort` on Ollama `/v1`.

**Beam and Muse Spark Open, identified:**
- **`beam`** is **Reflection AI's Beam 1.0**, 501B total / 23B active, open weights under Apache-2.0. It was announced 2026-10-05 and generally available 2026-10-16.
  - https://reflection.ai/blog/beam-is-available
  - https://huggingface.co/reflection/Beam-1.0-501B-A23B
- **`muse-spark-open`** is **Meta's Muse Spark Open**, 816B total / ~42B active, released 2026-10-15 under the custom Muse Model License. It is the open-weight version of Muse Spark. That it came from Meta Superintelligence Labs specifically is unverified.
  - https://research.meta.ai/blog/muse-spark-open
  - https://huggingface.co/meta-models/Muse-Spark-Open-816B-A42B
- **`clef:27b`** is Cloudflare's decision model, not a chat model (see row 2).

| Ollama id | Vendor | Released | Total / active params, architecture | Context (vendor / Ollama) | License | Thinking and its control | Tools | Paper / card | Reference price and source | TF id |
|---|---|---|---|---|---|---|---|---|---|---|
| `beam` | Reflection AI | Announced 2026-10-05, GA 2026-10-16 ([blog](https://reflection.ai/blog/beam-is-available)) | 501.3B / 23.4B. Sparse MoE (52 layers, 256 experts), GQA plus sliding window. Text only ([HF](https://huggingface.co/reflection/Beam-1.0-501B-A23B)) | 1M / 1M | Apache-2.0 | Always reasons ("modified Harmony" format). Effort low/medium/high/xhigh/max; the default is disputed, medium ([HF blog](https://huggingface.co/blog/reflection-beam)) or max ([vLLM recipe](https://recipes.vllm.ai/reflection/Beam-1.0-501B-A23B)). **Probe: `none` ignored.** | Yes. Own XML-style grammar, parsed by Ollama | **No technical report yet** ("coming"). [Model card](https://reflection.ai/beam-model-card), [safety report](https://reflection.ai/beam-safety-report) | **TF 0.25 / 0.05 / 1.00**. Free on Ollama "for a limited time" ([Ollama blog](https://ollama.com/blog/reflection-beam)) | `reflection/beam` |
| `clef:27b` | Cloudflare | 2026-10-01 ([changelog](https://developers.cloudflare.com/changelog/post/2026-10-01-clef-workers-ai/)) | 27B, post-trained from Qwen3.8-27B. Adds a non-autoregressive "joint schema head" ([blog](https://blog.cloudflare.com/clef-decision-models/)) | 65,536 / 64K | Apache-2.0 | None | **None.** Returns typed decisions with probabilities from `POST /v1/systemone` ([docs](https://docs.ollama.com/capabilities/decision)). **Probe: 400 on every chat request.** | No paper. Blog and [HF](https://huggingface.co/Cloudflare/clef) | Cloudflare and Ollama charge 0.24 input; output is free | not on TF |
| `deepseek-v4-pro:0813` | DeepSeek | Preview 2026-04-24. 0813 is the 2026-08-13 GA checkpoint ([updates](https://api-docs.deepseek.com/updates/)) | 1.6T / 49B on the preview card. The 0813 card says "1.7T" (it adds a DSpark speculative-decoding module); active count not stated. MoE with CSA+HCA hybrid attention and mHC ([HF](https://huggingface.co/deepseek-ai/DeepSeek-V4-Pro-0813)) | 1M / 1M (TF lists 979K) | MIT | Non-think / Think High / Think Max. API: `thinking` plus `reasoning_effort` low/high/max, default high ([guide](https://api-docs.deepseek.com/guides/thinking_mode)). **Probe: `none` turns it off.** | Yes. On DeepSeek's API, `reasoning_content` must be sent back on tool turns | **Real paper**, [arXiv 2606.19348](https://arxiv.org/abs/2606.19348) | **TF 1.32 / 0.04 / 3.96**. DeepSeek and Ollama charge the same at peak and half off-peak | `deepseek-ai/DeepSeek-V4-Pro-0813` |
| `deepseek-v4.1-flash` | DeepSeek | 2026-09-10 ([updates](https://api-docs.deepseek.com/updates/)) | 552B backbone; 763B in safetensors including a 196B Engram memory. About 8B active in prefill and 16B in decode. Multimodal MoE encoder-decoder with CSA2 and FP4 KV cache ([HF](https://huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash)) | 1M / 1M | MIT | API low/high/max. The card describes integer effort 1–100. **Probe: `none` turns it off.** | Yes | **Real paper**, [arXiv 2609.19969](https://arxiv.org/abs/2609.19969) | **TF 0.30 / 0.01 / 1.20** | `deepseek-ai/DeepSeek-V4.1-Flash` |
| `deepseek-v4.1-flash:1017` | DeepSeek | 2026-10-17 snapshot with shorter outputs ([HF](https://huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash-1017)) | Same as the row above | 1M / 1M | MIT | Same as the row above. The probe did not report on this tag separately (unverified). | Yes | Same paper | **TF 0.30 / 0.006 / 1.20**. Ollama matches at peak | `deepseek-ai/DeepSeek-V4.1-Flash-1017` |
| `gemma4:31b` | Google DeepMind | 2026-03-31 ([releases](https://ai.google.dev/gemma/docs/releases)) | 30.7B **dense**. Sliding-window (1024) attention interleaved with global layers; ~550M vision encoder ([card](https://ai.google.dev/gemma/docs/core/model_card_4)) | 256K / 256K | Apache-2.0 | On/off only: `<\|think\|>` in the system prompt, or `enable_thinking` in the template. **Probe: does not think by default; `low` turns thinking on.** | Yes. Native `<\|tool_call>` tokens ([docs](https://ai.google.dev/gemma/docs/capabilities/text/function-calling-gemma4)) | **Real paper**, [arXiv 2607.02770](https://arxiv.org/abs/2607.02770) | **OpenRouter median 0.145 / 0.40** across 16 endpoints; cheapest 0.10 / 0.34 ([endpoints](https://openrouter.ai/api/v1/models/google/gemma-4-31b-it/endpoints)). Ollama 0.14 / 0.05 / 0.40. Google has no paid API price | not served for inference; fine-tuning only ([docs](https://docs.tokenfactory.nebius.com/post-training/models)) |
| `glm-5.2` | Z.ai | Open weights 2026-06-16 ([Willison](https://simonwillison.net/2026/jun/17/glm-52/)) | 753B / ~39–40B (third-party figure). MoE with sparse attention and IndexShare ([HF](https://huggingface.co/zai-org/GLM-5.2)) | 1M / 976K | MIT | On by default; can be disabled (`thinking.type: disabled`). **Probe: `none` turns it off.** | Yes (glm47 parser) | GLM-5 family report, [arXiv 2602.15763](https://arxiv.org/abs/2602.15763); nothing specific to 5.2 | **TF 1.40 / 0.14 / 4.40** | `zai-org/GLM-5.2` |
| `glm-5.3` | Z.ai | Announced 2026-08-14, weights about 2026-08-27 | 753B ([HF](https://huggingface.co/zai-org/GLM-5.3)) / ~40B active (third-party: [Artificial Analysis](https://artificialanalysis.ai/models/glm-5-3)). Same base as 5.2, newer post-training | 1M / 1M (TF lists 1,024,000) | Custom GLM-5.3 License: MIT-style, plus a Z.ai security review for model-as-a-service firms over $10B revenue ([LICENSE](https://huggingface.co/zai-org/GLM-5.3/blob/main/LICENSE)) | Z.ai: thinking cannot be disabled; effort low/high/max, **default max** ([docs](https://docs.z.ai/guides/llm/glm-5.3)). **Probe: `none` turns it off on Ollama**, which contradicts the vendor docs (see takeaway 4) | Yes | GLM-5 family report (2602.15763) | **TF 1.40 / 0.26 / 4.40**. TF serves a third-party NVFP4 quantization | `zai-org/GLM-5.3` |
| `glm-5.3-flash` | Z.ai | 2026-08-26 | 320B / 18B. Hybrid sparse plus linear attention; natively multimodal ([docs](https://docs.z.ai/guides/llm/glm-5.3-flash)) | 1M / 1M | MIT | Same as GLM-5.3: Z.ai says "thinking cannot be disabled" and recommends `max`. **Probe: `none` turns it off.** | Yes; Z.ai recommends `tool_stream` | GLM-5 family report | **TF 0.15 / 0.03 / 0.50** | `zai-org/GLM-5.3-Flash` |
| `gpt-oss:120b` | OpenAI | 2025-08-05 | 116.8B / 5.1B. MoE with 128 experts (top 4); alternating banded-window and dense attention ([card](https://arxiv.org/abs/2508.10925)) | 131,072 / 128K | Apache-2.0 | Always reasons. Effort low/medium/high (default medium) through harmony `Reasoning:`. **Probe: `none` ignored; `low` shortens reasoning.** | Yes, on the harmony `commentary` channel | **Model card, not a full paper** ([arXiv 2508.10925](https://arxiv.org/abs/2508.10925)) | **TF 0.15 / 0.10 / 0.60**. Ollama 0.15 / 0.014 / 0.60 | `openai/gpt-oss-120b` |
| `gpt-oss:20b` | OpenAI | 2025-08-05 | 20.9B / 3.6B. MoE with 32 experts (top 4) | 131,072 / 128K | Apache-2.0 | Same as 120b. **Probe: `none` ignored; `low` shortens reasoning.** | Yes | Same model card | **OpenRouter median 0.03 / 0.145** across 10 endpoints ([endpoints](https://openrouter.ai/api/v1/models/openai/gpt-oss-20b/endpoints)). OpenAI has no API price. Ollama 0.07 / 0.035 / 0.30 | not on TF |
| `kimi-k2.6` | Moonshot AI | 2026-04-20 (secondary source) | 1T / 32B. MoE with MLA; 384 experts with 8 active; MoonViT vision encoder ([HF](https://huggingface.co/moonshotai/Kimi-K2.6)) | 256K / 256K | Modified MIT | Hybrid: `thinking` enabled or disabled ([API](https://platform.kimi.ai/docs/api/models-overview)). **Probe: `none` turns it off.** | Yes. K2-format ids `functions.name:idx` ([guidance](https://huggingface.co/moonshotai/Kimi-K2-Thinking/blob/main/docs/tool_call_guidance.md)) | K2.5 paper, [arXiv 2602.02276](https://arxiv.org/abs/2602.02276); nothing specific to K2.6 | **TF 0.95 / 0.16 / 4.00**. The TF status read "error" at check time | `moonshotai/Kimi-K2.6` |
| `kimi-k2.7-code` | Moonshot AI | 2026-06-12 (secondary source) | 1T / 32B, same design as K2.6 ([HF](https://huggingface.co/moonshotai/Kimi-K2.7-Code)) | 256K / 256K | Modified MIT | Vendor: always on, no Instant mode. **Probe: `none` turns it off on Ollama.** | Yes | No paper | **TF 0.95 / 0.15 / 4.00** (TF status "error") | `moonshotai/Kimi-K2.7-Code` |
| `kimi-k3` | Moonshot AI | API 2026-07-16 (secondary source); weights 2026-07-27 | 2.8T / 104B. MoE with hybrid KDA plus Gated MLA attention ([HF](https://huggingface.co/moonshotai/Kimi-K3)) | 1,048,576 / 1M | Kimi K3 License: MIT-based, with extra conditions | Vendor: always on; effort low/high/max, default max ([quickstart](https://platform.kimi.ai/docs/guide/kimi-k3-quickstart)). **Probe: `none` turns it off on Ollama.** | Yes | **Real paper**, [arXiv 2607.24653](https://arxiv.org/abs/2607.24653) | **TF 3.00 / 0.30 / 15.00** | `moonshotai/Kimi-K3` |
| `minimax-m2.7` | MiniMax | 2026-03-18 ([news](https://www.minimax.io/news/minimax-m27-en)) | 230B / 10B MoE ([NVIDIA](https://docs.api.nvidia.com/nim/reference/minimaxai-minimax-m2.7)) | 204,800 / 200K | Non-commercial per the [LICENSE](https://huggingface.co/MiniMaxAI/MiniMax-M2.7/blob/main/LICENSE). NVIDIA says "Modified MIT", which conflicts | Interleaved `<think>`, always on. **Probe: `none` ignored.** | Yes (minimax_m2 XML format) | **Real paper**, [arXiv 2605.26494](https://arxiv.org/abs/2605.26494) (M2 series) | 0.30 / 1.20, MiniMax's price as quoted by [Artificial Analysis](https://artificialanalysis.ai/models/minimax-m2-7). Ollama 0.30 / 0.06 / 1.20 | not on TF |
| `minimax-m3` | MiniMax | 2026-06-01 (secondary source) | ~428B / ~23B. MoE with MiniMax Sparse Attention; multimodal ([HF](https://huggingface.co/MiniMaxAI/MiniMax-M3)) | 1M with 512K guaranteed ([MiniMax](https://www.minimax.io/models/text/m3)) / 512K | MiniMax Community License (attribution required; authorization needed above $20M revenue) | Modes enabled/adaptive/disabled; MiniMax's API has no `reasoning_effort` ([API](https://platform.minimax.io/docs/api-reference/text-openai-api)). **Probe: `none` turns it off.** | Yes | Attention paper only, [arXiv 2606.13392](https://arxiv.org/abs/2606.13392) | **TF 0.30 / 0.06 / 1.20**. Ollama shows 0.60 / 0.12 / 2.40, MiniMax's long-context tier | `MiniMaxAI/MiniMax-M3` |
| `minimax-m3.1-flash` | MiniMax | 2026-10-19 ([blog](https://www.minimax.io/blog/minimax-m31f)) | ~428B / 23B (the HF safetensors box says 220B, a conflict) ([HF](https://huggingface.co/MiniMaxAI/MiniMax-M3.1-Flash)) | 1M / 976K | minimax-community | Vendor: always on; effort low..max, default max; `none` returns 400 on MiniMax's API. **Probe: `none` turns it off on Ollama.** | Yes | Attention paper only | **TF 0.15 / 0.015 / 0.60** | `MiniMaxAI/MiniMax-M3.1-Flash` |
| `mistral-large-3:675b` | Mistral AI | 2025-12-02 ([news](https://mistral.ai/news/mistral-3)) | 675B / 41B. MoE with MLA ([HF](https://huggingface.co/mistralai/Mistral-Large-3-675B-Instruct-2512)) | 256K / 256K | Apache-2.0 | **No thinking** | Yes. Tool-call ids must be 9 alphanumeric characters (reported in issue trackers; unverified on Ollama) | No paper | 0.50 / 1.50, Mistral API ([docs](https://docs.mistral.ai/models/mistral-large-3-25-12)) | not on TF |
| `mistral-large-4` | Mistral AI | Preview 2026-10-06; weights about 2026-10-29 ([news](https://mistral.ai/news/mistral-large-4/)) | ~1.05T / 49B (52B counting embeddings). MoE with MLA and a DSA indexer; 1.6B Pixtral vision encoder ([vLLM](https://vllm.ai/blog/2026-10-29-mistral-large-4)) | 1M / 1M | Mistral Ecosystem Open-Weight License | Effort low/medium/high, default high; no `none` ([docs](https://docs.mistral.ai/capabilities/reasoning)). **Probe: `none` returns 500; thinks at length by default.** | Yes | No paper | 0.70 / 0.07 / 2.10, Mistral API ([docs](https://docs.mistral.ai/models/mistral-large-4-0)) | not on TF |
| `muse-spark-open` | Meta | 2026-10-15 ([blog](https://research.meta.ai/blog/muse-spark-open)) | 816B / ~42B (HF and Ollama list 822B). MoE with 256 experts and 8 active; 1.8B Perception Encoder ([HF](https://huggingface.co/meta-models/Muse-Spark-Open-816B-A42B)) | 1,048,576 / 1M | Muse Model License (custom; requires "Built with Muse Spark Open") | Vendor: always on; effort low/medium/high/xhigh, **default xhigh**; `none` rejected ([settings](https://dev.meta.ai/docs/muse-spark-open/settings)). **Probe: `none` turns it off on Ollama.** | Yes, OpenAI format; results must be returned in call order ([prompting](https://dev.meta.ai/docs/muse-spark-open/prompting)) | **No paper**. Card and an evaluation-methodology document | **TF 1.25 / 0.15 / 4.25** | `meta-models/muse-spark-open` |

**JSON-schema output (probe).** `response_format: json_schema` came back as bare JSON only from:
- deepseek
- gpt-oss:20b
- minimax-m3 and m3.1-flash
- muse-spark-open
- beam
- nemotron

The others wrapped the JSON in a fenced ```json block. mistral-large-3 returned prose.

**TF serves 14 of these 20 models:**
- DeepSeek ×3
- GLM ×3
- MiniMax M3 and M3.1-Flash
- Kimi ×3
- gpt-oss-120b
- beam
- muse-spark-open

It does not serve gpt-oss:20b, gemma4:31b (fine-tuning only), minimax-m2.7, clef or either Mistral model.

## 2. Ollama Cloud facts

**OpenAI-compatible endpoint, `https://ollama.com/v1`** ([docs](https://docs.ollama.com/api/openai-compatibility)):
- **Supported:**
  - streaming
  - JSON mode and `response_format`
  - `seed`
  - vision (base64 images only)
  - `tools`
  - `reasoning_effort` and `reasoning.effort`
  - `stream_options.include_usage`
  - `temperature`, `top_p`, `max_tokens`, `stop`, and the frequency and presence penalties
- **Not supported:**
  - **`tool_choice`**
  - **logprobs**
  - `n`
  - `logit_bias`
  - `user`
  - image URLs
- **Responses API:** stateless only (no `previous_response_id` or `conversation`), no built-in web search, no custom or freeform tool-call replay.

**How `reasoning_effort` values are resolved:**
- Models with metadata: supported level names are applied exactly. **Unsupported names silently fall back to the model's default.** The default for GLM-5.3 and Kimi K3 is max, and for Muse Spark Open it is xhigh.
- Boolean-only models: any recognised level means on, and `none` means off.
- Models without metadata: `minimal` maps to `low`, and `xhigh`/`ultra` map to `max`.
- gpt-oss: `minimal` maps to `low`, `xhigh`/`ultra` map to `high`, and `none` "requests no thinking output". The probe shows `none` does not stop the reasoning itself.
- Each model's valid values are listed by `/api/show`.

**Reasoning in the response.** Not documented for `/v1` chat completions; third parties report a `reasoning` field (unverified, [hermes-agent#46131](https://github.com/NousResearch/hermes-agent/issues/46131)). On native `/api/chat`, reasoning comes back in `message.thinking`, and `think` takes true/false/null or a level name ([docs](https://docs.ollama.com/capabilities/thinking)).

**Structured outputs.** The docs say "Ollama's cloud currently does not support structured outputs" ([docs](https://docs.ollama.com/capabilities/structured-outputs)). This matches the probe: schema output is honoured only by some models and is not enforced.

**Plans** ([pricing](https://ollama.com/pricing)):

| Plan | Price | Included usage | Concurrent requests |
|---|---|---|---|
| Pay as you go | $0 | none | 3 |
| **Pro** | **$20/mo** | **$60/mo** | **3** |
| Max | $100/mo | $300/mo | 10 |
| Team | $500/mo | $1,000/mo | 10 |

- Requests over the concurrency limit are queued; when the queue is full they are rejected.
- Included usage resets monthly and does not roll over. After that, Ollama draws on purchased credits.
- Paid plans get an email at 90% of included usage.
- **"The session and weekly limits of the old plans no longer apply."** Usage is now credit-based, not session-capped.
- Usage page: https://ollama.com/settings/usage. The cloud docs give no numeric rate limits ([docs](https://docs.ollama.com/cloud)).

**Per-token prices.** Ollama publishes them at https://ollama.com/pricing, and they are what the Pro credits are drawn down by. Off-peak rates apply outside 12:00–18:00 UTC on weekdays and all weekend; only DeepSeek shows separate off-peak prices.
- Beam is not on the pricing page (free for a limited time).
- Ollama's Nemotron 3 Super row reads 0.015 / 0.015 / 0.60 and Ultra reads 0.10 / 0.10 / 3.00. These look like errors on the page compared with TF's 0.30 / 0.90 and 1.00 / 3.00. Do not use them.

## 3. The 7 picks

They form three cheap/expensive pairs plus one small dense model. Tiers: 3 small (gpt-oss:20b, gemma4:31b, glm-5.3-flash), 2 mid (gpt-oss:120b, deepseek-v4.1-flash:1017) and 2 frontier (glm-5.3, deepseek-v4-pro:0813).

1. **`gpt-oss:20b` (small).** The cheapest model with a strong agent reputation (3.6B active), paired with gpt-oss:120b from the same training recipe and harmony format. A plain swap from 120b to 20b is the cleanest within-family test available.
   - The vendor documents it well: model card, harmony guide, and an explicit low/medium/high effort.
   - Weaknesses: there is only a model card, not a paper; it is not on TF, so its price comes from the OpenRouter median; and reasoning cannot be turned off (the probe shows `none` is ignored).
   - JSON-schema output comes back bare.
2. **`gpt-oss:120b` (mid).** The expensive half of the gpt-oss pair, served by TF at 0.15 / 0.60, which is cheaper than Nemotron 3 Super. It gives a second non-NVIDIA mid-size reference.
   - Same documentation and the same "no off switch" caveat as 20b. Use `low` as the cheapest setting.
3. **`deepseek-v4.1-flash:1017` (mid).** The cheap half of the DeepSeek pair. It has a real technical paper (arXiv 2609.19969), MIT weights, a 1M context, the exact TF id `deepseek-ai/DeepSeek-V4.1-Flash-1017`, and a working `none` off switch per the probe.
   - Bare JSON-schema output. Pinned to the dated snapshot so the Ollama and TF runs use the same weights.
   - The plain `deepseek-v4.1-flash` Ollama tag has a different digest from `:1017` ([tags](https://ollama.com/library/deepseek-v4.1-flash/tags)).
   - The probe tested the plain tag. Run one probe on `:1017` before relying on it.
   - It is the cheapest-output model here after the small tier.
4. **`deepseek-v4-pro:0813` (frontier).** The expensive half of the DeepSeek pair: GA checkpoint, a real paper (arXiv 2606.19348), MIT weights, and the TF id `deepseek-ai/DeepSeek-V4-Pro-0813` at 1.32 / 3.96.
   - About 3.3× the Flash price, so "Flash plus a rewritten harness matches Pro" is a meaningful claim to test.
   - Caveat: Pro and V4.1-Flash have different architectures (V4.1 is a new encoder-decoder family), so this is a vendor pair rather than a pure size pair.
   - One third-party listing says the TF V4-Pro deployment was deactivated ([llmgateway](https://llmgateway.io/models/deepseek-v4-pro/nebius)). The TF catalog still lists it; confirm before use.
5. **`glm-5.3-flash` (small).** The cheap half of the GLM pair, on TF at 0.15 / 0.50, which is the cheapest TF output price among the picks. 320B / 18B, MIT.
   - The GLM-5 family report (arXiv 2602.15763) plus detailed Z.ai docs give the rewriter material.
   - The probe shows `none` works on Ollama, although Z.ai says thinking cannot be disabled. Check for reasoning leaking into `content`.
6. **`glm-5.3` (frontier).** The expensive half: 753B, TF 1.40 / 4.40, about 9× Flash's output price. Same docs and report.
   - Risk: the default effort is **max**, and any unsupported effort name (for example `medium`) falls back to max. Map every Downshift level explicitly.
7. **`gemma4:31b` (small, dense).** The only dense model among the picks, with a real technical report (arXiv 2607.02770), Apache-2.0, and Google's documented sampling settings and function-call format.
   - It tests whether harness rewrites help a small dense model that does not think by default.
   - Weaknesses: no partner model on Ollama Cloud (the cloud only has 31b); not on TF (price from the OpenRouter median); thinking is boolean only, so every effort level means the same "on".

**Not picked:**

| Model | Why not |
|---|---|
| minimax-m3 / m3.1-flash | Same size (~428B / 23B), so not a capability pair; only an attention paper |
| kimi-k2.6 / k3 | K3 costs $15 output; K2.6 has no paper of its own, and TF showed status "error" |
| muse-spark-open | No paper, no partner model; a good backup frontier pick (bare JSON, `none` works) |
| beam | No paper yet; `none` ignored; price will change when the free period ends |
| mistral-large-4 | `none` returns 500, no paper, not on TF |
| mistral-large-3 | No thinking; returns prose for JSON |
| minimax-m2.7 | Deprecated, non-commercial license, `none` ignored |
| glm-5.2 | Superseded by 5.3 on the same base |
| clef | Not a chat model |

## 4. YAML blocks for `sdk/downshift/models.yaml`

**Per-model reasoning maps are not supported yet.** `ProviderInfo.reasoning` in `sdk/downshift/pricing.py` is per provider, and the current Ollama map sends `reasoning_effort: none` for "off".
- That map is wrong for gpt-oss, where `none` is ignored.
- It is risky for GLM, where unknown names fall back to max.
- The `# reasoning (proposed)` lines below are YAML comments, so they are safe to paste. They take effect only after `pricing.py` gains a per-model override.

`ModelInfo.cost()` ignores `cached_input` today.

```yaml
  # Price: OpenRouter median of 10 endpoints (not on Token Factory; OpenAI has no API price).
  # https://openrouter.ai/api/v1/models/openai/gpt-oss-20b/endpoints, checked 2026-10-29
  gpt-oss-20b:
    display: gpt-oss 20B
    vendor: OpenAI
    tier: small
    size: 20.9B total / 3.6B active, MoE (alternating banded-window and dense attention)
    context: 131072
    price_per_1m: { input: 0.03, output: 0.145 }
    ids:
      ollama: gpt-oss:20b
      ollama-local: gpt-oss:20b
    # reasoning (proposed, ollama): off -> { reasoning_effort: low }  ("none" is ignored); on -> {} (= medium)

  # Price: Token Factory list price. https://tokenfactory.nebius.com/model-catalog.md, checked 2026-10-29
  gpt-oss-120b:
    display: gpt-oss 120B
    vendor: OpenAI
    tier: mid
    size: 116.8B total / 5.1B active, MoE (alternating banded-window and dense attention)
    context: 131072
    price_per_1m: { input: 0.15, output: 0.60, cached_input: 0.10 }
    ids:
      tokenfactory: openai/gpt-oss-120b
      ollama: gpt-oss:120b
      ollama-local: gpt-oss:120b
    # reasoning (proposed, ollama): off -> { reasoning_effort: low }  ("none" is ignored); on -> {} (= medium)

  # Price: OpenRouter median of 16 endpoints (not served for inference on Token Factory; no paid Google API price).
  # https://openrouter.ai/api/v1/models/google/gemma-4-31b-it/endpoints, checked 2026-10-29
  gemma-4-31b:
    display: Gemma 4 31B
    vendor: Google
    tier: small
    size: 30.7B dense (sliding-window + global attention)
    context: 262144
    price_per_1m: { input: 0.145, output: 0.40 }
    ids:
      ollama: gemma4:31b
      ollama-local: gemma4:31b
    # reasoning (proposed, ollama): off -> {} (no thinking by default); on/low/medium/high -> { reasoning_effort: high } (boolean: all levels = on)

  # Price: Token Factory list price. https://tokenfactory.nebius.com/model-catalog.md, checked 2026-10-29
  glm-5.3-flash:
    display: GLM-5.3 Flash
    vendor: Z.ai
    tier: small
    size: 320B total / 18B active, MoE (hybrid sparse + linear attention)
    context: 1024000
    price_per_1m: { input: 0.15, output: 0.50, cached_input: 0.03 }
    ids:
      tokenfactory: zai-org/GLM-5.3-Flash
      ollama: glm-5.3-flash
    # reasoning (proposed, ollama): levels low/high/max, default max. off -> { reasoning_effort: none }; on -> { reasoning_effort: high }; medium -> { reasoning_effort: high }

  # Price: Token Factory list price. https://tokenfactory.nebius.com/model-catalog.md, checked 2026-10-29
  glm-5.3:
    display: GLM-5.3
    vendor: Z.ai
    tier: frontier
    size: 753B total / ~40B active (third-party figure), MoE with sparse attention
    context: 1024000
    price_per_1m: { input: 1.40, output: 4.40, cached_input: 0.26 }
    ids:
      tokenfactory: zai-org/GLM-5.3
      ollama: glm-5.3
    # reasoning (proposed, ollama): levels low/high/max, default max. off -> { reasoning_effort: none }; on -> { reasoning_effort: high }; medium -> { reasoning_effort: high }

  # Price: Token Factory list price. https://tokenfactory.nebius.com/model-catalog.md, checked 2026-10-29
  deepseek-v4.1-flash:
    display: DeepSeek V4.1 Flash (1017)
    vendor: DeepSeek
    tier: mid
    size: 552B backbone (763B incl. Engram memory) / ~8B prefill, ~16B decode active, MoE encoder-decoder
    context: 1048576
    price_per_1m: { input: 0.30, output: 1.20, cached_input: 0.006 }
    ids:
      tokenfactory: deepseek-ai/DeepSeek-V4.1-Flash-1017
      ollama: deepseek-v4.1-flash:1017
    # reasoning (proposed, ollama): levels low/high/max. off -> { reasoning_effort: none }; medium -> { reasoning_effort: high }

  # Price: Token Factory list price. https://tokenfactory.nebius.com/model-catalog.md, checked 2026-10-29
  deepseek-v4-pro:
    display: DeepSeek V4 Pro (0813)
    vendor: DeepSeek
    tier: frontier
    size: 1.6T total / 49B active (preview card; 0813 card lists 1.7T), MoE with CSA+HCA hybrid attention
    context: 1000000
    price_per_1m: { input: 1.32, output: 3.96, cached_input: 0.04 }
    ids:
      tokenfactory: deepseek-ai/DeepSeek-V4-Pro-0813
      ollama: deepseek-v4-pro:0813
    # reasoning (proposed, ollama): levels low/high/max. off -> { reasoning_effort: none }; medium -> { reasoning_effort: high }
```

Notes on the blocks:
- **GLM context:** 1,024,000 is the TF value; Z.ai says "1M".
- **DeepSeek V4 Pro context:** TF lists 979K, and DeepSeek and Ollama say 1M.
- **Token Factory reasoning control:** whether TF's vLLM `chat_template_kwargs: {enable_thinking: false}` turns thinking off for these non-NVIDIA models is unverified. DeepSeek and Kimi use different template flags.

## 5. Harness writing guides

### gpt-oss:20b and gpt-oss:120b
- **Sampling:** temperature 1.0, top_p 1.0 ([repo](https://github.com/openai/gpt-oss)).
- **Reasoning effort:** low/medium/high, set as `Reasoning: <level>` in the system prompt or through `reasoning_effort`; default medium ([HF](https://huggingface.co/openai/gpt-oss-120b)).
  - It cannot be turned off. Probe: `none` is ignored and `low` shortens reasoning.
- **Harmony format:** required. Tool calls go on the `commentary` channel and the final answer on `final`. Ollama converts it to OpenAI `tool_calls` on the server side ([harmony](https://developers.openai.com/cookbook/articles/openai-harmony)).
- **Reasoning across tool calls:** pass it back after tool calls; drop it only after a final answer (same source).
  - Ollama has been reported to lose `reasoning` after tool calls ([#12158](https://github.com/ollama/ollama/issues/12158); old issue, current status unverified).
- **Known weaknesses:** high SimpleQA hallucination (0.78 for 120b, 0.91 for 20b) and weaker instruction-hierarchy following than o4-mini ([card](https://arxiv.org/abs/2508.10925)). Prompts should ground answers in tool output.
- **No `tool_choice` on Ollama** ([docs](https://docs.ollama.com/api/openai-compatibility)). To force a tool, say so in the prompt.
- **JSON-schema output:** bare JSON from 20b (probe). The probe's list of bare-JSON models does not include 120b, so expect fences and strip them.

### gemma4:31b
- **Sampling:** temperature 1.0, top_p 0.95, top_k 64 ([card](https://ai.google.dev/gemma/docs/core/model_card_4)). Ollama `/v1` does not list `top_k`.
- **Thinking:** off unless `<|think|>` starts the system prompt (or `enable_thinking=True` is set). It is boolean, with no levels.
  - Probe: off by default, and any effort such as `low` turns it on.
  - The 31B model still emits an empty thought block when thinking is off ([HF](https://huggingface.co/google/gemma-4-31B-it)).
- **History:** drop earlier thoughts from history, except on tool-call turns, where they should be kept (HF card).
- **Tool calls:** native `<|tool_call>call:NAME{...}<tool_call|>` format, with strings wrapped in `<|"|>`. Ollama parses it ([docs](https://ai.google.dev/gemma/docs/capabilities/text/function-calling-gemma4)). Keep tool schemas simple.
- **Images:** put images before text ([card](https://ai.google.dev/gemma/docs/core/model_card_4)).
- **JSON-schema output:** returned inside a ```json fence (probe). Strip fences or give an explicit "raw JSON only" instruction.
- **Context:** 256K, but a 31B dense model is likely to degrade on long contexts. That is an expectation, not a measured fact.

### glm-5.3-flash and glm-5.3
- **Sampling:** temperature 1.0, top_p 0.95 ([docs](https://docs.z.ai/guides/llm/glm-5.3-flash)). The card's evaluations used top_p 1.0 or 0.95 ([HF](https://huggingface.co/zai-org/GLM-5.3)).
- **Effort:** low/high/max, default max ([docs](https://docs.z.ai/guides/llm/glm-5.3)). Always send an explicit level, because unsupported names such as `medium` fall back to max on Ollama ([docs](https://docs.ollama.com/api/openai-compatibility)).
- **Turning thinking off:** Z.ai says thinking cannot be disabled, but the probe shows `none` turns it off on Ollama.
  - OpenClaw reports that `think:false` on Ollama makes GLM-5.3 put its reasoning inline in `content` ([OpenClaw](https://docs.openclaw.ai/providers/ollama/advanced.md); third party, unverified).
  - Check `content` for reasoning text and compare completion-token counts before trusting "off".
- **Preserved thinking:** send the full, unmodified `reasoning_content` back with tool results ([docs](https://docs.z.ai/guides/capabilities/thinking-mode)). The HF card suggests `clear_thinking=true` for plain chat.
- **Token use:** GLM-5.2 used about 43K output tokens per Artificial Analysis task ([Willison](https://simonwillison.net/2026/jun/17/glm-52/)). Expect 5.3 to be similar (unverified). Budget `max_tokens` generously or lower the effort.
- **Streaming tool calls:** Z.ai recommends `tool_stream=true` (Z.ai API only).
- **JSON-schema output:** fenced (probe).

### deepseek-v4.1-flash:1017 and deepseek-v4-pro:0813
- **Sampling:** temperature 1.0, top_p 1.0 (Flash 1017, [HF](https://huggingface.co/deepseek-ai/DeepSeek-V4.1-Flash-1017)). Pro 0813 recommends top_p 0.95 for agentic work ([HF](https://huggingface.co/deepseek-ai/DeepSeek-V4-Pro-0813)).
  - DeepSeek's own API ignores temperature in thinking mode ([guide](https://api-docs.deepseek.com/guides/thinking_mode)).
- **Effort:** low/high/max; medium maps to high on DeepSeek's API. Think Max uses a special system prompt and needs at least 384K of context (Pro card).
  - Probe: `none` turns thinking off on Ollama for both.
- **Tools:** on DeepSeek's API, `reasoning_content` must be sent back on tool turns or the request fails with 400 ([guide](https://api-docs.deepseek.com/guides/thinking_mode)). Whether Ollama or TF need the same is unverified, so keep the reasoning in history.
- **Chat template:** none in Jinja form; prompts are built with DeepSeek's encoding scripts. Serving stacks parse tool calls themselves (Flash 1017 card).
- **Output length:** very long. The vendor recommends `max_tokens` of at least 256K (Flash) or 384K (Pro at high/max).
  - 1017 was tuned to shorten outputs (vendor claim, [SiliconANGLE](https://siliconangle.com/2026/10/18/deepseek-releases-updated-v4-1-flash-model-it-says-completes-tasks-faster/)).
- **JSON-schema output:** bare JSON (probe).

## Top 10 takeaways

1. **Picks:** gpt-oss:20b, gpt-oss:120b, gemma4:31b, glm-5.3-flash, glm-5.3, deepseek-v4.1-flash:1017 and deepseek-v4-pro:0813. That is three cheap/expensive pairs plus one small dense model.
2. **Token Factory coverage:** TF serves 5 of the 7 picks with exact ids. gpt-oss:20b and gemma4:31b are priced from OpenRouter medians.
3. **Ollama Pro credits:** Pro is $20/mo with **$60 of included usage drawn at per-token prices** and **3 concurrent requests**. Ollama runs are not free and need their own budget alongside the $15 TF limit.
4. **"Off" is not uniform:**
   - gpt-oss, beam and minimax-m2.7 ignore `none`.
   - mistral-large-4 returns 500 on it.
   - gemma4 needs no field to be off.
   - GLM-5.3, Kimi K3/K2.7, M3.1-Flash and Muse accept `none` on Ollama although their vendors say thinking cannot be disabled. Confirm with completion-token counts and a look at `content`.
5. **Unknown effort names fall back silently:** on Ollama they resolve to the model default, which is **max** for GLM-5.3 and Kimi K3 and **xhigh** for Muse. Downshift needs per-model reasoning maps; `pricing.py` only has per-provider maps.
6. **JSON is not guaranteed on Ollama Cloud.** Its docs say cloud does not support structured outputs. Only DeepSeek, gpt-oss:20b, MiniMax M3/M3.1, Muse, Beam and Nemotron return bare JSON. Harnesses must strip code fences.
7. **No `tool_choice` or logprobs on ollama.com/v1.** A harness cannot force a tool call through the API.
8. **Papers:** real technical papers exist for DeepSeek V4/V4.1, Gemma 4, Kimi K3 and the GLM-5 and MiniMax-M2 families. gpt-oss has a model card on arXiv. Beam, Muse, Mistral Large 3/4, Clef and Kimi K2.7 have no paper.
9. **Pin dated snapshots** (`deepseek-v4.1-flash:1017`, `deepseek-v4-pro:0813`) so the Ollama and TF runs use the same weights. The plain Flash tag has a different digest.
10. **Exclusions and caveats:**
    - Exclude clef (not a chat model).
    - Treat Ollama's Nemotron Super/Ultra price rows as errors.
    - TF's K2.6 and K2.7-Code showed status "error".
    - V4-Pro on TF may have been deactivated (third-party claim); recheck `/api/public/models_info` before running.
