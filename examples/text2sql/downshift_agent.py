"""Downshift adapter for text2sql-framework. This file is the whole integration: text2sql's own code
is not modified.

For one task it:
  1. builds text2sql's own SQLGenerator against the database, as TextSQL does;
  2. sends the agent's model calls through Downshift (run.chat) in place of text2sql's OpenAI client,
     with the system prompt, tool descriptions and model settings taken from harness.yaml;
  3. records every execute_sql call (run.tool), so replays can reuse results for identical queries;
  4. lets text2sql's own tool loop and its own final-SQL extraction and execution run unchanged;
  5. grades the final SQL against the Spider gold SQL with the text2sql author's benchmark rule
     (examples/spider_80_table_run.md): same row count, every gold row's values in a distinct row.

Data: TEXT2SQL_DATA_DIR (default ../_data) holds spider_dev_merged.sqlite and spider_db/<db_id>.sqlite.
"""

from __future__ import annotations

import functools
import inspect
import json
import os
import sqlite3
from collections import Counter
from pathlib import Path
from typing import Any

from downshift import AgentAdapter, Harness, Run, Task, render

# text2sql builds its OpenAI backend when the generator is created; Downshift replaces that backend
# before any call, so the client never needs a real key.
os.environ.setdefault("OPENAI_API_KEY", "unused-calls-go-through-downshift")

from text2sql.connection import Database  # noqa: E402
from text2sql.dialects import get_dialect_guide  # noqa: E402
from text2sql.generate import SYSTEM_PROMPT, SQLGenerator  # noqa: E402
from text2sql.tools import make_tools  # noqa: E402

HERE = Path(__file__).resolve().parent
DATA = Path(os.environ.get("TEXT2SQL_DATA_DIR") or HERE.parent / "_data").resolve()
MERGED_DB = DATA / "spider_dev_merged.sqlite"
STEP = "agent"

CONTRACT = """text2sql's code runs one tool loop: the model calls execute_sql until it replies without a tool call.
The code then extracts the final SQL from that last reply: the SQL must be inside a ```sql code block
(text outside the block is treated as commentary); without a code block it falls back to the text from the
first SELECT/WITH onwards. The SQL must be read-only (SELECT/WITH). The code runs it itself and its rows
are graded against the task's correct result, so the final reply must contain exactly one complete query.
The system prompt may use these placeholders, which the code fills in: {dialect}, {dialect_guide},
{custom_metadata}, {example_tool_note}, {example_list_note}, {instructions}. The step prompt may use {question}."""


def _to_openai(system_prompt: str, few_shot: list[Any], messages: list[Any]) -> list[dict[str, Any]]:
    """text2sql's transcript in OpenAI chat format (as its own OpenAI backend builds it)."""
    out: list[dict[str, Any]] = [{"role": "system", "content": system_prompt}]
    for ex in few_shot:
        out += [{"role": "user", "content": ex.input}, {"role": "assistant", "content": ex.output}]
    for msg in messages:
        if msg.type == "human":
            out.append({"role": "user", "content": msg.content})
        elif msg.type == "ai":
            text = msg.content if isinstance(msg.content, str) else "".join(b.get("text", "") for b in msg.content if isinstance(b, dict))
            entry: dict[str, Any] = {"role": "assistant", "content": text or None}
            if msg.tool_calls:
                entry["tool_calls"] = [{"id": tc["id"], "type": "function", "function": {"name": tc["name"], "arguments": json.dumps(tc["args"])}} for tc in msg.tool_calls]
            out.append(entry)
        elif msg.type == "tool":
            out.append({"role": "tool", "tool_call_id": msg.tool_call_id, "content": msg.content})
    return out


class _DownshiftBackend:
    """Stands in for text2sql's model backend: same generate() contract, calls go through run.chat."""

    def __init__(self, run: Run, harness: Harness):
        self.run = run
        self.harness = harness
        self.step = harness.step(STEP)

    def generate(self, system_prompt: str, tool_schemas: list, messages: list):
        tools = [{"type": "function", "function": {"name": s["name"], "description": (self.harness.tools.get(s["name"]).description if s["name"] in self.harness.tools else s["description"]), "parameters": s["parameters"]}} for s in tool_schemas]
        res = self.run.chat(self.step, _to_openai(system_prompt, self.step.few_shot, messages), tools=tools or None)
        tool_calls = [{"id": tc.id, "name": tc.name, "args": {} if "_unparsed" in tc.arguments else tc.arguments} for tc in res.tool_calls]
        return res.content or "", tool_calls, {"input_tokens": res.tokens_in, "output_tokens": res.tokens_out}


