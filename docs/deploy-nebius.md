# Deploying Downshift

The hosted demo is two containers: the API (FastAPI + SQLite, seeded with precomputed results) and
the web UI (Next.js). The optimizer runs inside the API process for small live runs, and the same
code runs as a one-off job for bigger optimizations (`python -m app.cli optimize`).

## Images

```bash
docker build -f server/Dockerfile -t downshift-api .
docker build -t downshift-web --build-arg API_URL=https://<api host> web
```

`docker compose up --build` runs both locally (API on :8000, web on :3000) with the keys from `.env`.

## Nebius Serverless (target setup)

Nebius encourages running demos on Serverless, so this is the intended layout. It was not yet
exercised against a live Nebius account during the hackathon build; the pieces below are the
standard container shape it expects.

1. **Push the two images** to a registry Nebius can pull from (Nebius Container Registry or GHCR).
2. **Endpoint `downshift-api`** from `downshift-api`, port 8000, with environment:
   - `NEBIUS_API_KEY` (Token Factory) and `DOWNSHIFT_PROVIDER=tokenfactory`
   - `DOWNSHIFT_API_KEYS` – keys the SDK may use to send runs
   - `DOWNSHIFT_DEMO_MODE=true`, `DOWNSHIFT_MAX_LIVE_PER_HOUR=2` – small, rate-limited live runs
   - `GITHUB_REPO`, `GITHUB_TOKEN` – for the "Open PR" button
   - `DOWNSHIFT_PUBLIC_WEB_URL` – the web endpoint's URL (linked from PR descriptions)
   - a persistent volume mounted at `/data` (SQLite). Without one, the API still works: it seeds the
     precomputed results at every start and keeps live results until the next restart.
3. **Endpoint `downshift-web`** from `downshift-web` built with `API_URL=https://<api endpoint>`, port 3000.
4. **Job `downshift-optimize`** (optional) from `downshift-api` with the command
   `python -m app.cli optimize --targets super,nano,mix --rounds 2 --sample 10`, the same env and
   the same `/data` volume. Use it for the full-size optimizations; the Endpoint keeps live demo runs small.

## Switching from Ollama to Token Factory

The build used Ollama Cloud because no Token Factory key was available. Switching is configuration:
set `NEBIUS_API_KEY` and `DOWNSHIFT_PROVIDER=tokenfactory`. Model IDs and prices live in
`sdk/downshift/models.yaml`; verify the three Nemotron IDs in the Token Factory console before the
first run (they were read from the public catalog links on 2026-10-26). The `reasoning: off` mapping
for Token Factory (`chat_template_kwargs.enable_thinking=false`) is the vLLM convention and has not
been exercised against a live key yet.
