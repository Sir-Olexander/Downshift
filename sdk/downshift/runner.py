"""Run an adapted agent (see downshift.adapter) from its own folder and environment.

    python -m downshift.runner check                      # load adapter, harness and tasks; no model calls
    python -m downshift.runner init-harness               # write the adapter's default harness.yaml
    python -m downshift.runner record --limit 5           # record baseline runs, graded, sent to the API
    python -m downshift.runner replay < job.json          # used by the Downshift server (JSON lines out)

Run it with the agent's own Python (e.g. `.venv/bin/python -m downshift.runner record`) from the
agent folder, or pass --folder.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from typing import Any

from . import Downshift
from .adapter import (
    AgentAdapter,
    Task,
    grade,
    load_adapter,
    load_agent_config,
    load_tasks,
    task_meta,
)
from .harness import Harness
from .transport import NullTransport


def _paths(args: argparse.Namespace) -> tuple[Path, dict[str, Any]]:
    folder = Path(args.folder).resolve()
    return folder, load_agent_config(folder)


def _run_one(ds: Downshift, adapter: AgentAdapter, harness: Harness, task: Task, meta: dict[str, Any]) -> dict[str, Any]:
    with ds.run(task_id=task.id, input=task.input, harness=harness, meta={**meta, **task_meta(task)}) as run:
        try:
            adapter.run(task, harness, run)
        except Exception as e:  # recorded as an error run; keep going
            run.fail(f"{type(e).__name__}: {e}")
        grade(adapter, task, run)
    return run.record.model_dump(mode="json")


def _replay_one(ds: Downshift, adapter: AgentAdapter, harness: Harness, recorded: dict[str, Any], meta: dict[str, Any]) -> dict[str, Any]:
    task = Task.from_record(recorded)
    with ds.replay(recorded=recorded, harness=harness, meta={**meta, **task_meta(task)}, transport=NullTransport(), reuse_tool_results=getattr(adapter, "reuse_tool_results", True)) as run:
        try:
            adapter.run(task, harness, run)
        except Exception as e:  # the scorer counts it as a failure
            run.fail(f"{type(e).__name__}: {e}")
        grade(adapter, task, run)
    return run.record.model_dump(mode="json")


def cmd_check(args: argparse.Namespace) -> int:
    folder, cfg = _paths(args)
    adapter = load_adapter(folder, cfg["entry"])
    out: dict[str, Any] = {"folder": str(folder), "entry": cfg["entry"], "adapter": getattr(adapter, "name", "agent"), "reuse_tool_results": getattr(adapter, "reuse_tool_results", True), "grader": type(adapter).score is not AgentAdapter.score}
    hp = folder / (args.harness or cfg["harness"])
    if hp.is_file():
        h = Harness.load(hp)
        out["harness"] = {"name": h.name, "runtime": h.runtime, "fingerprint": h.fingerprint(), "steps": [s.id for s in h.steps if s.enabled], "tools": list(h.tools), "models": h.models_used()}
    else:
        out["harness"] = None
    tp = folder / (args.tasks or cfg["tasks"])
    if tp.is_file():
        tasks = load_tasks(tp)
        out["tasks"] = {"file": tp.name, "n": len(tasks), "with_expected": sum(1 for t in tasks if t.expected is not None)}
    else:
        out["tasks"] = None
    print(json.dumps(out, indent=1))
    return 0


def cmd_init_harness(args: argparse.Namespace) -> int:
    folder, cfg = _paths(args)
    adapter = load_adapter(folder, cfg["entry"])
    h = adapter.default_harness()
    if h is None:
        print("this adapter has no default_harness(); write harness.yaml by hand", file=sys.stderr)
        return 1
    if args.stdout:
        sys.stdout.write(h.to_yaml())
        return 0
    target = folder / (args.harness or cfg["harness"])
    if target.exists() and not args.force:
        print(f"{target} exists; pass --force to overwrite", file=sys.stderr)
        return 1
    h.save(target)
    print(f"wrote {target} ({h.name}, runtime {h.runtime}, fingerprint {h.fingerprint()})")
    return 0


def cmd_record(args: argparse.Namespace) -> int:
    folder, cfg = _paths(args)
    adapter = load_adapter(folder, cfg["entry"])
    harness = Harness.load(folder / (args.harness or cfg["harness"]))
    project = args.project or os.environ.get("DOWNSHIFT_PROJECT") or harness.name
    ds = Downshift(api_key=args.api_key, endpoint=args.endpoint, project=project, provider=args.provider, offline_dir=args.offline_dir or None)
    harness.validate_models(ds.table, ds.provider)
    tasks = load_tasks(folder / (args.tasks or cfg["tasks"]))
    if args.only:
        wanted = {x.strip() for x in args.only.split(",") if x.strip()}
        tasks = [t for t in tasks if t.id in wanted]
    if args.limit:
        tasks = tasks[: args.limit]
    print(f"agent: {getattr(adapter, 'name', 'agent')}  provider: {ds.provider}  project: {ds.project}")
    print(f"harness: {harness.name} v{harness.version} [{harness.fingerprint()}] models: {harness.models_used()}")
    print(f"recording {len(tasks)} runs -> {'offline ' + args.offline_dir if args.offline_dir else ds.endpoint}\n", flush=True)
    meta = {"tag": args.tag, "adapter": getattr(adapter, "name", "agent")}
    results = []
    with ThreadPoolExecutor(max_workers=max(1, args.concurrency)) as pool:
        futs = {pool.submit(_run_one, ds, adapter, harness, t, meta): t for t in tasks}
        for fut in as_completed(futs):
            rec = fut.result()
            results.append(rec)
            sc = rec.get("score")
            grade_txt = "" if sc is None else ("PASS" if sc["passed"] else "fail")
            t = rec["totals"]
            print(f"{'ok ' if rec['status'] == 'ok' else 'ERR'} {rec['task_id']}  {grade_txt:4}  ${t['cost_usd']:.4f}  {t['latency_ms'] / 1000:.1f}s  {t['tokens_in'] + t['tokens_out']} tok" + (f"  {rec['error'][:160]}" if rec.get("error") else ""), flush=True)
    ok = [r for r in results if r["status"] == "ok"]
    graded = [r for r in results if r.get("score") is not None]
    passed = sum(1 for r in graded if r["score"]["passed"])
    print(f"\n{len(ok)}/{len(results)} runs ok; graded {len(graded)}: {passed} passed; total cost ${sum(r['totals']['cost_usd'] for r in results):.4f}")
    return 0 if ok else 1


def cmd_replay(args: argparse.Namespace) -> int:
    """Read a job on stdin, write one JSON line per finished replay on stdout.

    Job: {"harness": {...}, "records": [baseline run records], "meta": {...}, "provider": str|null, "concurrency": int}
    Line: {"index": i, "record": {...}}  (or {"index": i, "error": "..."} if the replay could not run at all)
    """
    # The agent may print; keep the protocol channel clean by sending fd 1 to stderr.
    proto = os.fdopen(os.dup(1), "w", buffering=1, encoding="utf-8")
    os.dup2(2, 1)
    sys.stdout = sys.stderr
    folder, cfg = _paths(args)
    job = json.loads(sys.stdin.read())
    adapter = load_adapter(folder, cfg["entry"])
    ds = Downshift(transport=NullTransport(), provider=job.get("provider"), project=job.get("project"))
    harness = Harness.from_dict(job["harness"])
    harness.validate_models(ds.table, ds.provider)
    records = job.get("records") or []
    meta = job.get("meta") or {}
    lock = threading.Lock()

    def work(i: int) -> None:
        try:
            line = {"index": i, "record": _replay_one(ds, adapter, harness, records[i], meta)}
        except Exception as e:
            line = {"index": i, "error": f"{type(e).__name__}: {e}"[:1000]}
        with lock:
            proto.write(json.dumps(line, ensure_ascii=False) + "\n")
            proto.flush()

    with ThreadPoolExecutor(max_workers=max(1, int(job.get("concurrency") or 3))) as pool:
        list(pool.map(work, range(len(records))))
    proto.close()
    return 0


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    for name in ("check", "init-harness", "record", "replay"):
        p = sub.add_parser(name)
        p.add_argument("--folder", default=".", help="the agent folder (default: current directory)")
        p.add_argument("--harness", default=None, help="harness file, relative to the folder")
        p.add_argument("--tasks", default=None, help="tasks file, relative to the folder")
        if name == "init-harness":
            p.add_argument("--force", action="store_true")
            p.add_argument("--stdout", action="store_true", help="print the harness instead of writing it")
        if name == "record":
            p.add_argument("--project", default=None, help="project id the runs are recorded under")
            p.add_argument("--limit", type=int, default=0)
            p.add_argument("--only", default="", help="comma-separated task ids")
            p.add_argument("--concurrency", type=int, default=3)
            p.add_argument("--provider", default=None, help="tokenfactory | ollama | ollama-local | openai")
            p.add_argument("--offline-dir", default="", help="write runs here instead of posting them")
            p.add_argument("--endpoint", default=None)
            p.add_argument("--api-key", default=None)
            p.add_argument("--tag", default="baseline")
    args = ap.parse_args(argv)
    t0 = time.time()
    rc = {"check": cmd_check, "init-harness": cmd_init_harness, "record": cmd_record, "replay": cmd_replay}[args.cmd](args)
    if args.cmd == "record":
        print(f"done in {time.time() - t0:.0f}s")
    return rc


if __name__ == "__main__":
    raise SystemExit(main())