def _recorded(fn: Any, run: Run, budget: int | None, used: list[int]) -> Any:
    """The same tool, with each call recorded by Downshift (and an optional cap on calls)."""

    @functools.wraps(fn)
    def tool(**kwargs: Any) -> Any:
        used[0] += 1
        if budget is not None and used[0] > budget:
            return "Tool budget exhausted: reply now with your final SQL in a ```sql code block."
        return run.tool(fn.__name__, dict(kwargs), lambda: fn(**kwargs), step=STEP)

    return tool


def _norm(v: Any) -> Any:
    if isinstance(v, bool):
        return int(v)
    if isinstance(v, (int, float)):
        return round(float(v), 4)
    if isinstance(v, bytes):
        v = v.decode("utf-8", "replace")
    if isinstance(v, str):
        s = v.strip()
        try:
            return round(float(s), 4)
        except ValueError:
            return s
    return v


def _rows(path: Path, sql: str) -> list[tuple]:
    con = sqlite3.connect(f"file:{path}?mode=ro", uri=True)
    con.text_factory = lambda b: b.decode("utf-8", "replace")
    try:
        return [tuple(_norm(v) for v in row) for row in con.execute(sql).fetchall()]
    finally:
        con.close()


def _author_match(gold: list[tuple], pred: list[tuple]) -> bool:
    if len(gold) != len(pred):
        return False
    used = [False] * len(pred)
    for g in gold:
        need = Counter(g)
        for i, p in enumerate(pred):
            if not used[i] and not (need - Counter(p)):
                used[i] = True
                break
        else:
            return False
    return True


class Text2SQLAgent(AgentAdapter):
    name = "text2sql"
    reuse_tool_results = True  # execute_sql is read-only on a fixed database

    def __init__(self, db_path: Path = MERGED_DB):
        self.db_url = f"sqlite:///{db_path}"

    def run(self, task: Task, harness: Harness, run: Run) -> None:
        gen = SQLGenerator(Database(self.db_url), model="openai:downshift")
        step = harness.step(STEP)
        used = [0]
        tools = [_recorded(fn, run, step.max_tool_calls, used) for fn in gen.tools]
        gen.tools = tools
        gen.agent.tools = tools
        gen.agent._tool_map = {t.__name__: t for t in tools}
        gen.agent.backend = _DownshiftBackend(run, harness)
        if harness.system_prompt != SYSTEM_PROMPT:  # the default is exactly text2sql's own prompt
            dialect = gen.db.dialect
            gen.agent.system_prompt = render(harness.system_prompt, dialect=dialect, dialect_guide=get_dialect_guide(dialect), custom_metadata="", instructions="", example_tool_note="", example_list_note="")
        question = render(step.prompt or "{question}", question=task.input)
        res = gen.ask(question)
        preview = [{k: (v if isinstance(v, (int, float, str)) or v is None else str(v)) for k, v in row.items()} for row in (res.data or [])[:5]]
        run.finish(res.sql or "", [], sql=res.sql, error=res.error, rows=len(res.data or []), preview=preview, commentary=(res.commentary or "")[:500], tool_calls=used[0])

    def score(self, task: Task, output: dict[str, Any]) -> dict[str, Any]:
        exp = task.expected or {}
        gold = _rows(DATA / "spider_db" / f"{exp['db_id']}.sqlite", exp["gold_sql"])
        sql = (output.get("sql") or "").strip()
        if not sql:
            return {"passed": False, "details": f"no SQL: {(output.get('error') or '')[:160]}"}
        try:
            pred = _rows(MERGED_DB, sql)
        except Exception as e:
            return {"passed": False, "details": f"the SQL fails: {type(e).__name__}: {e}"[:200]}
        ok = _author_match(gold, pred)
        if ok:
            return {"passed": True, "details": f"{len(pred)} rows match"}
        # Say how it is wrong without revealing the correct values to the optimizer.
        why = f"expected {len(gold)} rows, got {len(pred)}" if len(gold) != len(pred) else "same row count, different values"
        return {"passed": False, "details": why}

    def default_harness(self) -> Harness:
        # Tool descriptions exactly as text2sql derives them (the tool functions' docstrings).
        tools = {fn.__name__: {"description": inspect.getdoc(fn) or ""} for fn in make_tools(Database("sqlite://"))}
        return Harness.from_dict({
            "name": "text2sql",
            "version": 1,
            "runtime": "custom",
            "description": "text2sql-framework: answers a question about a SQL database by exploring the schema with execute_sql, testing its query, and returning the final SQL.",
            "contract": CONTRACT,
            # text2sql sends no temperature or max_tokens: keep the provider defaults.
            "defaults": {"model": "nemotron-3-ultra", "temperature": None, "max_tokens": None},
            "system_prompt": SYSTEM_PROMPT,
            "tools": tools,
            "steps": [{
                "id": STEP,
                "kind": "tool_loop",
                "description": "The whole agent: explore the schema with execute_sql, write and test the query, then reply with the final SQL in a ```sql block (no tool call).",
                "prompt": "{question}",
            }],
        })


agent = Text2SQLAgent()
