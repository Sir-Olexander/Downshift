"""The rewriter's model notes come from the technical reports, and failed runs show their final message."""

import sys
from pathlib import Path

SERVER = Path(__file__).resolve().parents[1]
if str(SERVER) not in sys.path:
    sys.path.insert(0, str(SERVER))

from app.optimizer.engine import Engine  # noqa: E402
from app.optimizer.guidance import MODEL_NOTES, guidance_text, lookup_guidance  # noqa: E402
from app.optimizer.rewrite import _history_text  # noqa: E402
from downshift import default_table  # noqa: E402


def test_every_model_in_the_table_has_notes_except_the_closed_baseline():
    missing = [m.id for m in default_table().models if m.id not in MODEL_NOTES and m.tier != "closed"]
    assert missing == []


def test_nano_notes_keep_thinking_on_for_tool_loops():
    text = guidance_text(["nemotron-3-nano"], default_table(), [])
    assert "Keep thinking ON for every step that calls tools or loops" in text
    assert "never show a tool call as text" in text
    assert "closing rule for the final message" in text
    assert "Rules that hold across these models" in text


class _Tools:
    def __init__(self, provider: str):
        self.provider = provider
        self.calls = 0

    def web_search(self, q: str, max_results: int = 4):
        self.calls += 1
        return {"provider": self.provider, "results": [{"title": "t", "url": "u", "snippet": "s"}]}


def test_lookup_only_uses_a_real_search_provider():
    wiki = _Tools("wikipedia")
    assert lookup_guidance(wiki, "NVIDIA Nemotron 3 Nano") == []
    assert wiki.calls == 0
    tavily = _Tools("tavily")
    assert lookup_guidance(tavily, "NVIDIA Nemotron 3 Nano")[0]["url"] == "u"
    assert tavily.calls == 1


def _item(task_id: str, success: bool, answer: str, final: str):
    return {
        "task_id": task_id, "question": "q", "judge": {"reason": "candidate failed: no SQL"},
        "checks": {"no_errors": True, "ground_truth": success, "passed": True},
        "metrics": {"success": success, "quality": 100.0 if success else 0.0},
        "record": {"output": {"answer": answer}, "events": [
            {"type": "tool_call", "name": "execute_sql"},
            {"type": "model_call", "response": {"content": final, "tool_calls": []}},
        ]},
    }


def test_worst_examples_carry_the_models_final_message_into_the_rewrite_history():
    items = [_item("a", False, "", "The country with the most car makers is **Japan**."), _item("b", True, "SELECT 1", "```sql\nSELECT 1\n```")]
    worst = Engine._worst_examples(items, n=1)
    assert worst[0]["task_id"] == "a"
    assert worst[0]["final_message"].startswith("The country with the most")
    text = _history_text([{"round": 1, "metrics": {}, "worst_examples": worst, "changelog": []}])
    assert "the model's final message: 'The country with the most car makers" in text


def test_model_targets_cover_any_model_in_the_table():
    from app.optimizer.engine import target_spec

    assert target_spec("model:gpt-oss-20b")["allowed"] == ["gpt-oss-20b"]
    assert target_spec("model:not-a-model") is None and target_spec("nano")["allowed"] == ["nemotron-3-nano"]


def test_failure_summary_groups_failures_by_kind():
    def item(ok, details, status="ok"):
        return {"metrics": {"success": ok}, "judge": {"method": "ground_truth", "candidate": {"details": details}}, "record": {"status": status}}

    items = [item(False, "no SQL: No SQL produced. Response: Japan has 5"), item(False, "no SQL: No SQL produced. Response: 11 orchestras"),
             item(False, "expected 3 rows, got 1"), item(True, "1 rows match")]
    s = Engine._failure_summary(items)
    assert s[0] == "2 of 4 runs: no SQL: No SQL produced. Response: ..." and s[1] == "1 of 4 runs: expected N rows, got N"
    text = _history_text([{"round": 1, "metrics": {}, "worst_examples": [], "failure_summary": s, "changelog": []}])
    assert "failures by kind: 2 of 4 runs: no SQL" in text
