"""Replay an adapted agent (harness runtime: custom) with its own code, in its own environment.

The server never imports the agent. It starts `python -m downshift.runner replay` in the agent's
folder with the agent's Python (downshift.yaml `python:`), sends the job on stdin and reads one JSON
line per finished replay, so progress and scoring stream as replays complete.
"""

from __future__ import annotations

import json
import os
import queue
import subprocess
import sys
import threading
from collections import deque
from collections.abc import Callable
from pathlib import Path
from typing import Any

from downshift import Harness
from downshift.adapter import has_adapter, load_agent_config

from ..agents import FolderError, resolve_inside


# Stop a runner that finishes no replay for this long (a stalled provider connection, a hung tool);
# its unfinished replays become error records that `app.cli redo` can retry.
IDLE_TIMEOUT_S = float(os.environ.get("DOWNSHIFT_REPLAY_IDLE_TIMEOUT_S", "1800") or 1800)


class ExternalAgentError(RuntimeError):
    pass


class ExternalAgent:
    def __init__(self, folder: Path, provider: str | None):
        self.folder = folder
        self.config = load_agent_config(folder)
        self.provider = provider
        py = self.config.get("python")
        if py:
            p = Path(py).expanduser()
            self.python = str(p if p.is_absolute() else (folder / p))
            if not Path(self.python).exists():
                raise ExternalAgentError(f"the agent's Python {self.python} (downshift.yaml `python:`) does not exist")
        else:
            self.python = sys.executable

    @classmethod
    def for_project(cls, db: Any, settings: Any, project_id: str) -> ExternalAgent:
        """The registered agent folder for a project. Running a folder's code needs folder access on."""
        if not settings.allow_fs:
            raise ExternalAgentError("this agent runs its own code (harness runtime: custom), which needs folder access (DOWNSHIFT_ALLOW_FS=true)")
        agent = db.get_agent(project_id)
        if not agent:
            raise ExternalAgentError(f"project '{project_id}' uses a custom runtime but no agent folder is registered under that id; add it on the Agents screen (or POST /v1/agents) with id '{project_id}'")
        try:
            folder = resolve_inside(settings.agents_root, agent["path"])
        except FolderError as e:
            raise ExternalAgentError(str(e)) from e
        if not has_adapter(folder):
            raise ExternalAgentError(f"{folder} has no downshift_agent.py / downshift.yaml adapter")
        return cls(folder, settings.provider)

    def describe(self) -> str:
        return f"{self.folder} with {self.python}"

    def replay_many(self, harness: Harness, records: list[dict[str, Any]], *, concurrency: int = 3, meta: dict[str, Any] | None = None, on_each: Callable[[dict[str, Any], dict[str, Any]], None] | None = None) -> list[dict[str, Any]]:
        """Replay every record with `harness`; returns replay records in input order.
        A replay that could not run comes back as an error record, so it is scored as a failure and
        `app.cli redo` can retry it."""
        if not records:
            return []
        job = {"harness": harness.to_dict(), "records": records, "meta": meta or {}, "provider": self.provider, "concurrency": concurrency, "project": records[0].get("project")}
        env = dict(os.environ)
        if self.provider:
            env["DOWNSHIFT_PROVIDER"] = self.provider
        env.setdefault("DOWNSHIFT_MAX_CONCURRENT_CALLS", str(max(1, concurrency)))
        proc = subprocess.Popen(
            [self.python, "-m", "downshift.runner", "replay", "--folder", str(self.folder)],
            cwd=str(self.folder), env=env, stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True, encoding="utf-8",
        )
        stderr_tail: deque[str] = deque(maxlen=40)

        def drain() -> None:
            assert proc.stderr is not None
            for line in proc.stderr:
                stderr_tail.append(line.rstrip())

        t = threading.Thread(target=drain, daemon=True)
        t.start()
        assert proc.stdin is not None and proc.stdout is not None
        try:
            proc.stdin.write(json.dumps(job, ensure_ascii=False))
            proc.stdin.close()
        except BrokenPipeError:
            pass
        results: list[dict[str, Any] | None] = [None] * len(records)
        lines: queue.Queue[str | None] = queue.Queue()

        def read() -> None:
            assert proc.stdout is not None
            for raw in proc.stdout:
                lines.put(raw)
            lines.put(None)

        threading.Thread(target=read, daemon=True).start()
        timed_out = False
        while True:
            try:
                line = lines.get(timeout=IDLE_TIMEOUT_S)
            except queue.Empty:
                timed_out = True
                proc.kill()
                break
            if line is None:
                break
            line = line.strip()
            if not line.startswith("{"):
                continue
            try:
                msg = json.loads(line)
                i = int(msg["index"])
            except (ValueError, KeyError, TypeError):
                continue
            if not 0 <= i < len(records) or results[i] is not None:
                continue
            rec = msg.get("record") or _error_record(records[i], harness, msg.get("error") or "the runner returned no record", meta)
            results[i] = rec
            if on_each:
                on_each(records[i], rec)
        proc.wait()
        t.join(timeout=5)
        missing = [i for i, r in enumerate(results) if r is None]
        if missing:
            if timed_out:
                why = f"no replay finished for {int(IDLE_TIMEOUT_S)}s, so the agent runner was stopped (retry with app.cli redo)"
            else:
                why = f"the agent runner exited with code {proc.returncode}: " + " | ".join(list(stderr_tail)[-6:])
            for i in missing:
                rec = _error_record(records[i], harness, why, meta)
                results[i] = rec
                if on_each:
                    on_each(records[i], rec)
        return [r for r in results if r is not None]


def _error_record(base: dict[str, Any], harness: Harness, error: str, meta: dict[str, Any] | None) -> dict[str, Any]:
    import uuid

    from downshift.tracing import now_iso

    return {
        "id": uuid.uuid4().hex[:16], "project": base.get("project"), "task_id": base.get("task_id"), "input": base.get("input", ""),
        "harness": harness.to_dict(), "harness_fingerprint": harness.fingerprint(), "started_at": now_iso(), "ended_at": now_iso(),
        "status": "error", "error": error[:4000], "output": None, "score": None, "events": [],
        "totals": {"model_calls": 0, "tool_calls": 0, "tool_calls_recorded": 0, "tool_calls_live": 0, "tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0, "latency_ms": 0, "model_latency_ms": 0, "tool_latency_ms": 0, "wall_ms": 0},
        "meta": {**(meta or {}), "mode": "replay", "replay_of": base.get("id")},
    }
