import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.optimizer.judge import _extract_json, auto_checks, is_success, quality_score
from app.optimizer.metrics import aggregate, bar_tolerance_pp, deltas, meets_bar, objective
from app.optimizer.rewrite import _check_target, _extract_yaml
from app.optimizer.split import split_runs
from downshift import Harness

BASELINE = Path(__file__).resolve().parents[2] / "demo_agent" / "harness.yaml"


def _record(answer, sources, tool_urls, status="ok"):
    if answer and sources:  # real answers list their sources in the text; checks re-extract them from there
        answer = answer + "\n\nSources:\n" + "\n".join(sources)
    return {
        "status": status,
        "output": {"answer": answer, "sources": sources},
        "events": [{"type": "tool_call", "name": "web_search", "args": {"query": "q"}, "result": {"results": [{"url": u} for u in tool_urls]}, "latency_ms": 10}],
        "totals": {"cost_usd": 0.01, "latency_ms": 1000, "tokens_in": 100, "tokens_out": 50, "model_calls": 2, "tool_calls": 1},
    }


def test_split_is_deterministic_and_disjoint():
    runs = [{"task_id": f"q{i:03d}"} for i in range(42)]
    a_opt, a_test = split_runs(runs, 0.4, 42)
    _, b_test = split_runs(list(reversed(runs)), 0.4, 42)
    assert [r["task_id"] for r in a_test] == [r["task_id"] for r in b_test]
    assert len(a_test) == 17 and len(a_opt) == 25
    assert not {r["task_id"] for r in a_opt} & {r["task_id"] for r in a_test}


def test_auto_checks_flag_sources_not_in_evidence():
    good = auto_checks(_record("A long enough answer with a citation [1] and more words to pass the length check.", ["https://en.wikipedia.org/wiki/Moon"], ["https://en.wikipedia.org/wiki/Moon"]))
    assert good["passed"] and good["sources_from_evidence"]
    bad = auto_checks(_record("A long enough answer with a citation [1] and more words to pass the length check.", ["https://made-up.example/x"], ["https://en.wikipedia.org/wiki/Moon"]))
    assert not bad["passed"] and bad["n_unknown_sources"] == 1
    empty = auto_checks(_record("", [], []))
    assert not empty["answer_produced"] and not empty["has_sources"]


def test_judge_parsing_and_success_rule():
    data = _extract_json('```json\n{"A": {"correct": 5, "complete": 4, "supported": 3}, "B": {"correct": 2, "complete": 2, "supported": 2}, "preferred": "A", "reason": "x"}\n```')
    assert data["preferred"] == "A"
    assert quality_score(data["A"]) == 80.0
    checks = {"passed": True}
    assert is_success({"correct": 3, "complete": 1, "supported": 1}, checks)
    assert not is_success({"correct": 2, "complete": 5, "supported": 5}, checks)
    assert not is_success({"correct": 5, "complete": 5, "supported": 5}, {"passed": False})


def test_aggregate_deltas_and_objective():
    items = [
        {"success": True, "quality": 80, "checks_passed": True, "cost_usd": 0.004, "latency_ms": 10000, "tokens_in": 1, "tokens_out": 1, "preferred": "candidate", "tool_calls": 3, "tool_calls_live": 1, "status": "ok"},
        {"success": False, "quality": 40, "checks_passed": False, "cost_usd": 0.002, "latency_ms": 5000, "tokens_in": 1, "tokens_out": 1, "preferred": "baseline", "tool_calls": 1, "tool_calls_live": 0, "status": "ok"},
    ]
    agg = aggregate(items)
    assert agg["success_rate"] == 50.0 and agg["quality"] == 60.0 and agg["cost_per_run"] == 0.003 and agg["win_rate"] == 50.0
    base = {"success_rate": 90.0, "quality": 85.0, "cost_per_run": 0.015, "latency_ms": 20000}
    d = deltas(agg, base)
    assert d["success_rate_pp"] == -40.0 and d["cost_pct"] == -80.0
    assert not meets_bar(agg, base)
    assert objective({"success_rate": 90, "quality": 85, "cost_per_run": 0.003}, base) > objective({"success_rate": 90, "quality": 85, "cost_per_run": 0.015}, base)
    assert objective(agg, base) < objective({"success_rate": 88, "quality": 60, "cost_per_run": 0.003}, base)


