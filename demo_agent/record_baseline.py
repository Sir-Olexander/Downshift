"""Record baseline runs of the research agent with the Downshift SDK.

    uv run python demo_agent/record_baseline.py --limit 3            # quick check
    uv run python demo_agent/record_baseline.py --concurrency 4      # all questions

Runs are sent to the Downshift backend (DOWNSHIFT_ENDPOINT / DOWNSHIFT_API_KEY) or written to
--offline-dir as JSON files you can import later with `POST /v1/runs/import`.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

from downshift import Downshift
from research_agent.agent import ResearchAgent
from research_agent.env import load_env
from research_agent.tools import SearchTools

HERE = Path(__file__).resolve().parent


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--questions", default=str(HERE / "questions.json"))
    ap.add_argument("--harness", default=str(HERE / "harness.yaml"))
    ap.add_argument("--project", default="research-agent")
    ap.add_argument("--limit", type=int, default=0, help="only the first N questions")
    ap.add_argument("--only", default="", help="comma-separated question ids")
    ap.add_argument("--concurrency", type=int, default=3)
    ap.add_argument("--offline-dir", default="", help="write runs here instead of posting them")
    ap.add_argument("--endpoint", default=None)
    ap.add_argument("--api-key", default=None)
    ap.add_argument("--provider", default=None, help="tokenfactory | ollama | ollama-local | openai")
    ap.add_argument("--tag", default="baseline", help="meta.tag stored on each run")
    args = ap.parse_args()

    env_file = load_env()
    ds = Downshift(api_key=args.api_key, endpoint=args.endpoint, project=args.project, provider=args.provider, offline_dir=args.offline_dir or None)
    harness = ds.load_harness(args.harness)
    tools = SearchTools()
    questions = json.loads(Path(args.questions).read_text(encoding="utf-8"))
    if args.only:
        wanted = {x.strip() for x in args.only.split(",") if x.strip()}
        questions = [q for q in questions if q["id"] in wanted]
    if args.limit:
        questions = questions[: args.limit]

    print(f"env: {env_file or '(none)'}  provider: {ds.provider}  search: {tools.provider}")
    print(f"harness: {harness.name} v{harness.version} [{harness.fingerprint()}] models: {harness.models_used()}")
    print(f"recording {len(questions)} runs -> {'offline ' + args.offline_dir if args.offline_dir else ds.endpoint}\n")

    def one(q: dict) -> dict:
        t0 = time.time()
        with ds.run(task_id=q["id"], input=q["question"], harness=harness, meta={"tag": args.tag, "category": q.get("category"), "difficulty": q.get("difficulty"), "search_provider": tools.provider}) as run:
            agent = ResearchAgent(harness, run, tools)
            try:
                out = agent.answer(q["question"])
            except Exception as e:  # recorded as an error run; keep going
                run.fail(f"{type(e).__name__}: {e}")
                out = {"answer": "", "sources": []}
        rec = run.record
        return {"id": q["id"], "status": rec.status, "cost": rec.totals.cost_usd, "latency_s": rec.totals.latency_ms / 1000, "wall_s": time.time() - t0, "sources": len(out.get("sources") or []), "tokens": rec.totals.tokens_in + rec.totals.tokens_out, "error": rec.error}

    results = []
    with ThreadPoolExecutor(max_workers=max(1, args.concurrency)) as pool:
        futures = {pool.submit(one, q): q for q in questions}
        for fut in as_completed(futures):
            r = fut.result()
            results.append(r)
            flag = "ok " if r["status"] == "ok" else "ERR"
            print(f"{flag} {r['id']}  ${r['cost']:.4f}  {r['latency_s']:.1f}s  {r['tokens']} tok  {r['sources']} sources" + (f"  {r['error']}" if r["error"] else ""))
            sys.stdout.flush()

    ok = [r for r in results if r["status"] == "ok"]
    print(f"\n{len(ok)}/{len(results)} runs ok; total cost ${sum(r['cost'] for r in results):.4f}; avg latency {sum(r['latency_s'] for r in results)/max(1,len(results)):.1f}s")
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
