# Downshift

**Find out whether cheaper Nemotron models can run your agent. Get a pull request, not a hunch.**

A developer adds a thin SDK to their agent, which records real runs. Downshift then checks whether
cheaper Nemotron 3 models can do the same job: an optimizer agent rewrites the agent's harness for
each cheaper model, replays the recorded runs, scores them blind against the original answers, and
shows a clear cost vs quality result with a pull request ready to merge.

> Results in this README come from the precomputed optimization that ships with the demo
> (`server/seed/seed.json.gz`). See [Demo results](#demo-results); numbers are from the held-out test
> set the optimizer never saw.

## How it works

```
 your agent + SDK ──records runs──▶  Downshift API (SQLite)
                                         │
                                         ├─ 1. split      60% optimization set · 40% held-out test set
                                         ├─ 2. analyze    Nemotron 3 Nano labels every recorded step (kind, difficulty)
                                         ├─ 3. rewrite    Nemotron 3 Ultra proposes a harness.yaml per target
                                         ├─ 4. replay     run the agent on the target; matching tool calls come from the recording
                                         ├─ 5. score      auto checks + Ultra judge, blind pairwise, random order
                                         ├─ 6. report     success, quality, cost/run, latency vs baseline (held-out only)
                                         └─ 7. PR         new harness.yaml + results table on the agent's repo
```

Targets: **Nemotron 3 Super**, **Nemotron 3 Nano**, and a **per-step mix** (cheapest model that can
handle each step). Two rounds per target (propose → replay → score → keep the best), capped by a budget.

The key design choice is the **harness config**: the agent's system prompt, tool descriptions, step
plan and per-step model and parameters live in `demo_agent/harness.yaml`, not in Python. The SDK
loads it at runtime, the optimizer writes new versions, and the PR changes only this file.

## Demo results

_Generated from the shipped optimization with `uv run python -m app.report readme`; the UI has the live table._

RESULTS_PLACEHOLDER

## Quickstart

Requirements: Python 3.11+, [uv](https://docs.astral.sh/uv/), Node 22+, and one model provider key.

```bash
cp .env.example .env            # add OLLAMA_API_KEY (Ollama Cloud) or NEBIUS_API_KEY (Token Factory)
uv sync --all-packages          # installs sdk, server and demo_agent into .venv

# 1. API (seeds the precomputed demo results on first start)
uv run uvicorn app.main:app --app-dir server --port 8000

# 2. Web UI
cd web && cp .env.example .env.local && npm install && npm run dev      # http://localhost:3000

# 3. Record your own baseline runs with the SDK (42 research questions on Nemotron 3 Ultra)
uv run python demo_agent/record_baseline.py --concurrency 3

# 4. Optimize: from the UI ("Run optimization", small and rate limited) or in full from the CLI
uv run python -m app.cli optimize --targets super,nano,mix --rounds 2 --sample 10
```

Tests: `uv run pytest` (SDK, optimizer units, API).

## Repo layout

```
sdk/          Python package `downshift`: harness schema, model table + prices, provider layer, tracing, replay
server/       FastAPI backend: storage (SQLite), optimizer (split, analyze, rewrite, replay, judge), GitHub PR, seed
web/          Next.js UI: results, harness diff, run view, Open PR, Run optimization
demo_agent/   The "user's agent": research agent (web_search + read_page), harness.yaml, 42 questions, recorder
docs/         Deployment notes (Nebius Serverless), video script
```

## The honest notes

- **Provider.** Everything was built and measured on **Ollama Cloud** (`ollama.com/v1`) because no
  Token Factory key was available during the build. Every model call goes through one provider
  layer; switching is `NEBIUS_API_KEY` + `DOWNSHIFT_PROVIDER=tokenfactory`. The same three Nemotron 3
  models were used (`nemotron-3-nano:30b`, `nemotron-3-super`, `nemotron-3-ultra`).
- **Prices.** Costs are always computed from recorded token counts at **Nebius Token Factory list
  prices** (Nano $0.06/$0.24, Super $0.30/$0.90, Ultra $1.00/$3.00 per 1M input/output tokens,
  checked 2026-10-26), whichever provider served the call. IDs and prices live in one file,
  `sdk/downshift/models.yaml`; the Token Factory model IDs were read from the public catalog and
  should be verified in the console before a production rollout.
- **Search.** The demo agent uses Tavily when `TAVILY_API_KEY` is set and falls back to the keyless
  Wikipedia API otherwise. The shipped results were recorded with the Wikipedia fallback.
- **Reasoning.** On Ollama Cloud, `reasoning: off` in a harness maps to `reasoning_effort: "none"`
  (verified: it removes Nemotron's thinking tokens). The Token Factory mapping uses the vLLM
  `chat_template_kwargs.enable_thinking=false` convention and is not yet verified.
- **Held-out reporting.** Runs are split 60/40 with a fixed seed. Optimization rounds only replay a
  sample of the 60%; every number in the UI, the README and the PR comes from the 40%.
- **Judge.** Nemotron 3 Ultra compares the baseline and candidate answers blind, in random order,
  with a short rubric (correct, complete, supported, 0–5 each). Task success additionally requires the
  automatic checks: an answer was produced, sources are listed, every cited URL appeared in the tools'
  results, and no errors. A model that invents a source fails that run.
- **Open PR.** Needs `GITHUB_REPO` (owner/name) and a token (`GITHUB_TOKEN`, or a local `gh` login).
  Without them the button shows the exact PR it would open (title, branch, body, file) instead.
- **Deployment.** Dockerfiles and a compose file are included; `docs/deploy-nebius.md` describes the
  Nebius Serverless layout (two Endpoints plus an optional Job). It has not been deployed to Nebius
  yet.
- **Rate limits.** Ollama Cloud rejects more than a few concurrent requests per key and has a per-account
  usage limit ("session usage limit reached"). The SDK caps concurrent model calls per process
  (`DOWNSHIFT_MAX_CONCURRENT_CALLS`, default 3) and, on a 429, waits with backoff for up to
  `DOWNSHIFT_RATE_LIMIT_MAX_WAIT_S` (default 900 s; set it to hours for an unattended optimization) while
  the live log shows that the run is waiting. Recording the 42 baseline runs used about 1M tokens.

## Configuration

| Variable | Purpose |
|---|---|
| `NEBIUS_API_KEY` / `OLLAMA_API_KEY` / `OPENAI_API_KEY` | provider keys; the first configured provider wins |
| `DOWNSHIFT_PROVIDER` | force `tokenfactory`, `ollama`, `ollama-local` or `openai` |
| `TAVILY_API_KEY` | search provider for the demo agent (Wikipedia fallback without it) |
| `DOWNSHIFT_API_KEYS` | keys the SDK may use to send runs (default `ds_dev`) |
| `DOWNSHIFT_DEMO_MODE`, `DOWNSHIFT_MAX_LIVE_PER_HOUR` | keep live optimizations small and rate limited |
| `DOWNSHIFT_OPT_ROUNDS`, `DOWNSHIFT_OPT_SAMPLE`, `DOWNSHIFT_OPT_CONCURRENCY`, `DOWNSHIFT_TEST_FRACTION` | optimizer budget |
| `GITHUB_REPO`, `GITHUB_TOKEN`, `GITHUB_BASE_BRANCH`, `GITHUB_HARNESS_PATH` | Open PR |
| `DOWNSHIFT_PUBLIC_WEB_URL` | web URL linked from PR descriptions |
| `API_URL` (web) | where the Next.js server reaches the API |

## License

MIT, see `LICENSE`.
