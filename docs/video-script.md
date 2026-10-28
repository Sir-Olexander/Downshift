# Demo video script (about 3 minutes)

**0:00 – Hook (15 s).** Screen: the results page, headline large.
"This research agent runs on Nemotron 3 Ultra. Downshift just told us which cheaper Nemotron model can
do the same job, rewrote the agent's harness for it, proved it on held-out runs, and opened the PR."

**0:15 – The problem (20 s).** Screen: the demo agent folder and `harness.yaml`.
"Everyone wants to move agents to cheaper models, but nobody wants to find out in production that
the small model stopped citing sources. Switching the model name is easy; making the agent actually
work on it means rewriting prompts, tool descriptions and the step plan, and then measuring."

**0:35 – The SDK (25 s).** Screen: `record_baseline.py` and a run arriving in the API log.
"You add a thin SDK. It records real runs: every model call, every tool call, the final answer and the
cost. The agent's behaviour lives in one versioned file, the harness, so changes need no code."

**1:00 – The optimizer (50 s).** Screen: the live progress page with the event log.
"Downshift splits the recorded runs 60/40 and never reports on the 60. Nemotron 3 Nano labels every
step: how hard it is, whether it needs a strong model. Nemotron 3 Ultra then rewrites the harness
for each target, looking up prompting guidance for that model, and we replay the recorded runs on
the target. Tool calls that match the recording are served from it; new ones run live, which is safe
because the tools are read-only. An Ultra judge compares each new answer with the original, blind
and in random order, next to automatic checks: answer produced, sources listed, sources drawn from the
evidence. Two rounds, keep the best, then one honest pass on the held-out set."

**1:50 – Results (35 s).** Screen: chart and table.
"One point per option. On 17 held-out runs, Nano keeps task success at 94% against 100% for the
baseline, at 94% lower cost per run. The per-step mix loses nothing on success and only 3 quality
points, at half the cost. And the honest part: the judge still prefers Ultra's answers more often than
not, and Nano's own analysis says synthesis needs a strong model in 92% of runs, which is exactly why the
mix keeps Ultra for synthesis and puts Nano on planning and checking."

**2:25 – Diff and run view (25 s).** Screen: the option page.
"This is the whole change: the harness side by side. Shorter rules, explicit output format, reasoning
off for the search step, a verify step as a safety net. And every held-out run is inspectable:
baseline and new timeline on the same question, with the judge's reason."

**2:50 – PR (15 s).** Screen: click Open pull request, show the PR on GitHub.
"One click opens a pull request on the agent's repo with the new harness and the results table.
Review, merge, downshift."
