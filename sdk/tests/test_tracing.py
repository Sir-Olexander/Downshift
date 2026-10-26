from pathlib import Path

import pytest

from downshift import Harness, MemoryTransport, ReplayRun, Run, default_table
from downshift.providers import ChatResult, ToolCallRequest

BASELINE = Path(__file__).resolve().parents[2] / "demo_agent" / "harness.yaml"


class FakeLLM:
    provider_name = "fake"

    def __init__(self):
        self.calls = []

    def resolve(self, model):
        return f"fake/{model}"

    def chat(self, model, messages, **kw):
        self.calls.append((model, kw))
        return ChatResult(content="hello", tool_calls=[ToolCallRequest("c1", "web_search", {"query": "x"}, '{"query":"x"}')], reasoning=None, tokens_in=1000, tokens_out=500, latency_ms=42, finish_reason="stop", model=model, provider="fake", provider_model=f"fake/{model}")


def _run(**kw):
    h = Harness.load(BASELINE)
    return Run(project="p", task_id="t", input="q", harness=h, llm=FakeLLM(), table=default_table(), **kw)


def test_run_records_model_and_tool_calls_with_costs():
    tr = MemoryTransport()
    with _run(transport=tr) as run:
        res = run.chat("plan", [{"role": "user", "content": "hi"}])
        assert res.tool_calls[0].name == "web_search"
        out = run.tool("web_search", {"query": "x"}, lambda: {"results": []}, step="search")
        assert out == {"results": []}
        run.finish("answer", ["https://a"])
    rec = tr.records[0]
    assert rec["status"] == "ok"
    assert rec["totals"]["model_calls"] == 1 and rec["totals"]["tool_calls"] == 1
    assert rec["totals"]["cost_usd"] == pytest.approx(0.0025)  # 1000 in, 500 out on ultra
    assert rec["events"][0]["params"]["max_tokens"] == 400
    assert rec["totals"]["latency_ms"] >= 42


def test_exception_marks_run_as_error():
    tr = MemoryTransport()
    with pytest.raises(RuntimeError):
        with _run(transport=tr):
            raise RuntimeError("boom")
    assert tr.records[0]["status"] == "error" and "boom" in tr.records[0]["error"]


def test_replay_serves_recorded_results_and_flags_live_calls():
    tr = MemoryTransport()
    with _run(transport=tr) as run:
        run.tool("web_search", {"query": "Rosetta Stone discovery"}, lambda: {"results": [1]})
        run.finish("a")
    recorded = tr.records[0]
    h = Harness.load(BASELINE)
    rr = ReplayRun(recorded=recorded, project="p", task_id="t", input="q", harness=h, llm=FakeLLM(), table=default_table(), transport=None)
    assert rr.tool("web_search", {"query": "discovery of the rosetta stone"}, lambda: {"results": ["live"]}) == {"results": [1]}
    assert rr.tool("web_search", {"query": "unrelated thing"}, lambda: {"results": ["live"]}) == {"results": ["live"]}
    rr.finish("b")
    rec = rr.close()
    assert rec.totals.tool_calls_recorded == 1 and rec.totals.tool_calls_live == 1
    assert rec.meta["mode"] == "replay" and rec.meta["replay_of"] == recorded["id"]
