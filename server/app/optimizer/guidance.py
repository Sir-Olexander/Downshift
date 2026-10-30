"""What the rewriter knows about each target model.

The notes come from the models' technical reports, model cards and serving docs, not from a live web
search. Sources, with the full per-model guides, are in docs/research/nemotron-3-model-guides.md and
docs/research/ollama-cloud-models.md; the switch behaviour per provider was checked against the live
endpoints with `python -m downshift.probe` (docs/research/ollama-cloud-probe.md). A live lookup is used
only when a real search provider (Tavily) is configured: the keyless Wikipedia fallback returned the
pages "Nemotron", "Nvidia" and "List of free and open-source software packages", which helped nothing.
"""

from __future__ import annotations

from typing import Any

from downshift import ModelTable

# Facts only, each traceable to the research notes above. Keep every entry short enough to sit in the
# rewrite prompt next to the harness; the rewriter needs the rules, not the benchmark tables.
MODEL_NOTES: dict[str, str] = {
    "nemotron-3-nano": (
        "Nemotron 3 Nano (30B total / 3B active, hybrid Mamba-Transformer MoE, 256k context; technical report "
        "arXiv:2512.20848). Thinking is on or off only (the chat template's enable_thinking); there is no low, "
        "medium or high. Thinking off is a real quality loss on this model, not a free saving: only about 10% of "
        "its post-training data was non-reasoning, and independent benchmarks fall sharply with thinking off "
        "(tau2-bench 41 -> 25, IFBench 71 -> 38). Keep thinking ON for every step that calls tools or loops; use "
        "off only for a step with no tool call and a short, pinned output format. Tool calls go through the API "
        "tools field: never show a tool call as text in a prompt or few-shot, the model copies the text and stops "
        "calling tools. Few-shot examples are plain chat turns: show only the final-answer format. With thinking "
        "on, Nano tends to report a result in prose instead of the container the agent's code parses; end the "
        "system prompt with one explicit closing rule for the final message (for example: 'your final message "
        "must contain the complete SQL in one ```sql block; never answer with the values in prose only'). "
        "Sampling (model card): temperature 0.6, top_p 0.95 for tool calling; 1.0 / 1.0 for pure reasoning. "
        "Thinking tokens count against max_tokens: with thinking on leave max_tokens unset or at 8000 or more "
        "(NVIDIA uses about 10,000); 2000 truncates. Enforce tool budgets in code and truncate large tool outputs. "
        "Weak at long agent loops, multi-turn instruction following and long-context reasoning; strong at math, "
        "code, short instructions and JSON-schema output with thinking on. Never put the literal strings /think "
        "or /no_think in a prompt (Ollama's renderer acts on them)."
    ),
    "nemotron-3-super": (
        "Nemotron 3 Super (120B total / 12B active, hybrid MoE, 256k context; technical report arXiv:2604.12374). "
        "Thinking on or off, plus a low-effort mode ('significantly fewer reasoning tokens'; reasoning: low on "
        "Token Factory). For cheap steps prefer low over off: only 3% of its post-training data was "
        "reasoning-off and there are no published reasoning-off agentic scores. Sampling (model card): "
        "temperature 1.0, top_p 0.95 for every task, tool calling included. max_tokens: NVIDIA uses 16000 (32000 "
        "for coding agents); thinking counts against it. Same tool-call and few-shot rules as Nano. Strong at long "
        "context and tool use (tau2-bench 68 against Ultra's 83) and close to Ultra on well-specified tasks; "
        "weaker on hard multi-step agent loops. It can claim tool calls it never made, so count calls in code. "
        "Post-trained on 96.5k text-to-SQL records."
    ),
    "nemotron-3-ultra": (
        "Nemotron 3 Ultra (550B total / 55B active, 1M context; technical report arXiv:2606.15007). Thinking on or "
        "off, plus a medium-effort mode (about 2.5x fewer reasoning tokens for about 7% lower benchmark index; "
        "reasoning: medium on Token Factory). Reasoning-off is a trained mode here, unlike on Nano. Sampling: "
        "temperature 1.0, top_p 0.95; max_tokens 16000. The strongest of the family (tau2-bench 83, long-context "
        "reasoning 79, low hallucination). Expensive: keep it only for steps that need it."
    ),
    "gpt-oss-20b": (
        "gpt-oss 20B (OpenAI, Apache-2.0; 21B total / 3.6B active, 128k context; model card arXiv:2508.10925). "
        "Reasoning effort low, medium or high, default medium; it cannot be switched off (reasoning: off maps to "
        "low here). Sampling: temperature 1.0, top_p 1.0. Harmony chat format: tool calls and the final answer "
        "travel on separate channels that the server converts; keep the returned reasoning in the history across "
        "tool calls. High hallucination rate on open questions (SimpleQA 0.91): ground answers in tool output. No "
        "tool_choice on Ollama Cloud: say in the prompt when a tool must be called. JSON-schema output may come "
        "back fenced; strip fences."
    ),
    "gpt-oss-120b": (
        "gpt-oss 120B (OpenAI, Apache-2.0; 117B total / 5.1B active, 128k context; model card arXiv:2508.10925). "
        "Reasoning effort low, medium or high, default medium; it cannot be switched off (reasoning: off maps to "
        "low here). Sampling: temperature 1.0, top_p 1.0. Harmony chat format: keep the returned reasoning in the "
        "history across tool calls. Hallucinates on open questions (SimpleQA 0.78): ground answers in tool "
        "output. No tool_choice on Ollama Cloud. JSON-schema output comes back in a ```json fence; strip it."
    ),
    "gemma-4-31b": (
        "Gemma 4 31B (Google; dense, 256k context; technical report arXiv:2607.02770). Does not think by default; "
        "reasoning: on switches its thinking mode on (boolean, no levels). Sampling (model card): temperature "
        "1.0, top_p 0.95, top_k 64. Its native tool-call format is parsed by the server; keep tool schemas "
        "simple. Drop earlier thoughts from the history except on tool-call turns. JSON-schema output comes "
        "back in a ```json fence: strip it or ask for raw JSON. A 31B dense model: expect weaker long-context "
        "behaviour than the large MoE models."
    ),
    "glm-5.3-flash": (
        "GLM-5.3 Flash (Z.ai; 320B total / 18B active MoE, 1M context; GLM-5 report arXiv:2602.15763). Effort "
        "levels low, high and max with max as the default: always set a level, an unknown name falls back to "
        "max, the most expensive. reasoning: off is honoured on Ollama Cloud (verified by probe) although Z.ai "
        "documents thinking as always on; check the content for inline reasoning before trusting it. Sampling: "
        "temperature 1.0, top_p 0.95. Send reasoning_content back with tool results. Output can be very long at "
        "max effort: budget max_tokens or lower the effort. JSON-schema output comes back fenced."
    ),
    "glm-5.3": (
        "GLM-5.3 (Z.ai; 753B total / about 40B active MoE, 1M context; GLM-5 report arXiv:2602.15763). Effort "
        "levels low, high and max with max as the default: always set a level. reasoning: off is honoured on "
        "Ollama Cloud (verified by probe); check the content for inline reasoning. Sampling: temperature 1.0, "
        "top_p 0.95. Send reasoning_content back with tool results. Very long outputs at max effort (GLM-5.2 "
        "averaged about 43k output tokens per hard task): budget max_tokens or lower the effort. JSON-schema "
        "output comes back fenced."
    ),
    "deepseek-v4.1-flash": (
        "DeepSeek V4.1 Flash, snapshot 1017 (MoE, about 8B active for prefill and 16B for decode, 1M context; "
        "report arXiv:2609.19969). Effort low, high or max (medium maps to high). reasoning: off is honoured on "
        "Ollama Cloud (probe). Sampling: temperature 1.0, top_p 1.0. Keep reasoning_content in the history on "
        "tool turns (DeepSeek's own API rejects requests without it). Outputs can be very long: set a generous "
        "max_tokens or lower the effort. Returns bare JSON for json_schema requests."
    ),
    "deepseek-v4-pro": (
        "DeepSeek V4 Pro, snapshot 0813 (MoE, 1.6T total / 49B active, 1M context; report arXiv:2606.19348). "
        "Effort low, high or max (medium maps to high). reasoning: off is honoured on Ollama Cloud (probe). "
        "Sampling: temperature 1.0, top_p 0.95 for agentic work. Keep reasoning_content in the history on tool "
        "turns. Outputs can be very long: set a generous max_tokens or lower the effort. Returns bare JSON for "
        "json_schema requests."
    ),
}

