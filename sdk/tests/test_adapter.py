"""Custom-runtime harnesses, adapters and the runner (no model calls, no network)."""

import json
import subprocess
import sys
import uuid
from pathlib import Path

import pytest
from downshift import Downshift, Harness, HarnessError, MemoryTransport
from downshift.adapter import Task, load_adapter, load_tasks
from downshift.runner import _run_one

CUSTOM = {
    "name": "toy",
    "runtime": "custom",
    "contract": "Answer with the value in capital letters.",
    "defaults": {"model": "nemotron-3-ultra", "temperature": None, "max_tokens": None},
    "system_prompt": "You look things up.",
    "tools": {"lookup": {"description": "Look a key up."}},
    "steps": [{"id": "answer", "kind": "tool_loop", "description": "Look the key up and answer."}],
}

ADAPTER = '''
from downshift import AgentAdapter, Harness

class Toy(AgentAdapter):
    name = "toy"

    def run(self, task, harness, run):
        print("agent noise on stdout")  # must not break the runner protocol
        p = harness.params("answer")
        found = run.tool("lookup", {"key": task.input}, lambda: {"value": task.input.upper()}, step="answer")
        good = p.model == "nemotron-3-ultra" or "ANSWER IN CAPS" in harness.system_prompt
        run.finish(found["value"] if good else task.input.lower())

    def score(self, task, output):
        ok = output.get("answer") == task.expected
        return {"passed": ok, "details": "match" if ok else "got " + repr(output.get("answer"))}

    def default_harness(self):
        return Harness.from_dict(HARNESS)

HARNESS = __HARNESS__
agent = Toy()
'''


def make_agent_folder(root: Path) -> Path:
    folder = root / "toy-agent"
    folder.mkdir()
    module = f"toy_agent_{uuid.uuid4().hex[:8]}"
    (folder / f"{module}.py").write_text(ADAPTER.replace("__HARNESS__", repr(CUSTOM)))
    (folder / "downshift.yaml").write_text(f"entry: {module}:agent\n")
    (folder / "tasks.jsonl").write_text("\n".join(json.dumps({"id": f"t{i}", "input": w, "expected": w.upper()}) for i, w in enumerate(["alpha", "beta", "gamma", "delta", "eps", "zeta"])) + "\n")
    Harness.from_dict(CUSTOM).save(folder / "harness.yaml")
    return folder


def test_custom_harness_allows_any_step_kind_and_tools():
    h = Harness.from_dict(CUSTOM)
    assert h.is_custom and h.steps[0].kind == "tool_loop" and list(h.tools) == ["lookup"]
    # null temperature / max_tokens mean "provider default" and survive a YAML round trip
    again = Harness.from_yaml(h.to_yaml())
    assert again.defaults.temperature is None and again.defaults.max_tokens is None
    assert again.fingerprint() == h.fingerprint() and again.params("answer").temperature is None


def test_research_harness_still_requires_research_steps():
    bad = {**CUSTOM, "runtime": "research"}
    with pytest.raises(HarnessError, match="research harness step kinds"):
        Harness.from_dict(bad)
    research = Harness.load(Path(__file__).resolve().parents[2] / "demo_agent" / "harness.yaml")
    assert research.runtime == "research" and "runtime" not in research.to_dict()


def test_replay_can_run_every_tool_live():
    h = Harness.from_dict(CUSTOM)
    recorded = {"id": "r1", "task_id": "t1", "input": "x", "events": [{"type": "tool_call", "name": "lookup", "args": {"key": "x"}, "result": {"value": "OLD"}, "latency_ms": 5}]}
    ds = Downshift(transport=MemoryTransport(), provider="ollama-local")
    with ds.replay(recorded=recorded, harness=h) as run:
        assert run.tool("lookup", {"key": "x"}, lambda: {"value": "NEW"}) == {"value": "OLD"}
    with ds.replay(recorded=recorded, harness=h, reuse_tool_results=False) as run:
        assert run.tool("lookup", {"key": "x"}, lambda: {"value": "NEW"}) == {"value": "NEW"}
        assert run.record.totals.tool_calls_live == 1


