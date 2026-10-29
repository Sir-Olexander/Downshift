"""Record baseline runs of the tutor-agent demo agent with the downshift SDK.

    uv run python record_baseline.py --limit 3     # quick check (from this folder)
    uv run python record_baseline.py               # all 12 tasks

Same runtime as the research agent (demo_agent/research_agent); only harness.yaml and questions.json differ.
"""

from pathlib import Path

from research_agent.recorder import main

if __name__ == "__main__":
    raise SystemExit(main(Path(__file__).resolve().parent, "tutor-agent", __doc__))
