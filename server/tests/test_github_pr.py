import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from app.github_pr import open_pr, pr_payload, results_table
from app.settings import Settings
from downshift import Harness

BASELINE = Path(__file__).resolve().parents[2] / "demo_agent" / "harness.yaml"


def _summary():
    base = {"n": 17, "success_rate": 94.1, "quality": 82.0, "cost_per_run": 0.0251, "latency_ms": 150000}
    nano = {"n": 17, "success_rate": 88.2, "quality": 74.5, "cost_per_run": 0.0019, "latency_ms": 60000}
    return {
        "headline": {"text": "Task success 94% → 88%, cost down 92%", "verdict": "v", "recommended": "nano"},
        "baseline": base,
        "options": [{"key": "nano", "label": "Nemotron 3 Nano", "models_used": ["nemotron-3-nano"], "metrics": nano, "deltas": {"success_rate_pp": -5.9, "quality_pts": -7.5, "cost_pct": -92.4, "latency_pct": -60.0}, "meets_bar": False, "option_id": "x"}],
        "split": {"optimization": 25, "test": 17},
        "judge": {"model": "nemotron-3-ultra"},
    }


def test_pr_payload_and_dry_run(monkeypatch):
    monkeypatch.delenv("GITHUB_REPO", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    settings = Settings.from_env()
    settings.github_repo = None
    h = Harness.load(BASELINE).copy_with(defaults={"model": "nemotron-3-nano"}, changelog=["shorter prompt"])
    option = {"key": "nano", "label": "Nemotron 3 Nano", "harness_json": h.to_dict(), "harness_yaml": h.to_yaml()}
    opt = {"id": "opt_abc123def456", "summary_json": _summary()}
    payload = pr_payload(option, opt, settings)
    assert payload["branch"].startswith("downshift/nano-")
    assert "cost 92% lower" in payload["title"] and "94% → 88%" in payload["title"]
    assert "models: nemotron-3-nano" in payload["body"] and "- shorter prompt" in payload["body"]
    assert "| Nemotron 3 Nano **(this PR)** |" in payload["body"]
    assert payload["content"].startswith("name: research-agent")
    monkeypatch.setattr("app.github_pr.github_token", lambda s: None)
    result = open_pr(payload, settings)
    assert result["dry_run"] and result["url"] is None and "GITHUB_REPO" in result["reason"]


def test_results_table_marks_chosen_row():
    table = results_table(_summary(), "nano")
    assert table.splitlines()[2].startswith("| Baseline (Nemotron 3 Ultra) | 94% | 82.0 | $0.0251 | 150 s |")
    assert "**(this PR)**" in table
