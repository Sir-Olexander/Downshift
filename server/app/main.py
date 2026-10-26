"""Downshift backend: run storage, optimizer, replay, scoring and GitHub PRs."""

from __future__ import annotations

import threading
from contextlib import asynccontextmanager
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Depends, FastAPI, Header, HTTPException, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel, Field

from downshift import Harness, HarnessError, default_table

from .db import Database
from .github_pr import open_pr, pr_payload
from .optimizer.engine import TARGETS, Engine, default_config
from .settings import Settings

settings = Settings.from_env()
db = Database(settings.db_path)
_running: dict[str, threading.Thread] = {}
_run_lock = threading.Lock()


@asynccontextmanager
async def lifespan(app: FastAPI):
    if db.is_empty() and settings.seed_path.exists():
        counts = db.import_from_file(settings.seed_path)
        print(f"[downshift] seeded demo data from {settings.seed_path}: {counts}")
    yield


app = FastAPI(title="Downshift API", version="0.1.0", lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=["*"], allow_methods=["*"], allow_headers=["*"])


# ---- auth ---------------------------------------------------------------------------------------
def require_api_key(authorization: str | None = Header(default=None)) -> str:
    token = (authorization or "").removeprefix("Bearer ").strip()
    if token not in settings.api_keys:
        raise HTTPException(status_code=401, detail="invalid API key")
    return token


# ---- shaping ------------------------------------------------------------------------------------
def _option_public(o: dict[str, Any], *, with_harness: bool = False) -> dict[str, Any]:
    h = o.get("harness_json") or {}
    out = {
        "id": o["id"], "key": o["key"], "label": o["label"], "target": o["target"], "status": o["status"], "position": o["position"],
        "metrics": o.get("metrics_json"), "rounds": o.get("rounds_json") or [], "rationale": o.get("rationale"),
        "models_used": Harness.from_dict(h).models_used() if h else [], "changelog": h.get("changelog") or [], "created_at": o["created_at"],
    }
    if with_harness:
        out["harness"] = h
        out["harness_yaml"] = o.get("harness_yaml")
    return out


def _optimization_public(o: dict[str, Any], *, with_options: bool = True) -> dict[str, Any]:
    out = {
        "id": o["id"], "project_id": o["project_id"], "status": o["status"], "source": o.get("source"), "created_at": o["created_at"], "started_at": o.get("started_at"),
        "finished_at": o.get("finished_at"), "config": o.get("config_json"), "split": o.get("split_json"), "progress": o.get("progress_json"), "summary": o.get("summary_json"), "error": o.get("error"),
    }
    if with_options:
        out["options"] = [_option_public(x) for x in db.list_options(o["id"])]
    return out


def _run_public(r: dict[str, Any]) -> dict[str, Any]:
    return {k: r.get(k) for k in ("id", "project_id", "task_id", "input", "status", "harness_fingerprint", "started_at", "ended_at", "cost_usd", "latency_ms", "tokens_in", "tokens_out", "tag", "created_at")}


def _get_opt_or_404(oid: str) -> dict[str, Any]:
    if oid == "latest":
        done = [o for o in db.list_optimizations(limit=50) if o["status"] == "done"]
        if not done:
            raise HTTPException(status_code=404, detail="no completed optimization yet")
        return done[0]
    o = db.get_optimization(oid)
    if not o:
        raise HTTPException(status_code=404, detail="optimization not found")
    return o


def _get_option_or_404(opt: dict[str, Any], key: str) -> dict[str, Any]:
    o = db.get_option_by_key(opt["id"], key) or db.get_option(key)
    if not o or o["optimization_id"] != opt["id"]:
        raise HTTPException(status_code=404, detail="option not found")
    return o


# ---- basic ----------------------------------------------------------------------------------------
@app.get("/healthz")
def healthz() -> dict[str, Any]:
    return {"ok": True, "provider": settings.provider, "demo_mode": settings.demo_mode, "running": list(_running)}


@app.get("/v1/models")
def models() -> dict[str, Any]:
    return default_table().to_dict()


# ---- runs (SDK ingest) ------------------------------------------------------------------------------
def _ingest(record: dict[str, Any]) -> None:
    if not record.get("id") or "events" not in record:
        raise HTTPException(status_code=400, detail="not a run record")
    project_id = record.get("project") or "default"
    harness = record.get("harness")
    fp = record.get("harness_fingerprint")
    tag = (record.get("meta") or {}).get("tag")
    mode = (record.get("meta") or {}).get("mode", "record")
    if harness and mode == "record" and tag in (None, "baseline"):
        db.upsert_project(project_id, harness, fp, {"last_run_at": record.get("ended_at")})
    else:
        db.upsert_project(project_id, None, None, None)
    db.insert_run(record)


@app.post("/v1/runs", status_code=201)
def post_run(record: dict[str, Any], _key: str = Depends(require_api_key)) -> dict[str, Any]:
    _ingest(record)
    return {"ok": True, "id": record["id"]}


