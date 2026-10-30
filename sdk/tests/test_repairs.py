"""Runtime repairs declared on a step: a final-format re-ask and recovery of tool calls written as text."""

from downshift import Harness, Run, default_table
from downshift.providers import ChatResult
from downshift.tracing import recover_tool_calls

TOOLS = [{"type": "function", "function": {"name": "execute_sql", "description": "run SQL", "parameters": {"type": "object", "properties": {"sql": {"type": "string"}}}}}]


class ScriptLLM:
    provider_name = "ollama"

    def __init__(self, replies):
        self.replies = list(replies)
        self.calls = []

    def resolve(self, model):
        return model

    def chat(self, model, messages, **kw):
        self.calls.append({"messages": messages, **kw})
        content = self.replies.pop(0)
        return ChatResult(content=content, tool_calls=[], reasoning=None, tokens_in=10, tokens_out=5, latency_ms=1, finish_reason="stop", model=model, provider="ollama", provider_model=model)


def _run(llm, **step):
    h = Harness.from_dict({
        "name": "t", "version": 1, "runtime": "custom", "description": "", "system_prompt": "s", "tools": {},
        "defaults": {"model": "nemotron-3-nano", "temperature": None, "max_tokens": None},
        "steps": [{"id": "agent", "kind": "tool_loop", **step}],
    })
    return Run(project="p", task_id="t", input="q", harness=h, llm=llm, table=default_table())


def test_final_format_reasks_once_without_tools_and_returns_the_fixed_reply():
    llm = ScriptLLM(["The answer is **Japan**.", "```sql\nSELECT 1\n```"])
    run = _run(llm, final_format=r"```sql", repair_prompt="Reply with only the SQL in a ```sql block.")
    res = run.chat("agent", [{"role": "user", "content": "q"}], tools=TOOLS)
    assert res.content.startswith("```sql")
    assert len(llm.calls) == 2 and llm.calls[1]["tools"] is None
    assert llm.calls[1]["messages"][-1]["content"] == "Reply with only the SQL in a ```sql block."
    assert llm.calls[1]["messages"][-2] == {"role": "assistant", "content": "The answer is **Japan**."}
    events = [e for e in run.rec.events if e.type == "model_call"]
    assert [e.note for e in events] == [None, "repair"]
    assert run.rec.totals.model_calls == 2  # the repair is counted and costed


def test_no_repair_when_the_format_is_there_or_not_declared():
    llm = ScriptLLM(["```sql\nSELECT 1\n```"])
    _run(llm, final_format=r"```sql").chat("agent", [{"role": "user", "content": "q"}], tools=TOOLS)
    assert len(llm.calls) == 1
    llm = ScriptLLM(["prose answer"])
    _run(llm).chat("agent", [{"role": "user", "content": "q"}], tools=TOOLS)
    assert len(llm.calls) == 1


def test_text_tool_calls_are_recovered_for_offered_tools_only():
    xml = "<tool_call>\n<function=execute_sql>\n<parameter=sql>\nSELECT name FROM t\n</parameter>\n</function>\n</tool_call>"
    calls = recover_tool_calls(xml, ["execute_sql"])
    assert len(calls) == 1 and calls[0].name == "execute_sql" and calls[0].arguments == {"sql": "SELECT name FROM t"}
    js = 'I will run it: {"tool": "execute_sql", "args": {"sql": "SELECT 1"}} then {"name": "drop_db", "arguments": {}}'
    calls = recover_tool_calls(js, ["execute_sql"])
    assert [c.name for c in calls] == ["execute_sql"] and calls[0].arguments == {"sql": "SELECT 1"}
    assert recover_tool_calls("plain prose {\"a\": 1}", ["execute_sql"]) == []


def test_recovery_in_run_chat_is_opt_in_and_noted():
    xml = "<tool_call><function=execute_sql><parameter=sql>SELECT 1</parameter></function></tool_call>"
    llm = ScriptLLM([xml])
    res = _run(llm, recover_tool_calls=True).chat("agent", [{"role": "user", "content": "q"}], tools=TOOLS)
    assert res.tool_calls and res.tool_calls[0].arguments == {"sql": "SELECT 1"} and res.content == ""
    llm = ScriptLLM([xml])
    res = _run(llm).chat("agent", [{"role": "user", "content": "q"}], tools=TOOLS)
    assert not res.tool_calls


def test_changelog_entries_that_are_not_text_are_kept_as_text():
    h = Harness.from_dict({
        "name": "t", "version": 1, "runtime": "custom", "description": "", "system_prompt": "s", "tools": {},
        "defaults": {"model": "nemotron-3-nano"}, "steps": [{"id": "agent", "kind": "tool_loop"}],
        "changelog": ["ok", {"rule": "added"}],
    })
    assert h.changelog == ["ok", '{"rule": "added"}']
