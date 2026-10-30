"""The proxy serves the OpenAI chat API in front of a run: harness applied, every call recorded."""

import openai

from downshift import Harness, Run, default_table
from downshift.providers import ChatResult, ToolCallRequest
from downshift.proxy import ChatProxy, apply_harness


class LLM:
    provider_name = "ollama"

    def __init__(self):
        self.seen = []

    def resolve(self, model):
        return model

    def chat(self, model, messages, **kw):
        self.seen.append({"model": model, "messages": messages, **kw})
        if kw.get("tools") and messages[-1]["role"] == "user":
            return ChatResult(content="", tool_calls=[ToolCallRequest("c1", "lookup", {"id": 7}, '{"id": 7}')], reasoning=None, tokens_in=30, tokens_out=8, latency_ms=1, finish_reason="tool_calls", model=model, provider="ollama", provider_model=model)
        return ChatResult(content="Done.", tool_calls=[], reasoning=None, tokens_in=40, tokens_out=3, latency_ms=1, finish_reason="stop", model=model, provider="ollama", provider_model=model)


def _harness(system_prompt="Be brief.\n{original_system_prompt}"):
    return Harness.from_dict({
        "name": "p", "version": 1, "runtime": "custom", "description": "", "system_prompt": system_prompt,
        "tools": {"lookup": {"description": "Look up an order by id (harness text)."}},
        "defaults": {"model": "nemotron-3-super", "temperature": 0.3, "max_tokens": None},
        "steps": [{"id": "agent", "kind": "tool_loop"}],
    })


TOOLS = [{"type": "function", "function": {"name": "lookup", "description": "agent text", "parameters": {"type": "object", "properties": {"id": {"type": "integer"}}}}}]


def test_apply_harness_wraps_the_agents_system_prompt_and_tool_descriptions():
    msgs, tools = apply_harness(_harness(), [{"role": "system", "content": "POLICY"}, {"role": "user", "content": "hi"}], TOOLS)
    assert msgs[0]["content"] == "Be brief.\nPOLICY"
    assert tools[0]["function"]["description"] == "Look up an order by id (harness text)."
    assert TOOLS[0]["function"]["description"] == "agent text"  # the agent's request is not mutated
    msgs, _ = apply_harness(_harness("Extra rule."), [{"role": "system", "content": "POLICY"}], None)
    assert msgs[0]["content"] == "POLICY\n\nExtra rule."


def test_openai_client_through_the_proxy_records_calls_with_harness_settings():
    llm = LLM()
    run = Run(project="p", task_id="t", input="q", harness=_harness(), llm=llm, table=default_table())
    with ChatProxy(run, run.harness) as px:
        client = openai.OpenAI(base_url=px.base_url, api_key="unused")
        r1 = client.chat.completions.create(model="whatever-the-agent-says", temperature=1.0, messages=[{"role": "system", "content": "POLICY"}, {"role": "user", "content": "order 7?"}], tools=TOOLS)
        assert r1.choices[0].message.tool_calls[0].function.name == "lookup"
        r2 = client.chat.completions.create(model="x", messages=[{"role": "system", "content": "POLICY"}, {"role": "user", "content": "order 7?"}, {"role": "assistant", "content": None, "tool_calls": [{"id": "c1", "type": "function", "function": {"name": "lookup", "arguments": '{"id": 7}'}}]}, {"role": "tool", "tool_call_id": "c1", "content": "shipped"}], tools=TOOLS)
        assert r2.choices[0].message.content == "Done." and r2.usage.completion_tokens == 3
    assert px.calls == 2 and not px.errors
    assert [s["model"] for s in llm.seen] == ["nemotron-3-super", "nemotron-3-super"]  # the harness picks the model
    assert llm.seen[0]["temperature"] == 0.3 and llm.seen[0]["messages"][0]["content"] == "Be brief.\nPOLICY"
    assert run.rec.totals.model_calls == 2 and run.rec.totals.tokens_in == 70
