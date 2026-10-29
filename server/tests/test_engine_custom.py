"""End-to-end engine test for an agent Downshift did not build: its own code runs every replay (in a
subprocess, through its adapter) and runs are scored against each task's correct answer.
No network: the toy agent makes no model calls and the optimizer's own model calls are scripted."""

import json
import re
import sys
from pathlib import Path

import yaml

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
sys.path.insert(0, str(Path(__file__).resolve().parents[2] / "sdk" / "tests"))

import app.optimizer.engine as engine_mod
from app.db import Database
from app.optimizer.engine import Engine
from app.optimizer.rewrite import _check_custom
from app.settings import Settings
from downshift import Downshift, Harness, MemoryTransport, default_table
from downshift.adapter import load_adapter, load_tasks
from downshift.providers import ChatResult
from downshift.runner import _run_one
from research_agent.tools import SearchTools
from test_adapter import CUSTOM, make_agent_folder


class ScriptedLLM:
    provider_name = "ollama-local"

    def __init__(self):
        self.table = default_table()
        self.judge_calls = 0
        self.rewrites = 0

    def resolve(self, model):
        return f"fake/{model}"

    def _result(self, model, content):
        return ChatResult(content=content, tool_calls=[], reasoning=None, tokens_in=500, tokens_out=100, latency_ms=10, finish_reason="stop", model=model, provider="fake", provider_model=f"fake/{model}")

    def chat(self, model, messages, **kw):
        system = messages[0]["content"]
        user = messages[1]["content"] if len(messages) > 1 else ""
        if "label the steps" in system:
            return self._result(model, json.dumps({"question_type": "lookup", "question_difficulty": "easy", "steps": [{"step": "answer", "kind": "tool_loop", "difficulty": "easy", "needs_strong_model": False, "reason": "one lookup"}]}))
        if "strict grader" in system:
            self.judge_calls += 1
            return self._result(model, "{}")
        if "adapting LLM agent harnesses" in system:
            self.rewrites += 1
            assert "The agent's steps" in user and "Contract" in user  # the custom-runtime prompt
            h = yaml.safe_load(re.search(r"```yaml\n(.*?)```", user, re.DOTALL).group(1))
            retrying = any("That harness is invalid" in (m.get("content") or "") for m in messages)
            if "every step on nemotron-3-nano" in user:
                h["defaults"]["model"] = "nemotron-3-nano"
                if not retrying:  # first try breaks the structure; the rewriter must reject it
                    h["steps"][0]["id"] = "renamed"
                h["system_prompt"] = "ANSWER IN CAPS. " + h["system_prompt"]
                h["contract"] = "something else"  # must be restored from the baseline
            else:
                h["defaults"]["model"] = "nemotron-3-super"
            h["changelog"] = ["scripted"]
            return self._result(model, "```yaml\n" + yaml.safe_dump(h, sort_keys=False) + "```\nRationale: scripted.")
        raise AssertionError(f"unexpected model call: {system[:80]}")


class NoSearch(SearchTools):
    def __init__(self):
        super().__init__(tavily_api_key="")

    def web_search(self, query, max_results=5):
        return {"provider": "none", "results": []}


def test_check_custom_keeps_the_agent_structure():
    cur = Harness.from_dict(CUSTOM)
    renamed = Harness.from_dict({**CUSTOM, "steps": [{"id": "other", "kind": "tool_loop"}]})
    try:
        _check_custom(renamed, cur)
        raise AssertionError("a renamed step must be rejected")
    except ValueError as e:
        assert "steps must stay" in str(e)
    changed = Harness.from_dict({**CUSTOM, "contract": "nope", "name": "x", "system_prompt": "new", "steps": [{"id": "answer", "kind": "tool_loop"}]})
    fixed = _check_custom(changed, cur)
    assert fixed.contract == cur.contract and fixed.name == "toy" and fixed.system_prompt == "new" and fixed.steps[0].description == cur.steps[0].description


