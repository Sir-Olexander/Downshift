"""Probe what a provider's models actually support: tool calling, the reasoning switch, JSON schema output.

Before Downshift lets the optimizer set `reasoning: off` or rely on tool calls for a model, this checks
each control against the live endpoint with tiny requests and reports what happened (tokens, tool calls,
errors). Nothing here reads or prints API key values; the key comes from the provider's env variable.

    python -m downshift.probe --provider ollama --models gpt-oss:20b,glm-5.3-flash
    python -m downshift.probe --provider ollama --all            # every model the endpoint lists
    python -m downshift.probe --provider tokenfactory --models nvidia/NVIDIA-Nemotron-3-Nano-30B-A3B
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Any

import openai

from .pricing import default_table

TOOL = {
    "type": "function",
    "function": {
        "name": "get_weather",
        "description": "Current weather for a city.",
        "parameters": {"type": "object", "properties": {"city": {"type": "string"}}, "required": ["city"]},
    },
}
TOOL_MESSAGES = [
    {"role": "system", "content": "You are a helpful assistant. Use the tools when they help."},
    {"role": "user", "content": "What is the weather in Paris right now? Call the tool."},
]
PLAIN_MESSAGES = [{"role": "user", "content": "In one short sentence: why is the sky blue?"}]
SCHEMA = {
    "type": "json_schema",
    "json_schema": {
        "name": "answer",
        "schema": {"type": "object", "properties": {"city": {"type": "string"}, "country": {"type": "string"}}, "required": ["city", "country"], "additionalProperties": False},
    },
}
JSON_MESSAGES = [{"role": "user", "content": "Give the capital of France as JSON with keys city and country."}]


def _client(provider: str, timeout: float) -> tuple[openai.OpenAI, str]:
    p = default_table().provider(provider)
    key = p.api_key() or ("ollama" if p.api_key_optional else None)
    if not key:
        sys.exit(f"no key for provider {provider}: set {p.api_key_env}")
    return openai.OpenAI(base_url=p.base_url, api_key=key, timeout=timeout, max_retries=1), p.base_url


def _call(client: openai.OpenAI, model: str, messages: list[dict[str, Any]], *, tools: list | None = None, extra: dict | None = None, response_format: dict | None = None, max_tokens: int = 600) -> dict[str, Any]:
    kwargs: dict[str, Any] = {"model": model, "messages": messages, "max_tokens": max_tokens}
    if tools:
        kwargs["tools"] = tools
    if response_format:
        kwargs["response_format"] = response_format
    if extra:
        kwargs["extra_body"] = extra
    t0 = time.perf_counter()
    try:
        r = client.chat.completions.create(**kwargs)
    except Exception as e:  # report, never raise: the point is to see what each model does
        return {"error": f"{type(e).__name__}: {str(e)[:160]}", "latency_s": round(time.perf_counter() - t0, 1)}
    ch = r.choices[0]
    m = ch.message
    extra_fields = getattr(m, "model_extra", None) or {}
    reasoning = extra_fields.get("reasoning") or extra_fields.get("reasoning_content") or ""
    u = getattr(r, "usage", None)
    return {
        "latency_s": round(time.perf_counter() - t0, 1),
        "finish": ch.finish_reason,
        "tool_calls": [tc.function.name for tc in (m.tool_calls or [])],
        "content": (m.content or "")[:120].replace("\n", " "),
        "content_full": m.content or "",
        "reasoning_chars": len(reasoning) if isinstance(reasoning, str) else 0,
        "tokens_in": int(getattr(u, "prompt_tokens", 0) or 0),
        "tokens_out": int(getattr(u, "completion_tokens", 0) or 0),
    }


def probe_model(client: openai.OpenAI, model: str) -> dict[str, Any]:
    out: dict[str, Any] = {"model": model}
    out["tools_default"] = _call(client, model, TOOL_MESSAGES, tools=[TOOL])
    out["tools_reasoning_none"] = _call(client, model, TOOL_MESSAGES, tools=[TOOL], extra={"reasoning_effort": "none"})
    out["plain_default"] = _call(client, model, PLAIN_MESSAGES)
    out["plain_reasoning_none"] = _call(client, model, PLAIN_MESSAGES, extra={"reasoning_effort": "none"})
    out["plain_reasoning_low"] = _call(client, model, PLAIN_MESSAGES, extra={"reasoning_effort": "low"})
    out["json_schema"] = _call(client, model, JSON_MESSAGES, response_format=SCHEMA)
    js = out["json_schema"]
    if "error" not in js:
        try:
            v = json.loads(js.get("content_full") or "")
            js["valid_json"] = isinstance(v, dict) and "city" in v
        except Exception:
            js["valid_json"] = None
    return out


def _fmt(r: dict[str, Any]) -> str:
    if "error" in r:
        return f"ERR {r['error'][:70]}"
    tc = ",".join(r.get("tool_calls") or []) or "-"
    rs = f" r{r['reasoning_chars']}" if r.get("reasoning_chars") else ""
    return f"out={r['tokens_out']}{rs} tc={tc} {r['finish']} {r['latency_s']}s"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--provider", default="ollama")
    ap.add_argument("--models", default="", help="comma-separated provider model ids")
    ap.add_argument("--all", action="store_true", help="probe every model the endpoint lists")
    ap.add_argument("--exclude", default="", help="comma-separated ids to skip")
    ap.add_argument("--workers", type=int, default=2)
    ap.add_argument("--timeout", type=float, default=120.0)
    ap.add_argument("--json", default="", help="also write the full results to this file")
    args = ap.parse_args(argv)
    client, base_url = _client(args.provider, args.timeout)
    models = [m for m in args.models.split(",") if m.strip()]
    if args.all:
        models = sorted(m.id for m in client.models.list().data)
    skip = {m for m in args.exclude.split(",") if m.strip()}
    models = [m for m in models if m not in skip]
    if not models:
        sys.exit("no models to probe (use --models or --all)")
    print(f"probing {len(models)} models on {base_url} ({args.workers} at a time)", file=sys.stderr)
    with ThreadPoolExecutor(max_workers=max(1, args.workers)) as pool:
        results = list(pool.map(lambda m: probe_model(client, m), models))
    print("| model | tools, default | tools, reasoning_effort=none | plain, default | plain, none | plain, low | json_schema |")
    print("|---|---|---|---|---|---|---|")
    for r in results:
        js = r["json_schema"]
        js_s = f"ERR {js['error'][:50]}" if "error" in js else f"out={js['tokens_out']} {js['finish']} {js['content'][:40]!r}"
        print(f"| {r['model']} | {_fmt(r['tools_default'])} | {_fmt(r['tools_reasoning_none'])} | {_fmt(r['plain_default'])} | {_fmt(r['plain_reasoning_none'])} | {_fmt(r['plain_reasoning_low'])} | {js_s} |")
    if args.json:
        with open(args.json, "w", encoding="utf-8") as f:
            json.dump(results, f, indent=1, ensure_ascii=False)
    return 0


if __name__ == "__main__":
    sys.exit(main())
