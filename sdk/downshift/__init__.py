"""Downshift SDK: record your agent's runs, load its harness, replay it on cheaper models.

    from downshift import Downshift

    ds = Downshift(api_key="ds_dev", endpoint="http://localhost:8000", project="research-agent")
    harness = ds.load_harness("harness.yaml")
    with ds.run(task_id="q001", input=question, harness=harness) as run:
        res = run.chat("search", messages, tools=tool_defs)       # recorded model call
        hits = run.tool("web_search", {"query": q}, lambda: search(q))  # recorded tool call
        run.finish(answer=text, sources=urls)
"""

from __future__ import annotations

import os
from pathlib import Path
from typing import Any

from .harness import Harness, HarnessError, Step, StepParams, ToolSpec, FewShot, Defaults
from .pricing import ModelTable, ModelInfo, ProviderInfo, default_table, UnknownModelError
from .providers import LLM, LLMError, ChatResult, ToolCallRequest, active_provider_name
from .replay import ReplayCache, ReplayRun, ReplayMiss
from .tracing import Run, RunRecord, ModelCallEvent, ToolCallEvent, Totals, SDK_VERSION
from .transport import HttpTransport, FileTransport, MemoryTransport, NullTransport

__version__ = SDK_VERSION
__all__ = [
    "Downshift", "Harness", "HarnessError", "Step", "StepParams", "ToolSpec", "FewShot", "Defaults",
    "ModelTable", "ModelInfo", "ProviderInfo", "default_table", "UnknownModelError",
    "LLM", "LLMError", "ChatResult", "ToolCallRequest", "active_provider_name",
    "ReplayCache", "ReplayRun", "ReplayMiss",
    "Run", "RunRecord", "ModelCallEvent", "ToolCallEvent", "Totals",
    "HttpTransport", "FileTransport", "MemoryTransport", "NullTransport",
]


class Downshift:
    """Entry point. Holds the provider client, the model table and the transport."""

    def __init__(
        self,
        api_key: str | None = None,
        endpoint: str | None = None,
        *,
        project: str | None = None,
        provider: str | None = None,
        transport: Any = None,
        offline_dir: str | os.PathLike | None = None,
        table: ModelTable | None = None,
        llm: LLM | None = None,
    ):
        self.table = table or default_table()
        self.project = project or os.environ.get("DOWNSHIFT_PROJECT") or "default"
        self.api_key = api_key or os.environ.get("DOWNSHIFT_API_KEY") or "ds_dev"
        self.endpoint = endpoint or os.environ.get("DOWNSHIFT_ENDPOINT") or "http://localhost:8000"
        offline_dir = offline_dir or os.environ.get("DOWNSHIFT_OFFLINE_DIR")
        if transport is not None:
            self.transport = transport
        elif offline_dir:
            self.transport = FileTransport(offline_dir)
        else:
            self.transport = HttpTransport(self.endpoint, self.api_key)
        self.llm = llm or LLM(provider, table=self.table)

    @property
    def provider(self) -> str:
        return self.llm.provider_name

    def load_harness(self, path: str | Path) -> Harness:
        h = Harness.load(path)
        h.validate_models(self.table, self.llm.provider_name)
        return h

    def run(self, *, task_id: str, input: str, harness: Harness, meta: dict[str, Any] | None = None, run_id: str | None = None) -> Run:
        return Run(project=self.project, task_id=task_id, input=input, harness=harness, llm=self.llm, table=self.table, transport=self.transport, meta=meta, run_id=run_id)

    def replay(self, *, recorded: dict[str, Any], harness: Harness, meta: dict[str, Any] | None = None, allow_live: bool = True, run_id: str | None = None, transport: Any = None) -> ReplayRun:
        return ReplayRun(
            recorded=recorded,
            allow_live=allow_live,
            project=recorded.get("project") or self.project,
            task_id=recorded.get("task_id", ""),
            input=recorded.get("input", ""),
            harness=harness,
            llm=self.llm,
            table=self.table,
            transport=self.transport if transport is None else transport,
            meta=meta,
            run_id=run_id,
        )