def test_engine_optimizes_an_external_agent_against_ground_truth(tmp_path, monkeypatch):
    monkeypatch.setenv("DOWNSHIFT_DB_PATH", str(tmp_path / "e.sqlite3"))
    monkeypatch.setenv("DOWNSHIFT_PROVIDER", "ollama-local")
    monkeypatch.setenv("DOWNSHIFT_ALLOW_FS", "true")
    monkeypatch.setenv("DOWNSHIFT_AGENTS_ROOT", str(tmp_path))
    settings = Settings.from_env()
    db = Database(settings.db_path)
    folder = make_agent_folder(tmp_path)

    # baseline: the agent's own code, recorded and graded
    adapter = load_adapter(folder)
    ds = Downshift(transport=MemoryTransport(), provider="ollama-local", project="toy")
    h = Harness.load(folder / "harness.yaml")
    for task in load_tasks(folder / "tasks.jsonl"):
        rec = _run_one(ds, adapter, h, task, {"tag": "baseline"})
        assert rec["score"]["passed"]
        db.upsert_project("toy", rec["harness"], rec["harness_fingerprint"])
        db.insert_run(rec)

    llm = ScriptedLLM()
    monkeypatch.setattr(engine_mod, "LLM", lambda *a, **k: llm)
    monkeypatch.setattr(engine_mod, "SearchTools", NoSearch)

    # without a registered folder the engine refuses to guess where the agent's code is
    opt = db.create_optimization("toy", {"targets": ["super", "nano"], "rounds": 1, "sample_size": 3, "test_fraction": 0.5, "concurrency": 2, "max_cost_usd": 5.0, "seed": 3}, source="live")
    Engine(db, settings).run(opt["id"])
    failed = db.get_optimization(opt["id"])
    assert failed["status"] == "failed" and "no agent folder is registered" in failed["error"]

    db.upsert_agent("toy", "toy", str(folder))
    opt = db.create_optimization("toy", {"targets": ["super", "nano"], "rounds": 1, "sample_size": 3, "test_fraction": 0.5, "concurrency": 2, "max_cost_usd": 5.0, "seed": 3}, source="live")
    engine = Engine(db, settings)
    engine.run(opt["id"])
    final = db.get_optimization(opt["id"])
    assert final["status"] == "done", final["error"]
    summary = final["summary_json"]
    assert summary["scoring"] == "ground_truth" and summary["runtime"] == "custom" and summary["judge"]["model"] is None
    assert llm.judge_calls == 0  # ground truth: no LLM judge at all
    assert summary["baseline"]["success_rate"] == 100.0
    rows = {r["key"]: r for r in summary["options"]}
    assert rows["nano"]["metrics"]["success_rate"] == 100.0 and rows["nano"]["meets_bar"]
    assert rows["super"]["metrics"]["success_rate"] == 0.0 and not rows["super"]["meets_bar"]
    assert summary["headline"]["recommended"] == "nano"

    nano = db.get_option_by_key(opt["id"], "nano")
    nh = Harness.from_dict(nano["harness_json"])
    assert nh.runtime == "custom" and nh.contract == CUSTOM["contract"] and [s.id for s in nh.steps] == ["answer"]
    assert nano["rounds_json"][0]["kind"] == "model_swap" and nano["rounds_json"][0]["metrics"]["success_rate"] == 0.0  # the swap alone fails here
    assert nano["rounds_json"][1]["rewrite_usage"]["attempts"] == 2  # the renamed step was rejected
    reps = db.list_replays(nano["id"], split="test")
    assert len(reps) == 3
    for r in reps:
        assert r["judge_json"]["method"] == "ground_truth" and r["judge_json"]["candidate"]["passed"]
        assert r["record_json"]["meta"]["mode"] == "replay" and r["record_json"]["totals"]["tool_calls_recorded"] == 1
        assert r["checks_json"]["candidate"]["ground_truth"] is True and "has_sources" not in r["checks_json"]["candidate"]

    # redo and resummarize work for external agents too
    db.delete_replays(nano["id"], "test", [reps[0]["task_id"]])
    out = engine.redo_test_replays(opt["id"], "nano")
    assert out["redone"] == 1 and out["summary"]["scoring"] == "ground_truth"
    assert engine.resummarize(opt["id"])["options"][1]["metrics"]["success_rate"] == 100.0

    # several replays per held-out task, the plain swap on the same held-out tasks, paired statistics and a
    # verdict instead of the one-run rule; then fresh runs after the fact
    opt2 = db.create_optimization("toy", {"targets": ["nano"], "rounds": 1, "sample_size": 3, "test_fraction": 0.5, "concurrency": 2, "max_cost_usd": 5.0, "seed": 3, "test_trials": 2, "race_size": 2, "race_trials": 1}, source="live")
    engine.run(opt2["id"])
    final2 = db.get_optimization(opt2["id"])
    assert final2["status"] == "done", final2["error"]
    n_test = len(final2["split_json"]["test"])
    nano2 = db.get_option_by_key(opt2["id"], "nano")
    assert len(db.list_replays(nano2["id"], split="test")) == 2 * n_test
    assert len(db.list_replays(nano2["id"], split="test_swap")) == 2 * n_test  # the swap, paired on the held-out tasks
    stats = nano2["metrics_json"]["stats"]
    assert stats["n_tasks"] == n_test and stats["trials"] == 2 and stats["pass1"] == 100.0 and stats["passk"] == 100.0
    assert stats["verdict"] == "non_inferior" and nano2["metrics_json"]["meets_bar"]
    assert stats["delta_vs_swap"]["pp"] == 100.0 and stats["vs_swap"] == "better"  # the swap alone fails every task here
    row = {r["key"]: r for r in final2["summary_json"]["options"]}["nano"]
    assert row["verdict"] == "non_inferior" and "paired" in final2["summary_json"]["bar"]["note"]
    assert any("statistics:" in n for n in final2["summary_json"]["notes"])
    out = engine.verify(opt2["id"], trials=1)
    labels = [a["key"] for a in out["arms"]]
    assert labels == ["baseline", "nano", "nano-swap"]
    assert out["arms"][1]["passes_per_trial"] == [n_test] and out["arms"][1]["claimed_success_rate"] == 100.0
    assert out["arms"][2]["passes_per_trial"] == [0]
    assert len(db.list_replays(nano2["id"], split="verify")) == n_test  # the chosen harness; baseline and swap arms sit under the baseline option
    assert len(db.list_replays(db.get_option_by_key(opt2["id"], "baseline")["id"], split="verify")) == 2 * n_test


