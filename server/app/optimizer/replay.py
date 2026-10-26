"""Replay recorded runs with a candidate harness on the target model(s)."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor
from typing import Any, Callable

from downshift import Downshift, Harness, NullTransport
from research_agent.agent import ResearchAgent
from research_agent.tools import SearchTools


def replay_one(sdk: Downshift, harness: Harness, baseline_record: dict[str, Any], tools: SearchTools, *, meta: dict[str, Any] | None = None) -> dict[str, Any]:
    """Run the agent again on one recorded task; tool calls that match are served from the recording."""
    with sdk.replay(recorded=baseline_record, harness=harness, meta=meta, transport=NullTransport()) as run:
        agent = ResearchAgent(harness, run, tools)
        try:
            agent.answer(baseline_record.get("input", ""))
        except Exception as e:  # keep the record; the scorer will count it as a failure
            run.fail(f"{type(e).__name__}: {e}")
    return run.record.model_dump(mode="json")


def replay_many(sdk: Downshift, harness: Harness, records: list[dict[str, Any]], tools: SearchTools, *, concurrency: int = 4, meta: dict[str, Any] | None = None, on_each: Callable[[dict[str, Any], dict[str, Any]], None] | None = None) -> list[dict[str, Any]]:
    """Replay many records in parallel. Results come back in input order."""
    results: list[dict[str, Any] | None] = [None] * len(records)

    def work(i: int) -> None:
        rec = replay_one(sdk, harness, records[i], tools, meta=meta)
        results[i] = rec
        if on_each:
            on_each(records[i], rec)

    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        list(pool.map(work, range(len(records))))
    return [r for r in results if r is not None]
