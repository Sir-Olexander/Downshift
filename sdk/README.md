# downshift (SDK)

A thin Python package that records your agent's runs and loads its harness config. It wraps an
OpenAI-compatible client, so the only code change is where you create the client and where you call tools.

```python
from downshift import Downshift

ds = Downshift(api_key="ds_dev", endpoint="http://localhost:8000", project="research-agent")
harness = ds.load_harness("harness.yaml")          # system prompt, tools, steps, model per step

with ds.run(task_id="q001", input=question, harness=harness) as run:
    res = run.chat("search", messages, tools=tool_defs)          # model call, recorded
    hits = run.tool("web_search", {"query": q}, lambda: search(q))  # tool call, recorded
    run.finish(answer=text, sources=urls)                        # final answer + cost
```

What gets recorded per run: every model call (messages, model, tokens in/out, latency, cost from the
price table), every tool call (name, arguments, result, latency), the final answer and sources.
Runs are POSTed to the backend with the API key; if it is unreachable they are spooled to
`.downshift/spool/` and can be resent with `HttpTransport.flush()`. Set `DOWNSHIFT_OFFLINE_DIR` to
write JSON files instead.

## Provider layer

Every model call goes through `downshift.LLM`, an OpenAI-compatible client configured from
`models.yaml`: canonical model IDs (`nemotron-3-nano`, `nemotron-3-super`, `nemotron-3-ultra`),
Token Factory list prices, and the provider-specific IDs for Nebius Token Factory, Ollama Cloud,
local Ollama and OpenAI. Pick a provider with `DOWNSHIFT_PROVIDER`, or let it choose the first one
with a key. A harness `reasoning: off` is translated per provider (Ollama: `reasoning_effort: none`).
Concurrent calls are capped per process by `DOWNSHIFT_MAX_CONCURRENT_CALLS` (default 3).

## Replay

`ds.replay(recorded=run_record, harness=new_harness)` returns a run whose `tool()` serves recorded
results when the call matches (same URL, or a search query with enough word overlap) and runs the
tool live otherwise. Each tool event says whether it was `recorded` or `live`. Recorded hits keep
their original latency, so replay latencies stay comparable with the baseline.

## Harness file

```yaml
name: research-agent
version: 1
defaults: { model: nemotron-3-ultra, temperature: 0.2, max_tokens: 1200 }
system_prompt: |
  You are a careful research assistant...
tools:
  web_search: { description: Search the web... }
  read_page: { description: Fetch the readable text of a page... }
steps:
  - { id: plan, kind: plan, max_tokens: 400, prompt: "..." }
  - { id: search, kind: search, max_tool_calls: 6, prompt: "..." }
  - { id: synthesize, kind: synthesize, model: nemotron-3-ultra, prompt: "..." }
```

`Harness.load()` validates the file (unknown fields are rejected, so typos are caught), and
`harness.params(step)` merges step settings with the defaults.