def test_api_refuses_a_custom_project_without_an_agent_folder(client):
    rec = {"id": "r1", "project": "toy", "task_id": "t1", "input": "x", "harness": Harness.from_dict(CUSTOM).to_dict(), "harness_fingerprint": "f", "started_at": "2026-10-29T00:00:00Z", "status": "ok", "output": {"answer": ""}, "score": {"passed": False, "score": 0.0}, "events": [], "totals": {}, "meta": {"tag": "baseline", "mode": "record"}}
    for i in range(4):
        r = client.post("/v1/runs", json={**rec, "id": f"r{i}", "task_id": f"t{i}"}, headers={"Authorization": "Bearer test-key"})
        assert r.status_code == 201
    r = client.post("/v1/optimizations", json={"project_id": "toy", "targets": ["nano"]})
    assert r.status_code == 400 and "no agent folder is registered" in r.json()["detail"]


def test_rewriter_reply_with_code_fences_inside_the_yaml():
    from app.optimizer.rewrite import _extract_yaml
    h = Harness.from_dict({**CUSTOM, "contract": "Reply with the SQL inside a ```sql code block.", "system_prompt": "End with:\n```sql\nSELECT 1\n```\nand nothing else."})
    reply = "Here it is:\n```yaml\n" + h.to_yaml() + "```\nRationale: kept the contract."
    assert Harness.from_yaml(_extract_yaml(reply)).fingerprint() == h.fingerprint()


def test_few_shot_must_not_write_tool_calls_as_text():
    from app.optimizer.rewrite import _check_few_shot
    ok = Harness.from_dict({**CUSTOM, "steps": [{"id": "answer", "kind": "tool_loop", "few_shot": [{"input": "q", "output": "Final: ALPHA (found with the lookup tool)"}]}]})
    _check_few_shot(ok)
    for bad in ('{"tool": "lookup", "args": {"key": "x"}}', 'lookup(key="x")', '{"name": "lookup", "arguments": {}}'):
        h = Harness.from_dict({**CUSTOM, "steps": [{"id": "answer", "kind": "tool_loop", "few_shot": [{"input": "q", "output": bad}]}]})
        try:
            _check_few_shot(h)
            raise AssertionError(f"accepted {bad}")
        except ValueError as e:
            assert "tool call as text" in str(e)


def test_a_stalled_runner_is_stopped_and_its_replays_marked_as_errors(tmp_path, monkeypatch):
    import app.optimizer.external as ext
    folder = make_agent_folder(tmp_path)
    module = (folder / "downshift.yaml").read_text().split(":")[1].strip()
    src = (folder / f"{module}.py").read_text().replace('print("agent noise on stdout")', 'import time; time.sleep(30)')
    (folder / f"{module}.py").write_text(src)
    monkeypatch.setattr(ext, "IDLE_TIMEOUT_S", 2.0)
    base = {"id": "b1", "project": "toy", "task_id": "t1", "input": "alpha", "events": [], "meta": {"expected": "ALPHA"}}
    out = ext.ExternalAgent(folder, "ollama-local").replay_many(Harness.from_dict(CUSTOM), [base], concurrency=1)
    assert len(out) == 1 and out[0]["status"] == "error" and "was stopped" in out[0]["error"]
