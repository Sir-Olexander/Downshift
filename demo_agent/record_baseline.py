"""Record baseline runs of the research agent with the downshift SDK.

    uv run python demo_agent/record_baseline.py --limit 3            # quick check
    uv run python demo_agent/record_baseline.py --concurrency 4      # all questions

Runs are sent to the Downshift backend (DOWNSHIFT_ENDPOINT / DOWNSHIFT_API_KEY) or written to
--offline-dir as JSON files you can import later with `POST /v1/runs/import`.
"""

from pathlib import Path

from research_agent.recorder import main

if __name__ == "__main__":
    raise SystemExit(main(Path(__file__).resolve().parent, "research-agent", __doc__))
