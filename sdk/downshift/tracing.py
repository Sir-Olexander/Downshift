"""Run tracing: records every model call, tool call and the final answer of one agent run."""

from __future__ import annotations

import json
import re
import time
import traceback
import uuid
from datetime import datetime, timezone
from typing import Any, Callable, Literal

from pydantic import BaseModel, Field

from .harness import Harness, Step
from .pricing import ModelTable, default_table
from .providers import LLM, ChatResult, ToolCallRequest

SDK_VERSION = "0.1.0"


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


class ModelCallEvent(BaseModel):
    type: Literal["model_call"] = "model_call"
    index: int
    step: str
    ts: str
    model: str
    provider: str
    provider_model: str
    params: dict[str, Any] = Field(default_factory=dict)
    messages: list[dict[str, Any]] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    response: dict[str, Any] = Field(default_factory=dict)
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float | None = None
    latency_ms: int = 0
    error: str | None = None
    # set when run.chat changed what the agent sees: "repair" (a re-ask because the final reply missed the
    # step's final_format) or "recovered_tool_call" (a tool call written as text was turned into a real one)
    note: str | None = None


DEFAULT_REPAIR_PROMPT = "Your last reply is missing the required final format. Reply again with only your final answer, in that format."

_XML_CALL = re.compile(r"<tool_call>\s*<function=([\w.-]+)>(.*?)</function>", re.S)
_XML_PARAM = re.compile(r"<parameter=([\w.-]+)>\s*(.*?)\s*</parameter>", re.S)


def recover_tool_calls(content: str, tool_names: list[str]) -> list[ToolCallRequest]:
    """Tool calls the model wrote as text, for tools that were actually offered. Empty when none."""
    if not content or not tool_names:
        return []
    out: list[ToolCallRequest] = []
    for name, body in _XML_CALL.findall(content):
        if name in tool_names:
            args = {k: v for k, v in _XML_PARAM.findall(body)}
            out.append(ToolCallRequest(id=f"recovered_{len(out)}", name=name, arguments=args, raw_arguments=json.dumps(args)))
    if out:
        return out
    dec = json.JSONDecoder()
    i = 0
    while True:
        j = content.find("{", i)
        if j < 0:
            break
        try:
            obj, end = dec.raw_decode(content, j)
        except json.JSONDecodeError:
            i = j + 1
            continue
        i = end
        if isinstance(obj, dict):
            name = obj.get("name") or obj.get("tool")
            args = obj.get("arguments", obj.get("args", obj.get("parameters")))
            if isinstance(args, str):
                try:
                    args = json.loads(args)
                except json.JSONDecodeError:
                    args = None
            if name in tool_names and isinstance(args, dict):
                out.append(ToolCallRequest(id=f"recovered_{len(out)}", name=name, arguments=args, raw_arguments=json.dumps(args)))
    return out


class ToolCallEvent(BaseModel):
    type: Literal["tool_call"] = "tool_call"
    index: int
    step: str | None = None
    ts: str
    name: str
    args: dict[str, Any] = Field(default_factory=dict)
    result: Any = None
    latency_ms: int = 0
    # "live": the tool really ran. "recorded": served from the original run during a replay.
    source: Literal["live", "recorded"] = "live"
    matched_args: dict[str, Any] | None = None
    error: str | None = None


Event = ModelCallEvent | ToolCallEvent


class Totals(BaseModel):
    model_calls: int = 0
    tool_calls: int = 0
    tool_calls_recorded: int = 0
    tool_calls_live: int = 0
    tokens_in: int = 0
    tokens_out: int = 0
    cost_usd: float = 0.0
    # Sum of model and tool latencies. In replays, recorded tool hits count their original latency,
    # so baseline and replay latencies stay comparable.
    latency_ms: int = 0
    model_latency_ms: int = 0
    tool_latency_ms: int = 0
    wall_ms: int = 0


