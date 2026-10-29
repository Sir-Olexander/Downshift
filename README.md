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
                                         │                (the built-in research agent, or your own agent's code through its adapter)
                                         ├─ 5. score      the task's correct answer when it has one (the agent's own grader);
                                         │                otherwise auto checks + Ultra judge, blind pairwise, random order
                                         ├─ 6. report     success, quality, cost/run, latency vs baseline (held-out only)
                                         └─ 7. PR         new harness.yaml + results table on the agent's repo
```

Targets: **Nemotron 3 Super**, **Nemotron 3 Nano**, and a **per-step mix** (cheapest model that can
handle each step). For Super and Nano the optimizer first tries the **model swap alone** (prompts
unchanged); then two rewrite rounds (propose → replay → score), keeping whichever candidate scores best,
so a rewrite is only kept if it beats the plain swap. Capped by a budget.

The key design choice is the **harness config**: the agent's system prompt, tool descriptions, step
plan and per-step model and parameters live in `demo_agent/harness.yaml`, not in Python. The SDK
loads it at runtime, the optimizer writes new versions, and the PR changes only this file.

## Demo results

_Generated from the shipped optimization with `uv run python -m app.report readme`; the UI has the live table._

<!-- results:start -->
**Task success 100% → 94%, cost down 94%** · Nemotron 3 Nano keeps quality within the bar at 94% lower cost per run.

| Option | Task success | Quality (0-100) | Cost / run | Latency | vs baseline |
|---|---|---|---|---|---|
| Baseline (Nemotron 3 Ultra) | 100% | 98.4 | $0.0301 | 134 s | — |
| Nemotron 3 Super | 94% | 94.5 | $0.0081 | 37 s | success -6 pp, quality -4, cost -73% |
| Nemotron 3 Nano **(this PR)** | 94% | 93.7 | $0.0019 | 58 s | success -6 pp, quality -5, cost -94% |
| Per-step mix | 100% | 95.7 | $0.0148 | 118 s | success +0 pp, quality -3, cost -51% |

Held-out test set: 17 runs the optimizer never saw (25 runs were used to optimize). Judge: nemotron-3-ultra, blind pairwise in random order. Models served via Ollama Cloud, search via wikipedia. Optimization spend: $1.14.

What held up and what fell short:
- Nemotron 3 Super: within the bar (-6 pp success, -4 quality, -73% cost).
- Nemotron 3 Nano: within the bar (-6 pp success, -5 quality, -94% cost).
- Per-step mix: within the bar (+0 pp success, -3 quality, -51% cost).

Step analysis by nemotron-3-nano (share of optimization runs where the step needed a strong model):
- `plan` (plan): 4%
- `search` (search): 32%
- `synthesize` (synthesize): 92%

Nemotron 3 Super harness changes: Removed plan step; search step now generates its own queries and stops after 5 tool calls or 3 solid sources. · Set reasoning: "off" and temperature 0.6 for search (cheap, reliable tool use); reasoning: "on" with 3000 max_tokens for synthesis (quality). · Added verify step with retry_on_fail to catch citation/coverage errors; runs with reasoning off for speed. · Added one few-shot example each for search and synthesize to lock output format.
Nemotron 3 Nano harness changes: Set all steps to nemotron-3-nano; added reasoning: off for plan/search, reasoning: on for synthesize · Added few-shot examples to plan, search, and synthesize for exact output format · Reduced max_tool_calls in search from 6 to 4 with explicit stop rule · Added verify step with retry_on_fail to catch citation errors cheaply
Per-step mix harness changes: Assigned nemotron-3-nano (reasoning off) to plan step: 92% easy, only query generation needed · Assigned nemotron-3-super (reasoning on) to search step: good tool use, handles medium-difficulty retrieval · Kept nemotron-3-ultra (reasoning on) for synthesize: 92% runs need strong model for multi-source synthesis · Added verify step with nemotron-3-nano (reasoning off) to catch citation errors cheaply, retry_on_fail triggers one rewrite

Optimization id `opt_c5bcd27101b5`; open it in the UI for the harness diffs and every replayed run.
<!-- results:end -->

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

# 4. Optimize: from the UI's Run screen (small and rate limited) or in full from the CLI
uv run python -m app.cli optimize --targets super,nano,mix --rounds 2 --sample 10
```

