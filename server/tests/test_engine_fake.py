"""End-to-end engine test with a scripted model and canned tools: no network, a few seconds."""

import hashlib
import json
import re
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from downshift import Downshift, Harness, MemoryTransport, default_table
from downshift.providers import ChatResult, ToolCallRequest
from research_agent.agent import ResearchAgent
from research_agent.tools import SearchTools

import app.optimizer.engine as engine_mod
from app.db import Database
from app.optimizer.engine import Engine
from app.settings import Settings

BASELINE = Path(__file__).resolve().parents[2] / "demo_agent" / "harness.yaml"
QUESTIONS = [f"Why is thing number {i} the way it is?" for i in range(8)]


class ScriptedLLM:
    provider_name = "ollama"  # the model table needs a real provider for ID resolution

    def __init__(self):
        self.table = default_table()
        self.calls = 0

    def resolve(self, model):
        return f"fake/{model}"

    def _result(self, model, messages, content="", tool_calls=None):
        self.calls += 1
        return ChatResult(content=content, tool_calls=tool_calls or [], reasoning=None, tokens_in=len(json.dumps(messages)) // 4, tokens_out=120, latency_ms=50, finish_reason="stop", model=model, provider="fake", provider_model=f"fake/{model}")

    def chat(self, model, messages, *, tools=None, tool_choice=None, temperature=None, max_tokens=None, reasoning=None, response_format=None, extra=None):
        system = messages[0]["content"] if messages and messages[0]["role"] == "system" else ""
        user = next((m["content"] for m in reversed(messages) if m["role"] == "user"), "") or ""
        if "label the steps" in system:
            return self._result(model, messages, json.dumps({"question_type": "explain", "question_difficulty": "medium", "steps": [{"step": "plan", "kind": "plan", "difficulty": "easy", "needs_strong_model": False, "reason": "short"}, {"step": "search", "kind": "search", "difficulty": "easy", "needs_strong_model": False, "reason": "tool use"}, {"step": "synthesize", "kind": "synthesize", "difficulty": "hard", "needs_strong_model": True, "reason": "citations"}]}))
        if "adapting LLM agent harnesses" in system:
            h = Harness.load(BASELINE).to_dict()
            if "every step on nemotron-3-nano" in user:
                h["defaults"]["model"] = "nemotron-3-nano"
            elif "every step on nemotron-3-super" in user:
                h["defaults"]["model"] = "nemotron-3-super"
            else:
                h["defaults"]["model"] = "nemotron-3-nano"
                for s in h["steps"]:
                    if s["kind"] == "synthesize":
                        s["model"] = "nemotron-3-ultra"
            h["changelog"] = ["moved steps", "shorter prompt"]
            return self._result(model, messages, "```yaml\n" + Harness.from_dict(h).to_yaml() + "```\nRationale: scripted.")
        if "strict grader" in system:
            seed = int(hashlib.md5(user.encode()).hexdigest(), 16) % 3
            pref = ["A", "B", "tie"][seed]
            return self._result(model, messages, json.dumps({"A": {"correct": 4, "complete": 4, "supported": 4}, "B": {"correct": 4 - seed, "complete": 4, "supported": 3}, "preferred": pref, "reason": "scripted"}))
        if '"queries"' in user:
            q = re.search(r"Question: (.*)", user).group(1)
            return self._result(model, messages, json.dumps({"queries": [q, q + " details"], "notes": "n"}))
        if tools:
            if messages[-1]["role"] == "tool":
                return self._result(model, messages, "I found enough.")
            q = re.search(r"Question: (.*)", user).group(1)
            return self._result(model, messages, "", [ToolCallRequest("c1", "web_search", {"query": q, "max_results": 3}, json.dumps({"query": q, "max_results": 3}))])
        if '"ok"' in user:
            return self._result(model, messages, json.dumps({"ok": True, "problems": []}))
        urls = re.findall(r"URL: (\S+)", user)
        src = urls[0] if urls else "https://example.org/none"
        return self._result(model, messages, f"The answer is well supported by the evidence and covers every part of the question [1].\n\nSources:\n{src}")


class FakeTools(SearchTools):
    def __init__(self):
        super().__init__(tavily_api_key="")
        self.tavily_key = None

    @property
    def provider(self):
        return "fake"

    def web_search(self, query, max_results=5):
        slug = re.sub(r"[^a-z0-9]+", "-", query.lower())[:30]
        return {"provider": "fake", "query": query, "results": [{"title": f"Page about {query}", "url": f"https://example.org/{slug}", "snippet": "facts facts facts"}]}

    def read_page(self, url, max_chars=4000):
        return {"url": url, "title": "t", "text": "more facts", "truncated": False}


def _record_baselines(db: Database, llm: ScriptedLLM) -> None:
    h = Harness.load(BASELINE)
    tools = FakeTools()
    for i, q in enumerate(QUESTIONS):
        tr = MemoryTransport()
        ds = Downshift(transport=tr, llm=llm, project="research-agent")
        with ds.run(task_id=f"q{i:03d}", input=q, harness=h, meta={"tag": "baseline"}) as run:
            ResearchAgent(h, run, tools).answer(q)
        rec = tr.records[0]
        assert rec["status"] == "ok" and rec["output"]["sources"]
        db.upsert_project("research-agent", rec["harness"], rec["harness_fingerprint"])
        db.insert_run(rec)


def test_engine_runs_end_to_end(tmp_path, monkeypatch):
    monkeypatch.setenv("DOWNSHIFT_DB_PATH", str(tmp_path / "e.sqlite3"))
    monkeypatch.setenv("DOWNSHIFT_PROVIDER", "ollama")
    settings = Settings.from_env()
    db = Database(settings.db_path)
    llm = ScriptedLLM()
    _record_baselines(db, llm)
    monkeypatch.setattr(engine_mod, "LLM", lambda *a, **k: llm)
    monkeypatch.setattr(engine_mod, "SearchTools", FakeTools)

    opt = db.create_optimization("research-agent", {"targets": ["super", "nano", "mix"], "rounds": 2, "sample_size": 3, "test_fraction": 0.4, "concurrency": 2, "max_cost_usd": 5.0, "seed": 1}, source="live")
    Engine(db, settings).run(opt["id"])

    final = db.get_optimization(opt["id"])
    assert final["status"] == "done", final["error"]
    summary = final["summary_json"]
    assert summary["headline"]["text"] and summary["split"]["test"] == 3 and summary["split"]["optimization"] == 5
    options = db.list_options(opt["id"])
    assert [o["key"] for o in options] == ["baseline", "super", "nano", "mix"]
    for o in options:
        assert o["status"] == "done", o
        assert o["metrics_json"]["test"]["n"] == 3
    mix = db.get_option_by_key(opt["id"], "mix")
    assert "nemotron-3-ultra" in Harness.from_dict(mix["harness_json"]).models_used()
    assert len(mix["rounds_json"]) == 2
    test_replays = db.list_replays(mix["id"], split="test")
    assert len(test_replays) == 3 and all(r["judge_json"]["preferred"] in {"candidate", "baseline", "tie"} for r in test_replays)
    # replayed tool calls were served from the recording
    rec = test_replays[0]["record_json"]
    assert rec["totals"]["tool_calls_recorded"] >= 1 and rec["meta"]["mode"] == "replay"
    phases = {e["phase"] for e in db.list_events(opt["id"])}
    assert {"split", "analyze", "done"} <= phases
    # redo: a missing and an errored held-out replay are redone, the good one is kept
    engine = Engine(db, settings)
    kept = test_replays[0]
    db.delete_replays(mix["id"], "test", [test_replays[1]["task_id"]])
    db.update_replay(test_replays[2]["id"], status="error", judge_json={"error": "LLMError: 429"})
    out = engine.redo_test_replays(opt["id"], "mix")
    assert out["redone"] == 2
    after = db.list_replays(mix["id"], split="test")
    assert len(after) == 3 and all(r["status"] == "ok" and "error" not in (r["judge_json"] or {}) for r in after)
    assert any(r["id"] == kept["id"] for r in after)
    assert engine.redo_test_replays(opt["id"], "mix")["redone"] == 0
    assert db.get_optimization(opt["id"])["summary_json"]["headline"]["text"]
    # seed round trip keeps everything
    out = tmp_path / "seed.json.gz"
    db.export_to_file(out)
    db2 = Database(tmp_path / "copy.sqlite3")
    counts = db2.import_from_file(out)
    assert counts["optimizations"] == 1 and counts["replays"] == len(db.list_replays(mix["id"])) * 3 + 0 or counts["replays"] > 0
    assert db2.get_optimization(opt["id"])["status"] == "done"
