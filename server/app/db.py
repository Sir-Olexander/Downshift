"""SQLite storage. One small class, JSON columns, a lock around every call."""

from __future__ import annotations

import gzip
import json
import sqlite3
import threading
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

SCHEMA = """
CREATE TABLE IF NOT EXISTS projects (
  id TEXT PRIMARY KEY, name TEXT, created_at TEXT, harness_json TEXT, harness_fingerprint TEXT, meta_json TEXT
);
CREATE TABLE IF NOT EXISTS runs (
  id TEXT PRIMARY KEY, project_id TEXT, task_id TEXT, input TEXT, status TEXT, harness_fingerprint TEXT,
  started_at TEXT, ended_at TEXT, cost_usd REAL, latency_ms INTEGER, tokens_in INTEGER, tokens_out INTEGER,
  tag TEXT, record_json TEXT, created_at TEXT
);
CREATE INDEX IF NOT EXISTS runs_project ON runs(project_id, created_at);
CREATE TABLE IF NOT EXISTS optimizations (
  id TEXT PRIMARY KEY, project_id TEXT, status TEXT, created_at TEXT, started_at TEXT, finished_at TEXT,
  config_json TEXT, split_json TEXT, progress_json TEXT, summary_json TEXT, error TEXT, source TEXT
);
CREATE TABLE IF NOT EXISTS options (
  id TEXT PRIMARY KEY, optimization_id TEXT, key TEXT, label TEXT, target TEXT, status TEXT, position INTEGER,
  harness_json TEXT, harness_yaml TEXT, rounds_json TEXT, metrics_json TEXT, rationale TEXT, created_at TEXT
);
CREATE INDEX IF NOT EXISTS options_opt ON options(optimization_id, position);
CREATE TABLE IF NOT EXISTS replays (
  id TEXT PRIMARY KEY, optimization_id TEXT, option_id TEXT, task_id TEXT, baseline_run_id TEXT, split TEXT,
  round INTEGER, status TEXT, record_json TEXT, judge_json TEXT, checks_json TEXT, metrics_json TEXT, created_at TEXT
);
CREATE INDEX IF NOT EXISTS replays_option ON replays(option_id, split, round);
CREATE TABLE IF NOT EXISTS labels (run_id TEXT PRIMARY KEY, labels_json TEXT, created_at TEXT);
CREATE TABLE IF NOT EXISTS events (
  id INTEGER PRIMARY KEY AUTOINCREMENT, optimization_id TEXT, ts TEXT, level TEXT, phase TEXT, message TEXT, data_json TEXT
);
CREATE INDEX IF NOT EXISTS events_opt ON events(optimization_id, id);
CREATE TABLE IF NOT EXISTS prs (
  id TEXT PRIMARY KEY, optimization_id TEXT, option_id TEXT, created_at TEXT, url TEXT, dry_run INTEGER, payload_json TEXT
);
"""

TABLES = ["projects", "runs", "optimizations", "options", "replays", "labels", "events", "prs"]
JSON_COLS = {"harness_json", "meta_json", "record_json", "config_json", "split_json", "progress_json", "summary_json", "rounds_json", "metrics_json", "judge_json", "checks_json", "labels_json", "data_json", "payload_json"}


def now_iso() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds").replace("+00:00", "Z")


def new_id(prefix: str) -> str:
    return f"{prefix}_{uuid.uuid4().hex[:12]}"


def _dumps(v: Any) -> str | None:
    return None if v is None else json.dumps(v, ensure_ascii=False)


def _loads(v: Any) -> Any:
    if v is None:
        return None
    try:
        return json.loads(v)
    except (TypeError, json.JSONDecodeError):
        return v