def test_rewrite_helpers_extract_yaml_and_enforce_target():
    h = Harness.load(BASELINE)
    text = "Here you go:\n```yaml\n" + h.to_yaml() + "```\nRationale: kept it simple."
    assert Harness.from_yaml(_extract_yaml(text)).fingerprint() == h.fingerprint()
    try:
        _check_target(h, "nano", ["nemotron-3-nano"])
        assert False, "should reject ultra steps for the nano target"
    except Exception:
        pass
    try:
        _check_target(h, "mix", ["nemotron-3-nano", "nemotron-3-super", "nemotron-3-ultra"])
        assert False, "mix must move something off ultra"
    except Exception:
        pass
    nano = h.copy_with(defaults={**h.to_dict()["defaults"], "model": "nemotron-3-nano"})
    _check_target(nano, "nano", ["nemotron-3-nano"])


def test_unparsed_judge_reply_is_unknown_not_zero():
    from app.optimizer.judge import judge_pair
    from downshift.providers import ChatResult

    class Mute:
        provider_name = "fake"

        def __init__(self):
            from downshift import default_table
            self.table = default_table()
            self.calls = 0

        def chat(self, model, messages, **kw):
            self.calls += 1
            return ChatResult(content="I cannot decide.", tool_calls=[], reasoning=None, tokens_in=10, tokens_out=5, latency_ms=1, finish_reason="stop", model=model, provider="fake", provider_model=model)

    llm = Mute()
    j = judge_pair(llm, "nemotron-3-ultra", "q", "a", "b")
    assert llm.calls == 2 and j["parsed"] is False and j["candidate"] is None and j["preferred"] is None
    items = [
        {"judged": False, "success": False, "quality": None, "checks_passed": True, "cost_usd": 0.01, "latency_ms": 100, "tokens_in": 1, "tokens_out": 1, "tool_calls": 1, "tool_calls_live": 0, "status": "ok"},
        {"judged": True, "success": True, "quality": 90, "checks_passed": True, "cost_usd": 0.01, "latency_ms": 100, "tokens_in": 1, "tokens_out": 1, "preferred": "candidate", "tool_calls": 1, "tool_calls_live": 0, "status": "ok"},
    ]
    agg = aggregate(items)
    assert agg["n"] == 2 and agg["n_judged"] == 1 and agg["success_rate"] == 100.0 and agg["quality"] == 90.0


def test_tool_errors_do_not_fail_checks():
    rec = _record("A long enough answer with a citation [1] and more words to pass the length check.", ["https://en.wikipedia.org/wiki/Moon"], ["https://en.wikipedia.org/wiki/Moon"])
    rec["events"].append({"type": "tool_call", "name": "read_page", "args": {"url": "x"}, "result": None, "latency_ms": 5, "error": "HTTPError: 404"})
    assert auto_checks(rec)["passed"]
    rec["events"].append({"type": "model_call", "step": "synthesize", "error": "LLMError: boom"})
    assert not auto_checks(rec)["passed"]


def test_bar_tolerance_is_at_least_one_run():
    assert bar_tolerance_pp(17) == 5.9 and bar_tolerance_pp(100) == 5.0 and bar_tolerance_pp(None) == 5.0
    base = {"n": 17, "n_judged": 17, "success_rate": 82.4, "quality": 98.8, "cost_per_run": 0.03, "latency_ms": 100}
    one_run_worse = {"n": 17, "n_judged": 17, "success_rate": 76.5, "quality": 94.5, "cost_per_run": 0.008, "latency_ms": 40}
    two_runs_worse = {**one_run_worse, "success_rate": 70.6}
    assert meets_bar(one_run_worse, base) and not meets_bar(two_runs_worse, base)
