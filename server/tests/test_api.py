import json
from pathlib import Path

from downshift import Harness

BASELINE = Path(__file__).resolve().parents[2] / "demo_agent" / "harness.yaml"


def _record(i: int) -> dict:
    h = Harness.load(BASELINE)
    return {
        "id": f"run{i}", "project": "research-agent", "task_id": f"q{i:03d}", "input": f"question {i}", "harness": h.to_dict(), "harness_fingerprint": h.fingerprint(),
        "started_at": "2026-10-26T00:00:00Z", "ended_at": "2026-10-26T00:00:30Z", "status": "ok", "output": {"answer": "answer " * 20, "sources": ["https://en.wikipedia.org/wiki/Moon"]},
        "events": [], "totals": {"model_calls": 1, "tool_calls": 0, "tokens_in": 10, "tokens_out": 5, "cost_usd": 0.001, "latency_ms": 100}, "meta": {"tag": "baseline", "mode": "record"},
    }


def test_ingest_requires_key_and_creates_project(client):
    assert client.post("/v1/runs", json=_record(1)).status_code == 401
    r = client.post("/v1/runs", json=_record(1), headers={"Authorization": "Bearer test-key"})
    assert r.status_code == 201
    projects = client.get("/v1/projects").json()
    assert projects[0]["id"] == "research-agent" and projects[0]["run_count"] == 1 and projects[0]["models_used"] == ["nemotron-3-ultra"]
    run = client.get("/v1/runs/run1").json()
    assert run["task_id"] == "q001" and run["record"]["output"]["sources"]
    project = client.get("/v1/projects/research-agent").json()
    assert "system_prompt" in project["harness_yaml"]


def test_optimization_needs_enough_runs_and_models_endpoint(client):
    r = client.post("/v1/optimizations", json={"project_id": "research-agent"})
    assert r.status_code == 400
    client.post("/v1/runs/import", json=[_record(i) for i in range(1, 4)], headers={"Authorization": "Bearer test-key"})
    r = client.post("/v1/optimizations", json={"project_id": "research-agent"})
    assert r.status_code == 400 and "at least 4" in r.json()["detail"]
    m = client.get("/v1/models").json()
    assert {x["id"] for x in m["models"]} >= {"nemotron-3-nano", "nemotron-3-super", "nemotron-3-ultra"}
    assert client.get("/v1/optimizations/latest").status_code == 404
    assert client.get("/healthz").json()["ok"] is True


def test_harness_validate_endpoint(client):
    yaml_text = Harness.load(BASELINE).to_yaml()
    ok = client.post("/v1/harness/validate", json={"yaml": yaml_text}).json()
    assert ok["ok"] and ok["models_used"] == ["nemotron-3-ultra"]
    bad = client.post("/v1/harness/validate", json={"yaml": "name: x\n"}).json()
    assert not bad["ok"] and "invalid harness" in bad["error"]