class RunRecord(BaseModel):
    id: str
    project: str
    task_id: str
    input: str
    harness: dict[str, Any]
    harness_fingerprint: str
    started_at: str
    ended_at: str | None = None
    status: Literal["running", "ok", "error"] = "running"
    error: str | None = None
    output: dict[str, Any] | None = None
    # Ground-truth grade from the agent's own grader, when the task has a correct answer:
    # {"passed": bool, "score": 0..1 or null, "details": "...", "grader": "..."}
    score: dict[str, Any] | None = None
    events: list[Event] = Field(default_factory=list)
    totals: Totals = Field(default_factory=Totals)
    meta: dict[str, Any] = Field(default_factory=dict)


class Run:
    """One traced agent run. Use as a context manager so the record is always sent."""

    def __init__(
        self,
        *,
        project: str,
        task_id: str,
        input: str,
        harness: Harness,
        llm: LLM,
        table: ModelTable | None = None,
        transport: Any = None,
        meta: dict[str, Any] | None = None,
        run_id: str | None = None,
        mode: str = "record",
    ):
        self.harness = harness
        self.llm = llm
        self.table = table or default_table()
        self.transport = transport
        self._t0 = time.perf_counter()
        self._closed = False
        self.rec = RunRecord(
            id=run_id or uuid.uuid4().hex[:16],
            project=project,
            task_id=task_id,
            input=input,
            harness=harness.to_dict(),
            harness_fingerprint=harness.fingerprint(),
            started_at=now_iso(),
            meta={
                "sdk_version": SDK_VERSION,
                "provider": llm.provider_name,
                "mode": mode,
                **(meta or {}),
            },
        )

    # ---- properties -------------------------------------------------------------------------
    @property
    def id(self) -> str:
        return self.rec.id

    @property
    def events(self) -> list[Event]:
        return self.rec.events

    @property
    def record(self) -> RunRecord:
        return self.rec

    # ---- model calls ------------------------------------------------------------------------
    def chat(
        self,
        step: Step | str,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: Any = None,
        response_format: dict[str, Any] | None = None,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        reasoning: str | None = None,
    ) -> ChatResult:
        """Call the model configured for `step` in the harness and record the call.

        Two optional repairs, declared on the step: recover_tool_calls turns a tool call written as text into
        a real one; final_format re-asks once (without tools) when a final reply misses the required format."""
        step_obj = self.harness.step(step) if isinstance(step, str) else step
        res = self._chat_once(step_obj, messages, tools=tools, tool_choice=tool_choice, response_format=response_format, model=model, temperature=temperature, max_tokens=max_tokens, reasoning=reasoning)
        if step_obj.recover_tool_calls and tools and not res.tool_calls:
            names = [t.get("function", {}).get("name", "") for t in tools]
            recovered = recover_tool_calls(res.content, names)
            if recovered:
                res.tool_calls = recovered
                res.content = ""
                ev = self.rec.events[-1]
                ev.note = "recovered_tool_call"
                ev.response = res.response_dict()
        if step_obj.final_format and not res.tool_calls and not re.search(step_obj.final_format, res.content or ""):
            repair_msgs = list(messages) + [{"role": "assistant", "content": res.content or ""}, {"role": "user", "content": step_obj.repair_prompt or DEFAULT_REPAIR_PROMPT}]
            fixed = self._chat_once(step_obj, repair_msgs, tools=None, response_format=response_format, model=model, temperature=temperature, max_tokens=max_tokens, reasoning=reasoning, note="repair")
            if (fixed.content or "").strip():
                res = fixed
        return res

    def _chat_once(
        self,
        step_obj: Step,
        messages: list[dict[str, Any]],
        *,
        tools: list[dict[str, Any]] | None = None,
        tool_choice: Any = None,
        response_format: dict[str, Any] | None = None,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        reasoning: str | None = None,
        note: str | None = None,
    ) -> ChatResult:
        p = self.harness.params(step_obj)
        model = model or p.model
        temperature = p.temperature if temperature is None else temperature
        max_tokens = p.max_tokens if max_tokens is None else max_tokens
        reasoning = p.reasoning if reasoning is None else reasoning
        params = {"temperature": temperature, "max_tokens": max_tokens, "reasoning": reasoning}
        ev = ModelCallEvent(
            index=len(self.rec.events),
            step=step_obj.id,
            ts=now_iso(),
            model=model,
            provider=self.llm.provider_name,
            provider_model="",
            params=params,
            messages=messages,
            tools=[t.get("function", {}).get("name", "?") for t in (tools or [])],
            note=note,
        )
        try:
            ev.provider_model = self.llm.resolve(model)
        except Exception:
            ev.provider_model = model
        t0 = time.perf_counter()
        try:
            res = self.llm.chat(
                model,
                messages,
                tools=tools,
                tool_choice=tool_choice,
                temperature=temperature,
                max_tokens=max_tokens,
                reasoning=reasoning,
                response_format=response_format,
            )
        except Exception as e:
            ev.latency_ms = int((time.perf_counter() - t0) * 1000)
            ev.error = f"{type(e).__name__}: {e}"[:2000]
            self._add(ev)
            raise
        ev.response = res.response_dict()
        ev.tokens_in = res.tokens_in
        ev.tokens_out = res.tokens_out
        ev.latency_ms = res.latency_ms
        ev.cost_usd = self.table.cost(model, res.tokens_in, res.tokens_out)
        ev.provider_model = res.provider_model
        self._add(ev)
        return res

    # ---- tool calls -------------------------------------------------------------------------
    def tool(
        self,
        name: str,
        args: dict[str, Any],
        fn: Callable[[], Any],
        *,
        step: str | None = None,
    ) -> Any:
        """Run a tool through `fn()` and record its arguments, result and latency."""
        ev = ToolCallEvent(index=len(self.rec.events), step=step, ts=now_iso(), name=name, args=args)
        t0 = time.perf_counter()
        try:
            result = fn()
        except Exception as e:
            ev.latency_ms = int((time.perf_counter() - t0) * 1000)
            ev.error = f"{type(e).__name__}: {e}"[:2000]
            self._add(ev)
            raise
        ev.latency_ms = int((time.perf_counter() - t0) * 1000)
        ev.result = result
        self._add(ev)
        return result

    # ---- lifecycle --------------------------------------------------------------------------
    def finish(self, answer: str, sources: list[str] | None = None, **extra: Any) -> None:
        self.rec.output = {"answer": answer, "sources": list(sources or []), **extra}
        self.rec.status = "ok"
        self.rec.error = None

    def set_score(self, score: dict[str, Any] | None) -> None:
        """Attach a ground-truth grade (see RunRecord.score)."""
        self.rec.score = score

    def fail(self, error: str) -> None:
        self.rec.status = "error"
        self.rec.error = error[:4000]

    def close(self) -> RunRecord:
        if self._closed:
            return self.rec
        self._closed = True
        if self.rec.status == "running":
            self.fail("run closed without finish()")
        self.rec.ended_at = now_iso()
        self.rec.totals.wall_ms = int((time.perf_counter() - self._t0) * 1000)
        if self.transport is not None:
            try:
                self.transport.send(self.rec.model_dump(mode="json"))
            except Exception as e:  # never let telemetry break the agent
                print(f"[downshift] could not send run {self.rec.id}: {e}")
        return self.rec

    def __enter__(self) -> "Run":
        return self

    def __exit__(self, exc_type, exc, tb) -> bool:  # type: ignore[no-untyped-def]
        if exc is not None and self.rec.status == "running":
            self.fail("".join(traceback.format_exception_only(exc_type, exc)).strip())
        self.close()
        return False

    # ---- internals --------------------------------------------------------------------------
    def _add(self, ev: Event) -> None:
        self.rec.events.append(ev)
        t = self.rec.totals
        if isinstance(ev, ModelCallEvent):
            t.model_calls += 1
            t.tokens_in += ev.tokens_in
            t.tokens_out += ev.tokens_out
            t.cost_usd += ev.cost_usd or 0.0
            t.model_latency_ms += ev.latency_ms
        else:
            t.tool_calls += 1
            if ev.source == "recorded":
                t.tool_calls_recorded += 1
            else:
                t.tool_calls_live += 1
            t.tool_latency_ms += ev.latency_ms
        t.latency_ms = t.model_latency_ms + t.tool_latency_ms
