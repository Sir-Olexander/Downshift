# More demo agents

Four extra agents to try Downshift on, each with a different job. They share the research agent's
runtime (`demo_agent/research_agent`: plan, search, synthesize and verify steps over `web_search` and
`read_page`), so the optimizer can replay them; everything that makes them different lives in their
`harness.yaml` and `questions.json`.

| Folder | Task | Steps | Output |
|---|---|---|---|
| `fact-checker/` | Check a claim (12 popular claims and myths) | plan, search, synthesize, verify (with one rewrite) | Verdict, short explanation, sources |
| `compare-agent/` | Compare two things side by side (12 comparisons) | plan, search (up to 8 tool calls), synthesize | One bullet per criterion, bottom line, sources |
| `timeline-agent/` | Build a dated timeline (12 events and lives) | research (no plan step), write | 6 to 10 dated entries, sources |
| `tutor-agent/` | Explain a concept to a 15-year-old (12 concepts) | plan, search (up to 4 tool calls), explain | Explanation, analogy, 3-question quiz, sources |

All four start on Nemotron 3 Ultra, like the research agent. Record baseline runs from an agent's folder:

```bash
cd demo_agents/fact-checker
uv run python record_baseline.py --limit 3     # quick check, about $0.10 on Token Factory
uv run python record_baseline.py               # all 12 tasks, about $0.30 to $0.60
```

The project id defaults to the folder name; pass `--project <id>` if you gave the agent another id
in the UI.
