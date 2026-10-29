# Downshift: notes for Claude

## Spending limit: $15

The Nebius Token Factory key (`TOKEN_FACTORY_API_KEY`, referenced from `.env` as `NEBIUS_API_KEY`)
has a hard limit of **$15 in total**. Every model call costs real money against it.

- Before anything that calls models in bulk (recording baselines, optimizations, `redo`, test runs
  against the live provider), estimate the cost and keep the total well under $15.
- Prefer the smallest run that answers the question: a few runs, Nano or Super instead of Ultra,
  `reasoning: off` where it is enough, demo mode on for optimizations.
- Never start a full optimization (`app.cli optimize` without demo limits) or re-record all baselines
  without asking the user first.
- Costs are computed from token counts with the prices in `sdk/downshift/models.yaml`; the UI and the
  SQLite database (`server/data/downshift.sqlite3`) show what each run and optimization cost.

## Testing Downshift: stay unbiased and check its claims

Every time Downshift is tested (on our demo agents or anyone else's), do both of these:

- **Analyse the results without bias.** Report what the numbers show, including when Downshift looks
  bad: rewrites that do no better than a plain model swap, differences within noise, small samples,
  failures caused by the test setup rather than the model. Prefer agents we did not write and tasks with
  correct answers over LLM-judged ones. Do not tune prompts, tasks or agent code to make results look better.
- **Check Downshift's claims against reality.** After an optimization, re-run the real agent yourself
  (fresh runs, not replays, ideally two trials) with the baseline and each recommended harness on the
  held-out tasks, and compare with what Downshift reported. Also compare with the plain model swap
  (same harness, cheaper model). Say clearly where the claims held and where they did not.

## Commits and pull requests

Commit messages and PR titles/descriptions must not mention any model provider other than
Nebius Token Factory.

## Secrets

Never print, log or copy API key values. `.env` is gitignored and references keys from the shell
(`NEBIUS_API_KEY=${TOKEN_FACTORY_API_KEY}`) instead of holding them.

## Commands

- API: `uv run uvicorn app.main:app --app-dir server --port 8000`
- Web: `cd web && npm run dev` (http://localhost:3000)
- Tests: `uv run pytest` (no live model calls)