If a run is interrupted (provider outage, usage limit), nothing is lost: every round's harness and every
replay are stored as they happen. `uv run python -m app.cli redo <optimization id> mix` replays only the
held-out tasks that failed or are missing for that option and rebuilds the summary;
`uv run python -m app.cli resummarize <optimization id>` recomputes checks, metrics and the summary from
the stored replays without spending tokens (for example after a fix to the automatic checks).

To try the whole flow on one of the extra demo agents from the UI, follow [docs/try-a-run.md](docs/try-a-run.md).

Tests: `uv run pytest` (SDK, optimizer units, API, a scripted end-to-end optimization).

## Bring your own agent

Downshift can record, replay and optimize an agent it did not build. The agent's folder gets four
small files; the agent's own code is not changed:

| file | what it is |
|---|---|
| `downshift_agent.py` | an `AgentAdapter` (from the SDK) exposed as `agent`: runs one task with the agent's own code, sending model calls through `run.chat` and tool calls through `run.tool`, and grades an output against the task's correct answer (`score`) |
| `harness.yaml` | `runtime: custom`: the agent's prompts, tool descriptions and models, plus a `contract` that says what its code needs from the model. The optimizer may rewrite prompts, examples and model settings, never the steps, tools or contract |
| `tasks.jsonl` | one task per line: `{"id", "input", "expected"}`. With `expected`, runs are graded against the correct answer and no LLM judge is used |
| `downshift.yaml` | which Python runs the agent (its own environment) |

```bash
cd my-agent && uv pip install -e path/to/downshift/sdk     # the SDK, into the agent's own environment
.venv/bin/python -m downshift.runner init-harness           # write the adapter's default harness.yaml
.venv/bin/python -m downshift.runner check                  # adapter, harness and tasks load; no model calls
.venv/bin/python -m downshift.runner record --project my-agent   # baseline runs, graded, sent to the API
```