@app.post("/v1/runs/import", status_code=201)
def import_runs(records: list[dict[str, Any]], _key: str = Depends(require_api_key)) -> dict[str, Any]:
    for r in records:
        _ingest(r)
    return {"ok": True, "imported": len(records)}


@app.get("/v1/runs/{run_id}")
def get_run(run_id: str) -> dict[str, Any]:
    r = db.get_run(run_id)
    if not r:
        raise HTTPException(status_code=404, detail="run not found")
    return {**_run_public(r), "record": r["record_json"]}


# ---- projects ---------------------------------------------------------------------------------------
@app.get("/v1/projects")
def list_projects() -> list[dict[str, Any]]:
    return [{"id": p["id"], "name": p["name"], "created_at": p["created_at"], "harness_fingerprint": p.get("harness_fingerprint"), "run_count": p.get("run_count", 0), "models_used": Harness.from_dict(p["harness_json"]).models_used() if p.get("harness_json") else []} for p in db.list_projects()]


@app.get("/v1/projects/{project_id}")
def get_project(project_id: str) -> dict[str, Any]:
    p = db.get_project(project_id)
    if not p:
        raise HTTPException(status_code=404, detail="project not found")
    h = Harness.from_dict(p["harness_json"]) if p.get("harness_json") else None
    runs = db.list_runs(project_id, limit=2000)
    return {"id": p["id"], "name": p["name"], "created_at": p["created_at"], "harness": p.get("harness_json"), "harness_yaml": h.to_yaml() if h else None, "harness_fingerprint": p.get("harness_fingerprint"), "runs": [_run_public(r) for r in runs], "optimizations": [_optimization_public(o, with_options=False) for o in db.list_optimizations(project_id)]}


@app.get("/v1/projects/{project_id}/runs")
def list_project_runs(project_id: str, tag: str | None = None, limit: int = Query(500, le=5000)) -> list[dict[str, Any]]:
    return [_run_public(r) for r in db.list_runs(project_id, tag=tag, limit=limit)]


# ---- optimizations ------------------------------------------------------------------------------------
class OptimizationRequest(BaseModel):
    project_id: str = "research-agent"
    targets: list[str] = Field(default_factory=lambda: ["super", "nano", "mix"])
    rounds: int | None = None
    sample_size: int | None = None
    test_fraction: float | None = None
    max_cost_usd: float | None = None
    concurrency: int | None = None
    tag: str | None = None


def _start(oid: str) -> None:
    engine = Engine(db, settings)

    def target() -> None:
        try:
            engine.run(oid)
        finally:
            with _run_lock:
                _running.pop(oid, None)

    t = threading.Thread(target=target, name=f"opt-{oid}", daemon=True)
    with _run_lock:
        _running[oid] = t
    t.start()


@app.post("/v1/optimizations", status_code=202)
def create_optimization(req: OptimizationRequest) -> dict[str, Any]:
    project = db.get_project(req.project_id)
    if not project or not project.get("harness_json"):
        raise HTTPException(status_code=400, detail=f"project '{req.project_id}' has no recorded baseline runs")
    n_ok = len([r for r in db.latest_runs_per_task(req.project_id, tag=req.tag)])
    if n_ok < 4:
        raise HTTPException(status_code=400, detail=f"need at least 4 successful recorded runs, found {n_ok}")
    with _run_lock:
        if _running:
            raise HTTPException(status_code=409, detail="an optimization is already running; try again in a few minutes")
    cfg = default_config(settings)
    targets = [t for t in req.targets if t in TARGETS]
    if not targets:
        raise HTTPException(status_code=400, detail=f"targets must be among {list(TARGETS)}")
    cfg["targets"] = targets
    if req.rounds is not None:
        cfg["rounds"] = req.rounds
    if req.sample_size is not None:
        cfg["sample_size"] = req.sample_size
    if req.test_fraction is not None:
        cfg["test_fraction"] = req.test_fraction
    if req.max_cost_usd is not None:
        cfg["max_cost_usd"] = req.max_cost_usd
    if req.concurrency is not None:
        cfg["concurrency"] = req.concurrency
    cfg["tag"] = req.tag
    if settings.demo_mode:  # keep live demo runs small and rate limited
        since = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat().replace("+00:00", "Z")
        if db.count_live_optimizations_since(since) >= settings.max_live_optimizations_per_hour:
            raise HTTPException(status_code=429, detail=f"demo limit: at most {settings.max_live_optimizations_per_hour} live optimizations per hour")
        cfg["rounds"] = max(1, min(int(cfg["rounds"]), 2))
        cfg["sample_size"] = max(3, min(int(cfg["sample_size"]), 8))
        cfg["max_cost_usd"] = min(float(cfg["max_cost_usd"]), 4.0)
        cfg["concurrency"] = max(1, min(int(cfg["concurrency"]), 4))
    opt = db.create_optimization(req.project_id, cfg, source="live")
    db.add_event(opt["id"], f"Queued optimization for project '{req.project_id}' with targets {targets}.", phase="queued")
    _start(opt["id"])
    return _optimization_public(opt)


@app.get("/v1/optimizations")
def list_optimizations(project_id: str | None = None, limit: int = Query(50, le=200)) -> list[dict[str, Any]]:
    return [_optimization_public(o, with_options=False) for o in db.list_optimizations(project_id, limit)]


