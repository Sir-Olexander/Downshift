# Try a run yourself

A run in Downshift has four stages: **add an agent → record baseline runs → start an optimization →
read the results**. This walks through it with one of the demo agents in `demo_agents/`.

Budget: the Token Factory key has a **$15 limit**. The path below costs about **$0.50** per agent
(12 baseline runs on Ultra ≈ $0.40, one demo-mode optimization ≈ $0.10 to $0.50 depending on targets).

## 0. Start the app (once per session)

Two terminals, from the repo root. Restart them if they were already running, so they pick up `.env`.

```bash
uv run uvicorn app.main:app --app-dir server --port 8000      # terminal 1: API
cd web && npm run dev                                         # terminal 2: web, http://localhost:3000
```

Check the API is on Token Factory: `curl -s localhost:8000/healthz` should show `"provider":"tokenfactory"`.

## 1. Add the agent

1. Open http://localhost:3000/agents and click **Add agent**.
2. Folder: paste the full path, e.g. `/Users/nadiya/Documents/Alex/Downshift/demo_agents/fact-checker`
   (or use **Browse**), then confirm. Downshift reads the folder: it finds `harness.yaml`, the 12 tasks in
   `questions.json` and `record_baseline.py`.
3. Keep the suggested **Agent id** (`fact-checker`). It is the project name the runs are recorded under.
4. The harness step shows the existing `harness.yaml`; click through. You can edit it here if you want
   to try a change.

## 2. Record baseline runs

The **Record baseline runs** step shows the command to copy. In a third terminal:

```bash
cd demo_agents/fact-checker
uv run python record_baseline.py --project fact-checker --limit 5   # quick: about $0.17, 2 minutes
# or all 12 tasks (a firmer result):
uv run python record_baseline.py --project fact-checker             # about $0.40, 4 minutes
```

Each line prints `ok <task> $cost latency tokens sources`. The counter on the page goes up as runs
arrive. At 4 successful runs **Continue to run** turns on.

## 3. Start an optimization

On the **Run** screen (top bar → Run):

1. **Cheaper options to try**: tick one or more of Nemotron 3 Super, Nemotron 3 Nano, Per-step mix.
   Fewer options = cheaper and faster. Nano alone is the cheapest test.
2. Demo mode keeps it small: 1 round, up to 4 runs replayed per round, 6 held-out runs, $3 cap,
   at most 2 live optimizations per hour.
3. Click **Start optimization**. The live log shows each phase: split → analyze → rewrite → replay
   → score. A run with 5 recorded tasks and one option takes a few minutes.

## 4. Read the results

When it finishes, open **View results →** (or top bar → Results / History):

- The table compares the baseline (Ultra) with each option on task success, quality, cost per run and
  latency, on the held-out runs only.
- Click an option for its harness diff (what the optimizer changed) and every replayed run side by side
  with the baseline.
- **Open PR** shows the pull request it would open (it only opens one if `GITHUB_REPO` and a token are set).

## Things to know

- With 5 recorded tasks only 2 are held out, so one run flips success by 50 points. Record all 12 for a
  more meaningful result.
- If something stalls, the log says so (rate limits wait and resume). An interrupted optimization can be
  finished with `uv run python -m app.cli redo <optimization id> <option>`.
- Try the other agents the same way: `compare-agent`, `timeline-agent`, `tutor-agent`.
