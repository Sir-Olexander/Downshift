# Demo agent: research-agent

A small research agent that answers questions by searching the web, reading pages and writing a short,
sourced answer. It stands in for "the user's agent": it uses the Downshift SDK to record runs, and its
whole behaviour lives in `harness.yaml`, which is the file the optimizer rewrites and the PR changes.

- `harness.yaml` – system prompt, tool descriptions, step plan, model and parameters per step
- `questions.json` – 42 research questions used to record baseline runs
- `research_agent/agent.py` – interprets the step plan (`plan`, `search`, `synthesize`, `verify`)
- `research_agent/tools.py` – read-only tools: `web_search` and `read_page` (Tavily, or Wikipedia without a key)
- `record_baseline.py` – records a run per question with the SDK (shared logic in `research_agent/recorder.py`)

Four more agents built on this runtime live in `../demo_agents/`.

```bash
uv run python demo_agent/record_baseline.py --limit 3
```

Tools are read-only, so replaying a run on another model is safe: matching tool calls are served from the
recording and anything new runs live.