@app.get("/v1/optimizations/{oid}")
def get_optimization(oid: str) -> dict[str, Any]:
    return _optimization_public(_get_opt_or_404(oid))


@app.get("/v1/optimizations/{oid}/events")
def get_events(oid: str, after: int = 0, limit: int = Query(500, le=2000)) -> list[dict[str, Any]]:
    opt = _get_opt_or_404(oid)
    return [{"id": e["id"], "ts": e["ts"], "level": e["level"], "phase": e["phase"], "message": e["message"], "data": e.get("data_json")} for e in db.list_events(opt["id"], after, limit)]


@app.get("/v1/optimizations/{oid}/options/{key}")
def get_option(oid: str, key: str) -> dict[str, Any]:
    opt = _get_opt_or_404(oid)
    option = _get_option_or_404(opt, key)
    baseline = db.get_option_by_key(opt["id"], "baseline")
    out = _option_public(option, with_harness=True)
    out["baseline_harness_yaml"] = (baseline or {}).get("harness_yaml")
    out["baseline_harness"] = (baseline or {}).get("harness_json")
    out["optimization"] = _optimization_public(opt, with_options=False)
    replays = []
    for r in db.list_replays(option["id"], with_records=False):
        base_run = db.get_run(r["baseline_run_id"]) if r.get("baseline_run_id") else None
        replays.append({"id": r["id"], "task_id": r["task_id"], "split": r["split"], "round": r["round"], "status": r["status"], "question": (base_run or {}).get("input"), "metrics": r.get("metrics_json"), "judge": {k: (r.get("judge_json") or {}).get(k) for k in ("preferred", "reason", "candidate", "baseline", "candidate_quality", "baseline_quality", "order", "error")} if r.get("judge_json") else None, "checks": r.get("checks_json")})
    out["replays"] = replays
    out["prs"] = [{"id": p["id"], "url": p["url"], "dry_run": bool(p["dry_run"]), "created_at": p["created_at"]} for p in db.list_prs(option["id"])]
    return out


@app.get("/v1/optimizations/{oid}/options/{key}/runs/{task_id}")
def get_option_run(oid: str, key: str, task_id: str, split: str = "test") -> dict[str, Any]:
    opt = _get_opt_or_404(oid)
    option = _get_option_or_404(opt, key)
    rep = db.find_replay(option["id"], task_id, split) or db.find_replay(option["id"], task_id, "opt")
    if not rep:
        raise HTTPException(status_code=404, detail="no replay for that task")
    base = db.get_run(rep["baseline_run_id"]) if rep.get("baseline_run_id") else None
    return {
        "task_id": task_id, "split": rep["split"], "round": rep["round"], "question": (base or {}).get("input") or rep["record_json"].get("input"),
        "baseline": (base or {}).get("record_json"), "candidate": rep["record_json"], "judge": rep.get("judge_json"), "checks": rep.get("checks_json"), "metrics": rep.get("metrics_json"),
        "option": _option_public(option), "baseline_option": _option_public(db.get_option_by_key(opt["id"], "baseline") or option),
    }


class PRRequest(BaseModel):
    dry_run: bool = False


@app.post("/v1/optimizations/{oid}/options/{key}/pr")
def create_pr(oid: str, key: str, req: PRRequest | None = None) -> dict[str, Any]:
    opt = _get_opt_or_404(oid)
    option = _get_option_or_404(opt, key)
    if option["key"] == "baseline" or not option.get("harness_yaml"):
        raise HTTPException(status_code=400, detail="this option has no new harness to propose")
    payload = pr_payload(option, opt, settings)
    if req and req.dry_run:
        return {"dry_run": True, "url": None, "reason": "preview", **payload}
    try:
        result = open_pr(payload, settings)
    except Exception as e:
        raise HTTPException(status_code=502, detail=f"GitHub error: {e}") from e
    pr = db.insert_pr(opt["id"], option["id"], result.get("url"), bool(result.get("dry_run")), {k: v for k, v in result.items() if k != "content"})
    return {**result, "id": pr["id"]}


@app.get("/v1/optimizations/{oid}/options/{key}/pr")
def list_option_prs(oid: str, key: str) -> list[dict[str, Any]]:
    opt = _get_opt_or_404(oid)
    option = _get_option_or_404(opt, key)
    return [{"id": p["id"], "url": p["url"], "dry_run": bool(p["dry_run"]), "created_at": p["created_at"], "payload": p.get("payload_json")} for p in db.list_prs(option["id"])]


# ---- harness validation helper for the UI -------------------------------------------------------------
@app.post("/v1/harness/validate")
def validate_harness(body: dict[str, Any]) -> dict[str, Any]:
    try:
        h = Harness.from_yaml(body.get("yaml", "")) if "yaml" in body else Harness.from_dict(body.get("harness") or {})
        h.validate_models(default_table())
    except HarnessError as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True, "fingerprint": h.fingerprint(), "models_used": h.models_used(), "yaml": h.to_yaml()}