Register the folder on the Agents screen (or `POST /v1/agents` with the same id), then optimize as
usual. Replays run `python -m downshift.runner replay` in the agent's folder with its own Python, so the
server never imports the agent's code; this needs `DOWNSHIFT_ALLOW_FS=true` and the folder inside
`DOWNSHIFT_AGENTS_ROOT`. Agents whose tools change state set `reuse_tool_results = False` so replays
run every tool live. `examples/text2sql/` is a complete adapter for
[text2sql-framework](https://github.com/Text2SqlAgent/text2sql-framework).

## Repo layout

```
sdk/          Python package `downshift`: harness schema, model table + prices, provider layer, tracing, replay
server/       FastAPI backend: storage (SQLite), optimizer (split, analyze, rewrite, replay, judge), GitHub PR, seed
web/          Next.js UI: agents, onboarding (folder → harness.yaml → baseline runs), Run screen, results, harness diff, Open PR
demo_agent/   The "user's agent": research agent (web_search + read_page), harness.yaml, 42 questions, recorder
demo_agents/  Four more agents on the same runtime: fact-checker, compare-agent, timeline-agent, tutor-agent
examples/     Adapters for agents Downshift did not build (text2sql-framework)
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
  `sdk/downshift/models.yaml`; the Token Factory model IDs were checked against the live model list
  on 2026-10-29.
- **Search.** The demo agent uses Tavily when `TAVILY_API_KEY` is set and falls back to the keyless
  Wikipedia API otherwise. The shipped results were recorded with the Wikipedia fallback.
- **Reasoning.** On Ollama Cloud, `reasoning: off` in a harness maps to `reasoning_effort: "none"`
  (verified: it removes Nemotron's thinking tokens). On Token Factory it maps to
  `chat_template_kwargs.enable_thinking=false` (verified 2026-10-29 on Nano, Super and Ultra).
- **Read the results with the sample size in mind.** The held-out set is 17 runs, so one run is 5.9
  points of task success; Super and Nano each lost exactly one run against the baseline. The bar counts a
  one-run drop as within tolerance, and says so. In blind pairwise judging the baseline was still
  preferred more often than any cheaper option (Nano won 12% and tied 35% of comparisons), so "within the
  bar" means "close", not "as good". The per-step mix kept every run and lost the least quality, at about
  half the cost; Nano is the cheapest option that stayed within the bar.
- **Held-out reporting.** Runs are split 60/40 with a fixed seed. Optimization rounds only replay a
  sample of the 60%; every number in the UI, the README and the PR comes from the 40%.
- **Judge.** Nemotron 3 Ultra compares the baseline and candidate answers blind, in random order,
  with a short rubric (correct, complete, supported, 0–5 each). Task success additionally requires the
  automatic checks: an answer was produced, sources are listed, every cited URL appeared in the tools'
  results, and no errors. A model that invents a source fails that run.
- **An agent we did not build.** text2sql-framework (`examples/text2sql/`), 40 Spider questions graded
  against the gold SQL, 16 held out (optimization `opt_10b7f3486f2d`). Downshift recommended its
  Super harness: 68.8% task success, the same as the Ultra baseline on those tasks, at 72% lower cost per run.
  Fresh runs of the real agent (no replay, two trials) gave Ultra 72%, that Super harness 78% and the
  Nano option 44%, so the decisions held (Super kept, Nano rejected). The point estimates are single
  replays of 16 tasks and moved by up to three tasks (Downshift said 62.5% for Nano). Downshift's Nano
  rewrites scored 12.5-50% on the optimization sample against 62.5% for the plain swap. A diagnostic
  (`docs/research/nano-text2sql-diagnostic.md`) traced the worst of it to a few-shot example that wrote
  tool calls as text, which Nano copied; thinking off alone halves Nano's pass rate but does not break
  its tool calls. With thinking on and one final-reply format rule, the plain Nano swap reached 14/16 on
  the held-out tasks (Ultra: 11-12/16) at about one eighth of Ultra's cost. The optimizer did not find
  that rule by itself; `docs/prove-the-optimizer-plan.md` is the plan to make it.
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
| `NEBIUS_API_KEY` (or `TOKEN_FACTORY_API_KEY`) / `OLLAMA_API_KEY` / `OPENAI_API_KEY` | provider keys; the first configured provider wins |
| `DOWNSHIFT_PROVIDER` | force `tokenfactory`, `ollama`, `ollama-local` or `openai` |
| `TAVILY_API_KEY` | search provider for the demo agent (Wikipedia fallback without it) |
| `DOWNSHIFT_API_KEYS` | keys the SDK may use to send runs (default `ds_dev`) |
| `DOWNSHIFT_DEMO_MODE`, `DOWNSHIFT_MAX_LIVE_PER_HOUR` | keep live optimizations small and rate limited |
| `DOWNSHIFT_ALLOW_FS`, `DOWNSHIFT_AGENTS_ROOT` | let the UI browse agent folders and write their harness.yaml (default on, inside your home folder); turn off on a public deployment |
| `DOWNSHIFT_OPT_ROUNDS`, `DOWNSHIFT_OPT_SAMPLE`, `DOWNSHIFT_OPT_CONCURRENCY`, `DOWNSHIFT_TEST_FRACTION` | optimizer budget |
| `GITHUB_REPO`, `GITHUB_TOKEN`, `GITHUB_BASE_BRANCH`, `GITHUB_HARNESS_PATH` | Open PR |
| `DOWNSHIFT_PUBLIC_WEB_URL` | web URL linked from PR descriptions |
| `API_URL` (web) | where the Next.js server reaches the API |

## License

MIT, see `LICENSE`.