GENERAL_TIPS = (
    "Rules that hold across these models. "
    "1. Do not switch thinking off on a step that calls tools or loops unless the model notes say off is a trained "
    "mode, and never to save cost alone: a cheaper step that fails the task costs more. "
    "2. Thinking tokens count against max_tokens: with thinking on, leave max_tokens unset or generous (8000 or more). "
    "3. Never write a tool call as text anywhere in a prompt or few-shot example; tool calls go through the API. "
    "4. The commonest small-model failure is the final message in the wrong container (prose where the agent's code "
    "expects a code block, JSON or a label). Write one explicit closing rule for the final message and show one "
    "example of that final reply; on custom agents also set the step's final_format so the SDK re-asks once when "
    "the rule is ignored. "
    "5. Short numbered rules and a concrete stop condition beat long prose instructions. "
    "6. Few-shot examples are chat turns the model imitates: show only the final reply, never a skipped step or a "
    "different dialect than the agent's environment uses. "
    "7. A separate verify step without an execution signal rarely helps; prefer rules the agent's code can check. "
    "8. Structured-output (json_schema) requests are not enforced on Ollama Cloud and are unverified on Token "
    "Factory: do not rely on them."
)


def lookup_guidance(tools: Any, model_display: str, max_results: int = 4) -> list[dict[str, Any]]:
    """Live prompting guidance for the target model, only through a real search provider (Tavily).

    With the keyless Wikipedia fallback the results were encyclopedia pages about NVIDIA, so that path
    is skipped: the curated MODEL_NOTES are the guidance."""
    if getattr(tools, "provider", "") != "tavily":
        return []
    queries = [
        f"{model_display} prompting guide best practices tool calling reasoning",
        f"{model_display} model card recommended sampling thinking mode",
    ]
    for q in queries:
        try:
            res = tools.web_search(q, max_results=max_results)
        except Exception:
            continue
        results = (res or {}).get("results") or []
        if results:
            return [{"title": r.get("title", ""), "url": r.get("url", ""), "snippet": (r.get("snippet") or "")[:400], "provider": res.get("provider"), "query": q} for r in results]
    return []


def guidance_text(target_models: list[str], table: ModelTable, search_results: list[dict[str, Any]]) -> str:
    parts = []
    for m in target_models:
        info = table.get(m)
        price = f"${info.input_per_1m}/M input, ${info.output_per_1m}/M output" if info.input_per_1m is not None else "price unknown"
        parts.append(f"{m} ({info.display}, {price}): {MODEL_NOTES.get(m, 'no notes for this model; use the general rules and the recorded runs.')}")
    parts.append(GENERAL_TIPS)
    if search_results:
        parts.append("Web lookup for prompting guidance:")
        for r in search_results:
            parts.append(f"- {r.get('title')} ({r.get('url')}): {r.get('snippet')}")
    return "\n".join(parts)