def test_record_grades_against_the_expected_answer(tmp_path):
    folder = make_agent_folder(tmp_path)
    adapter = load_adapter(folder)
    tasks = load_tasks(folder / "tasks.jsonl")
    assert tasks[0] == Task(id="t0", input="alpha", expected="ALPHA", meta={})
    tr = MemoryTransport()
    ds = Downshift(transport=tr, provider="ollama-local", project="toy")
    rec = _run_one(ds, adapter, Harness.from_dict(CUSTOM), tasks[0], {"tag": "baseline"})
    assert rec["status"] == "ok" and rec["score"]["passed"] and rec["score"]["grader"] == "toy"
    assert rec["meta"]["expected"] == "ALPHA" and tr.records[0]["score"]["passed"]
    nano = Harness.from_dict({**CUSTOM, "defaults": {**CUSTOM["defaults"], "model": "nemotron-3-nano"}})
    rec = _run_one(ds, adapter, nano, tasks[1], {})
    assert rec["status"] == "ok" and rec["score"] == {"passed": False, "score": 0.0, "details": "got 'beta'", "grader": "toy"}


def test_runner_replay_protocol_runs_the_agent_in_its_own_process(tmp_path):
    folder = make_agent_folder(tmp_path)
    adapter = load_adapter(folder)
    ds = Downshift(transport=MemoryTransport(), provider="ollama-local", project="toy")
    tasks = load_tasks(folder / "tasks.jsonl")[:3]
    baseline = [_run_one(ds, adapter, Harness.from_dict(CUSTOM), t, {"tag": "baseline"}) for t in tasks]
    cand = {**CUSTOM, "system_prompt": "ANSWER IN CAPS. You look things up.", "defaults": {**CUSTOM["defaults"], "model": "nemotron-3-nano"}}
    job = {"harness": cand, "records": baseline, "meta": {"split": "test"}, "provider": "ollama-local", "concurrency": 2}
    proc = subprocess.run([sys.executable, "-m", "downshift.runner", "replay", "--folder", str(folder)], input=json.dumps(job), capture_output=True, text=True, cwd=str(folder), timeout=120)
    assert proc.returncode == 0, proc.stderr
    assert "agent noise on stdout" in proc.stderr  # the agent's prints went to stderr
    lines = [json.loads(line) for line in proc.stdout.splitlines()]
    assert sorted(x["index"] for x in lines) == [0, 1, 2]
    for x in lines:
        rec = x["record"]
        assert rec["status"] == "ok" and rec["score"]["passed"] and rec["meta"]["mode"] == "replay"
        assert rec["totals"]["tool_calls_recorded"] == 1  # the lookup was served from the recording
        assert rec["harness"]["defaults"]["model"] == "nemotron-3-nano"


def test_runner_check_and_init_harness(tmp_path):
    folder = make_agent_folder(tmp_path)
    out = subprocess.run([sys.executable, "-m", "downshift.runner", "check", "--folder", str(folder)], capture_output=True, text=True, timeout=60)
    info = json.loads(out.stdout)
    assert info["grader"] is True and info["tasks"] == {"file": "tasks.jsonl", "n": 6, "with_expected": 6} and info["harness"]["runtime"] == "custom"
    out = subprocess.run([sys.executable, "-m", "downshift.runner", "init-harness", "--stdout", "--folder", str(folder)], capture_output=True, text=True, timeout=60)
    assert Harness.from_yaml(out.stdout).fingerprint() == Harness.from_dict(CUSTOM).fingerprint()


def test_unquoted_yaml_on_off_for_reasoning():
    text = Harness.from_dict(CUSTOM).to_yaml().replace("temperature: null", "temperature: null\n  reasoning: off")
    h = Harness.from_yaml(text)
    assert h.defaults.reasoning == "off"
    h2 = Harness.from_dict({**CUSTOM, "steps": [{"id": "answer", "kind": "tool_loop", "reasoning": True}]})
    assert h2.steps[0].reasoning == "on" and Harness.from_dict({**CUSTOM, "defaults": {**CUSTOM["defaults"], "reasoning": "none"}}).defaults.reasoning == "off"
