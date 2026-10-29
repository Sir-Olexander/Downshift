"""Adapters: how Downshift runs an agent it did not build.

An agent folder that Downshift should record, replay and optimize holds:

  downshift_agent.py   an AgentAdapter subclass, exposed as `agent`. It runs the agent's own code for
                       one task, sending model calls through `run.chat` and tool calls through
                       `run.tool`, and can grade an output against the task's correct answer.
  harness.yaml         the agent's prompts, tool descriptions and per-step models (`runtime: custom`).
                       The optimizer rewrites this file; the adapter applies it.
  tasks.jsonl          one task per line: {"id", "input", "expected"?, "meta"?}.
  downshift.yaml       optional: which Python runs the agent (its own environment) and file names.

Downshift then runs the agent through `python -m downshift.runner` in that environment, so the
agent keeps its own dependencies and Downshift never imports its code into the server.
"""

from __future__ import annotations

import importlib
import json
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

import yaml

from .harness import Harness
from .tracing import Run

AGENT_CONFIG_FILE = "downshift.yaml"
DEFAULT_CONFIG: dict[str, Any] = {
    "entry": "downshift_agent:agent",
    "python": None,  # None: the Python that runs the runner
    "tasks": "tasks.jsonl",
    "harness": "harness.yaml",
}


@dataclass
class Task:
    id: str
    input: str
    # The correct answer, in whatever form the adapter's grader understands. None: no ground truth.
    expected: Any = None
    meta: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, d: dict[str, Any]) -> Task:
        known = {"id", "input", "question", "expected", "meta"}
        meta = dict(d.get("meta") or {})
        meta.update({k: v for k, v in d.items() if k not in known})
        text = d.get("input", d.get("question"))
        if not d.get("id") or text is None:
            raise ValueError(f"a task needs 'id' and 'input' (or 'question'): {str(d)[:200]}")
        return cls(id=str(d["id"]), input=str(text), expected=d.get("expected"), meta=meta)

    @classmethod
    def from_record(cls, record: dict[str, Any]) -> Task:
        meta = record.get("meta") or {}
        return cls(id=str(record.get("task_id", "")), input=str(record.get("input", "")), expected=meta.get("expected"), meta=dict(meta.get("task") or {}))


class AgentAdapter:
    """Base class for running a third-party agent under Downshift.

    Subclasses implement `run` (required) and `score` (when tasks have correct answers).
    """

    name: str = "agent"
    # False when tools change state (orders, bookings, files): replays then run every tool live
    # instead of reusing the recorded results.
    reuse_tool_results: bool = True

    def run(self, task: Task, harness: Harness, run: Run) -> None:
        """Run the agent on one task. Route model calls through run.chat(step, messages, tools=...)
        and tool calls through run.tool(name, args, fn). Finish with run.finish(answer, **extra)."""
        raise NotImplementedError

    def score(self, task: Task, output: dict[str, Any]) -> dict[str, Any] | None:
        """Grade `output` (what run.finish stored) against task.expected.
        Return {"passed": bool, "score": 0..1 or None, "details": "short reason"}, or None."""
        return None

    def default_harness(self) -> Harness | None:
        """The harness that reproduces the agent as it ships (used by `downshift.runner init-harness`)."""
        return None


def render(template: str, **values: Any) -> str:
    """Fill {name} placeholders that are given; leave every other brace alone (prompts contain JSON)."""
    out = template
    for k, v in values.items():
        out = out.replace("{" + k + "}", "" if v is None else str(v))
    return out


def load_agent_config(folder: str | Path) -> dict[str, Any]:
    folder = Path(folder)
    cfg = dict(DEFAULT_CONFIG)
    f = folder / AGENT_CONFIG_FILE
    if f.is_file():
        data = yaml.safe_load(f.read_text(encoding="utf-8")) or {}
        if not isinstance(data, dict):
            raise ValueError(f"{f} must be a mapping")
        cfg.update({k: v for k, v in data.items() if v is not None})
    return cfg


def has_adapter(folder: str | Path) -> bool:
    folder = Path(folder)
    cfg = load_agent_config(folder)
    module = str(cfg["entry"]).split(":", 1)[0]
    return (folder / AGENT_CONFIG_FILE).is_file() or (folder / f"{module.replace('.', '/')}.py").is_file()


def load_adapter(folder: str | Path, entry: str | None = None) -> AgentAdapter:
    """Import `module:attr` from the agent folder. A class is instantiated."""
    folder = Path(folder).resolve()
    entry = entry or load_agent_config(folder)["entry"]
    module_name, _, attr = str(entry).partition(":")
    attr = attr or "agent"
    if str(folder) not in sys.path:
        sys.path.insert(0, str(folder))
    module = importlib.import_module(module_name)
    obj = getattr(module, attr)
    if isinstance(obj, type):
        obj = obj()
    if not hasattr(obj, "run"):
        raise TypeError(f"{entry} is not an agent adapter (it has no run method)")
    return obj


def load_tasks(path: str | Path) -> list[Task]:
    p = Path(path)
    text = p.read_text(encoding="utf-8")
    if p.suffix == ".jsonl":
        rows = [json.loads(line) for line in text.splitlines() if line.strip()]
    else:
        rows = json.loads(text)
        if isinstance(rows, dict):
            rows = rows.get("tasks") or []
    return [Task.from_dict(r) for r in rows]


def grade(adapter: AgentAdapter, task: Task, run: Run) -> None:
    """Attach the grader's verdict to the run, when the task has a correct answer."""
    if task.expected is None or run.record.status != "ok":
        return
    try:
        s = adapter.score(task, run.record.output or {})
    except Exception as e:  # a grader bug must not lose the run
        s = {"passed": False, "score": 0.0, "details": f"grader error: {type(e).__name__}: {e}"[:300], "grader_error": True}
    if s is None:
        return
    passed = bool(s.get("passed"))
    score = s.get("score")
    run.set_score({
        "passed": passed,
        "score": float(score) if isinstance(score, (int, float)) else (1.0 if passed else 0.0),
        "details": str(s.get("details", ""))[:500],
        "grader": getattr(adapter, "name", "agent"),
        **({"grader_error": True} if s.get("grader_error") else {}),
    })


def task_meta(task: Task) -> dict[str, Any]:
    """What a run record keeps about its task, so a replay can rebuild it."""
    out: dict[str, Any] = {}
    if task.expected is not None:
        out["expected"] = task.expected
    if task.meta:
        out["task"] = task.meta
    return out
