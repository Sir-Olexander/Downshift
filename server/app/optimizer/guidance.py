"""What the rewriter knows about each target model: static notes plus a live lookup of prompting guidance."""

from __future__ import annotations

from typing import Any

from downshift import ModelTable

# Static notes, from NVIDIA's model cards and the Unsloth Nemotron 3 guides (checked 2026-10-26).
MODEL_NOTES: dict[str, str] = {
    "nemotron-3-nano": (
        "Nemotron 3 Nano (30B total, ~3B active; hybrid Mamba-Transformer MoE). Strong for its cost on tool "
        "use, retrieval and short structured outputs; weaker at long multi-part synthesis and at staying "
        "faithful to many sources. Thinking can be switched off (reasoning: off), which makes short mechanical "
        "steps much cheaper and faster. Keep instructions short, explicit and ordered; give the exact output "
        "shape; keep tool loops tight (few calls, concrete stop rule); one task per step. Recommended sampling "
        "for tool calling: temperature 0.6, top_p 0.95 (lower temperature is fine for deterministic steps)."
    ),
    "nemotron-3-super": (
        "Nemotron 3 Super (120B total, ~12B active; hybrid MoE). Good general reasoning, long context and "
        "tool use; close to Ultra on well-specified tasks, less robust on subtle synthesis and on noticing "
        "gaps in evidence. Benefits from explicit structure (what to cover, how to cite, when to stop). "
        "Recommended sampling for tool calling: temperature 0.6, top_p 0.95; thinking on helps synthesis, off "
        "is fine for planning and search steps."
    ),
    "nemotron-3-ultra": (
        "Nemotron 3 Ultra (550B total, ~55B active). The strongest model in the family: complex reasoning, "
        "multi-step research, long context. Expensive; use it only where quality depends on it."
    ),
}

GENERAL_TIPS = (
    "Reasoning (thinking) tokens count against max_tokens on these endpoints: a step with reasoning on needs "
    "a generous max_tokens (2000+ for synthesis) or it returns an empty answer; reasoning off makes short "
    "steps cheap and reliable. "
    "Techniques that usually help smaller models: shorter system prompts with numbered rules; an explicit "
    "output template; one or two few-shot examples of the exact output; a hard cap on tool calls with a "
    "clear stop condition; a separate cheap 'verify' step that checks citations and completeness and triggers "
    "one rewrite; moving reasoning off for mechanical steps and on for synthesis."
)


def lookup_guidance(tools: Any, model_display: str, max_results: int = 4) -> list[dict[str, Any]]:
    """Look up prompting guidance for the target model (Tavily when configured, Wikipedia otherwise).

    Falls back to broader queries, since an encyclopedia rarely has a page for a prompting guide."""
    queries = [
        f"{model_display} prompting guide best practices tool calling reasoning",
        f"{model_display} language model",
        "Nemotron NVIDIA language model",
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
        parts.append(f"{m} ({info.display}, {price}): {MODEL_NOTES.get(m, '')}")
    parts.append(GENERAL_TIPS)
    if search_results:
        parts.append("Web lookup for prompting guidance:")
        for r in search_results:
            parts.append(f"- {r.get('title')} ({r.get('url')}): {r.get('snippet')}")
    return "\n".join(parts)