class Database:
    def __init__(self, path: str | Path):
        self.path = Path(path)
        if str(self.path) != ":memory:":
            self.path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._conn = sqlite3.connect(str(self.path), check_same_thread=False)
        self._conn.row_factory = sqlite3.Row
        with self._lock:
            self._conn.execute("PRAGMA journal_mode=WAL")
            self._conn.execute("PRAGMA synchronous=NORMAL")
            self._conn.executescript(SCHEMA)
            self._conn.commit()

    # ---- generic helpers -----------------------------------------------------------------------
    def _row(self, row: sqlite3.Row | None) -> dict[str, Any] | None:
        if row is None:
            return None
        d = dict(row)
        for k in list(d):
            if k in JSON_COLS:
                d[k] = _loads(d[k])
        return d

    def _rows(self, rows: Iterable[sqlite3.Row]) -> list[dict[str, Any]]:
        return [self._row(r) for r in rows]  # type: ignore[misc]

    def _insert(self, table: str, data: dict[str, Any]) -> None:
        cols = list(data)
        vals = [_dumps(data[c]) if c in JSON_COLS else data[c] for c in cols]
        sql = f"INSERT OR REPLACE INTO {table} ({', '.join(cols)}) VALUES ({', '.join('?' for _ in cols)})"
        with self._lock:
            self._conn.execute(sql, vals)
            self._conn.commit()

    def _update(self, table: str, id_: str, data: dict[str, Any]) -> None:
        if not data:
            return
        cols = list(data)
        vals = [_dumps(data[c]) if c in JSON_COLS else data[c] for c in cols]
        sql = f"UPDATE {table} SET {', '.join(c + ' = ?' for c in cols)} WHERE id = ?"
        with self._lock:
            self._conn.execute(sql, [*vals, id_])
            self._conn.commit()

    def _one(self, sql: str, args: tuple = ()) -> dict[str, Any] | None:
        with self._lock:
            return self._row(self._conn.execute(sql, args).fetchone())

    def _all(self, sql: str, args: tuple = ()) -> list[dict[str, Any]]:
        with self._lock:
            return self._rows(self._conn.execute(sql, args).fetchall())

    # ---- projects -----------------------------------------------------------------------------
    def upsert_project(self, project_id: str, harness: dict[str, Any] | None, fingerprint: str | None, meta: dict[str, Any] | None = None) -> dict[str, Any]:
        with self._lock:  # read-then-write as one step (RLock, so the nested calls are fine)
            existing = self.get_project(project_id)
            if existing is None:
                self._insert("projects", {"id": project_id, "name": project_id, "created_at": now_iso(), "harness_json": harness, "harness_fingerprint": fingerprint, "meta_json": meta or {}})
            else:
                upd: dict[str, Any] = {}
                if harness is not None and fingerprint != existing.get("harness_fingerprint"):
                    upd.update({"harness_json": harness, "harness_fingerprint": fingerprint})
                if meta:
                    upd["meta_json"] = {**(existing.get("meta_json") or {}), **meta}
                self._update("projects", project_id, upd)
            return self.get_project(project_id)  # type: ignore[return-value]

    def get_project(self, project_id: str) -> dict[str, Any] | None:
        return self._one("SELECT * FROM projects WHERE id = ?", (project_id,))

    def list_projects(self) -> list[dict[str, Any]]:
        return self._all("SELECT p.*, (SELECT COUNT(*) FROM runs r WHERE r.project_id = p.id) AS run_count FROM projects p ORDER BY created_at")

    # ---- runs ---------------------------------------------------------------------------------
    def insert_run(self, record: dict[str, Any]) -> None:
        totals = record.get("totals") or {}
        self._insert("runs", {
            "id": record["id"], "project_id": record.get("project", "default"), "task_id": record.get("task_id"), "input": record.get("input"),
            "status": record.get("status"), "harness_fingerprint": record.get("harness_fingerprint"), "started_at": record.get("started_at"),
            "ended_at": record.get("ended_at"), "cost_usd": totals.get("cost_usd"), "latency_ms": totals.get("latency_ms"), "tokens_in": totals.get("tokens_in"),
            "tokens_out": totals.get("tokens_out"), "tag": (record.get("meta") or {}).get("tag"), "record_json": record, "created_at": now_iso(),
        })

    def get_run(self, run_id: str) -> dict[str, Any] | None:
        return self._one("SELECT * FROM runs WHERE id = ?", (run_id,))

    def list_runs(self, project_id: str | None = None, *, tag: str | None = None, status: str | None = None, limit: int = 500, with_records: bool = False) -> list[dict[str, Any]]:
        cols = "*" if with_records else "id, project_id, task_id, input, status, harness_fingerprint, started_at, ended_at, cost_usd, latency_ms, tokens_in, tokens_out, tag, created_at"
        where, args = [], []
        if project_id:
            where.append("project_id = ?"); args.append(project_id)
        if tag:
            where.append("tag = ?"); args.append(tag)
        if status:
            where.append("status = ?"); args.append(status)
        sql = f"SELECT {cols} FROM runs" + (" WHERE " + " AND ".join(where) if where else "") + " ORDER BY task_id, created_at LIMIT ?"
        args.append(limit)
        return self._all(sql, tuple(args))

    def latest_runs_per_task(self, project_id: str, tag: str | None = None) -> list[dict[str, Any]]:
        """The most recent successful run of each task (the baseline set)."""
        runs = self.list_runs(project_id, tag=tag, status="ok", limit=5000, with_records=True)
        latest: dict[str, dict[str, Any]] = {}
        for r in runs:
            if r["task_id"] not in latest or r["created_at"] > latest[r["task_id"]]["created_at"]:
                latest[r["task_id"]] = r
        return [latest[k] for k in sorted(latest)]

    # ---- optimizations ------------------------------------------------------------------------
    def create_optimization(self, project_id: str, config: dict[str, Any], source: str = "live") -> dict[str, Any]:
        oid = new_id("opt")
        self._insert("optimizations", {"id": oid, "project_id": project_id, "status": "queued", "created_at": now_iso(), "started_at": None, "finished_at": None, "config_json": config, "split_json": None, "progress_json": {"phase": "queued", "percent": 0}, "summary_json": None, "error": None, "source": source})
        return self.get_optimization(oid)  # type: ignore[return-value]

    def update_optimization(self, oid: str, **fields: Any) -> None:
        self._update("optimizations", oid, fields)

    def get_optimization(self, oid: str) -> dict[str, Any] | None:
        return self._one("SELECT * FROM optimizations WHERE id = ?", (oid,))

    def list_optimizations(self, project_id: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        if project_id:
            return self._all("SELECT * FROM optimizations WHERE project_id = ? ORDER BY created_at DESC LIMIT ?", (project_id, limit))
        return self._all("SELECT * FROM optimizations ORDER BY created_at DESC LIMIT ?", (limit,))

    def count_live_optimizations_since(self, since_iso: str) -> int:
        row = self._one("SELECT COUNT(*) AS n FROM optimizations WHERE source = 'live' AND created_at >= ?", (since_iso,))
        return int(row["n"]) if row else 0

    # ---- options ------------------------------------------------------------------------------
    def create_option(self, optimization_id: str, key: str, label: str, target: str, position: int, harness: dict[str, Any] | None, harness_yaml: str | None) -> dict[str, Any]:
        oid = new_id("optn")
        self._insert("options", {"id": oid, "optimization_id": optimization_id, "key": key, "label": label, "target": target, "status": "pending", "position": position, "harness_json": harness, "harness_yaml": harness_yaml, "rounds_json": [], "metrics_json": None, "rationale": None, "created_at": now_iso()})
        return self.get_option(oid)  # type: ignore[return-value]

    def update_option(self, option_id: str, **fields: Any) -> None:
        self._update("options", option_id, fields)

    def get_option(self, option_id: str) -> dict[str, Any] | None:
        return self._one("SELECT * FROM options WHERE id = ?", (option_id,))

    def get_option_by_key(self, optimization_id: str, key: str) -> dict[str, Any] | None:
        return self._one("SELECT * FROM options WHERE optimization_id = ? AND key = ?", (optimization_id, key))

    def list_options(self, optimization_id: str) -> list[dict[str, Any]]:
        return self._all("SELECT * FROM options WHERE optimization_id = ? ORDER BY position", (optimization_id,))

    # ---- replays ------------------------------------------------------------------------------
    def insert_replay(self, data: dict[str, Any]) -> str:
        rid = data.get("id") or new_id("rep")
        self._insert("replays", {"id": rid, "created_at": now_iso(), **data})
        return rid

    def update_replay(self, replay_id: str, **fields: Any) -> None:
        self._update("replays", replay_id, fields)

    def get_replay(self, replay_id: str) -> dict[str, Any] | None:
        return self._one("SELECT * FROM replays WHERE id = ?", (replay_id,))

    def list_replays(self, option_id: str, *, split: str | None = None, round_: int | None = None, with_records: bool = True) -> list[dict[str, Any]]:
        cols = "*" if with_records else "id, optimization_id, option_id, task_id, baseline_run_id, split, round, status, judge_json, checks_json, metrics_json, created_at"
        where, args = ["option_id = ?"], [option_id]
        if split:
            where.append("split = ?"); args.append(split)
        if round_ is not None:
            where.append("round = ?"); args.append(round_)
        return self._all(f"SELECT {cols} FROM replays WHERE {' AND '.join(where)} ORDER BY task_id", tuple(args))

    def find_replay(self, option_id: str, task_id: str, split: str) -> dict[str, Any] | None:
        return self._one("SELECT * FROM replays WHERE option_id = ? AND task_id = ? AND split = ? ORDER BY round DESC LIMIT 1", (option_id, task_id, split))

    # ---- labels -------------------------------------------------------------------------------
    def get_labels(self, run_id: str) -> dict[str, Any] | None:
        row = self._one("SELECT labels_json FROM labels WHERE run_id = ?", (run_id,))
        return row["labels_json"] if row else None

    def set_labels(self, run_id: str, labels: dict[str, Any]) -> None:
        self._insert("labels", {"run_id": run_id, "labels_json": labels, "created_at": now_iso()})

    # ---- events -------------------------------------------------------------------------------
    def add_event(self, optimization_id: str, message: str, *, level: str = "info", phase: str = "", data: dict[str, Any] | None = None) -> None:
        self._insert("events", {"optimization_id": optimization_id, "ts": now_iso(), "level": level, "phase": phase, "message": message, "data_json": data})

    def list_events(self, optimization_id: str, after_id: int = 0, limit: int = 500) -> list[dict[str, Any]]:
        return self._all("SELECT * FROM events WHERE optimization_id = ? AND id > ? ORDER BY id LIMIT ?", (optimization_id, after_id, limit))

    # ---- PRs ----------------------------------------------------------------------------------
    def insert_pr(self, optimization_id: str, option_id: str, url: str | None, dry_run: bool, payload: dict[str, Any]) -> dict[str, Any]:
        pid = new_id("pr")
        self._insert("prs", {"id": pid, "optimization_id": optimization_id, "option_id": option_id, "created_at": now_iso(), "url": url, "dry_run": 1 if dry_run else 0, "payload_json": payload})
        return self._one("SELECT * FROM prs WHERE id = ?", (pid,))  # type: ignore[return-value]

    def list_prs(self, option_id: str) -> list[dict[str, Any]]:
        return self._all("SELECT * FROM prs WHERE option_id = ? ORDER BY created_at DESC", (option_id,))

    # ---- seed export / import -----------------------------------------------------------------
    def is_empty(self) -> bool:
        row = self._one("SELECT (SELECT COUNT(*) FROM runs) + (SELECT COUNT(*) FROM optimizations) AS n")
        return not row or int(row["n"]) == 0

    def export_all(self) -> dict[str, Any]:
        out: dict[str, Any] = {"exported_at": now_iso(), "tables": {}}
        with self._lock:
            for t in TABLES:
                out["tables"][t] = self._rows(self._conn.execute(f"SELECT * FROM {t}").fetchall())
        return out

    def import_all(self, dump: dict[str, Any]) -> dict[str, int]:
        counts: dict[str, int] = {}
        for t in TABLES:
            rows = dump.get("tables", {}).get(t) or []
            for row in rows:
                row = dict(row)
                if t == "events":
                    row.pop("id", None)
                self._insert(t, row)
            counts[t] = len(rows)
        return counts

    def export_to_file(self, path: str | Path) -> None:
        path = Path(path)
        path.parent.mkdir(parents=True, exist_ok=True)
        data = json.dumps(self.export_all(), ensure_ascii=False).encode("utf-8")
        if path.suffix == ".gz":
            path.write_bytes(gzip.compress(data))
        else:
            path.write_bytes(data)

    def import_from_file(self, path: str | Path) -> dict[str, int]:
        path = Path(path)
        raw = path.read_bytes()
        if path.suffix == ".gz":
            raw = gzip.decompress(raw)
        return self.import_all(json.loads(raw.decode("utf-8")))
