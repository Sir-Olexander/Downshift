"""Run an optimization from the command line (also what a Nebius Serverless Job would run).

    uv run python -m app.cli optimize --targets super,nano,mix --rounds 2 --sample 10
    uv run python -m app.cli status <optimization id>
"""

from __future__ import annotations

import argparse
import json
import sys
import threading
import time

from .db import Database
from .optimizer.engine import Engine, default_config
from .optimizer.stats import describe
from .settings import Settings


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    o = sub.add_parser("optimize", help="run an optimization now, in this process")
    o.add_argument("--project", default="research-agent")
    o.add_argument("--targets", default="super,nano,mix")
    o.add_argument("--rounds", type=int, default=None)
    o.add_argument("--sample", type=int, default=None, help="runs replayed per round")
    o.add_argument("--test-fraction", type=float, default=None)
    o.add_argument("--concurrency", type=int, default=None)
    o.add_argument("--max-cost", type=float, default=None)
    o.add_argument("--seed", type=int, default=42)
    o.add_argument("--trials", type=int, default=None, help="replays per held-out task (default DOWNSHIFT_TEST_TRIALS or 1)")
    o.add_argument("--race", type=int, default=None, help="race the top candidates and the swap on this many unseen optimization tasks before choosing (default DOWNSHIFT_OPT_RACE or 0)")
    o.add_argument("--margin", type=float, default=None, help="non-inferiority margin in points (default 10)")
    o.add_argument("--source", default="seed", help="label stored on the optimization: seed (precomputed) or live")
    s = sub.add_parser("status", help="print an optimization's status and events")
    s.add_argument("id")
    r = sub.add_parser("resummarize", help="recompute checks, metrics and the summary of a finished optimization from its stored replays")
    r.add_argument("id")
    rd = sub.add_parser("redo", help="replay the held-out tasks of one option whose replays failed or are missing (e.g. after a provider outage), then rebuild the summary")
    rd.add_argument("id")
    rd.add_argument("option", help="option key: super | nano | mix")
    rd.add_argument("--all", action="store_true", help="redo every held-out replay of the option, not only the failed ones")
    vf = sub.add_parser("verify", help="fresh runs of every chosen harness, the plain swap and the baseline on the held-out tasks, next to the replay numbers")
    vf.add_argument("id")
    vf.add_argument("--trials", type=int, default=2)
    args = ap.parse_args(argv)

    settings = Settings.from_env()
    db = Database(settings.db_path)
    if args.cmd == "redo":
        out = Engine(db, settings).redo_test_replays(args.id, args.option, only_failed=not args.all)
        print(f"redone {out['redone']} replays")
        if out.get("summary"):
            print(json.dumps(out["summary"].get("headline"), indent=1))
        return 0
    if args.cmd == "verify":
        out = Engine(db, settings).verify(args.id, trials=args.trials)
        print(f"held-out tasks: {out['n_tasks']}, trials: {out['trials']}, spent ${out['spent_usd']}")
        for a in out["arms"]:
            print(f"{a['label']:40} passes per trial {a['passes_per_trial']}  cost/run ${a['cost_per_run']}" + (f"  (replay said {a['claimed_success_rate']}%)" if a.get("claimed_success_rate") is not None else ""))
            print("   " + describe(a["fresh"]))
        return 0
    if args.cmd == "resummarize":
        summary = Engine(db, settings).resummarize(args.id)
        print(json.dumps({k: summary.get(k) for k in ("headline", "baseline", "bar")}, indent=1))
        for row in summary.get("options") or []:
            print(row["key"], row["metrics"].get("success_rate"), row["metrics"].get("quality"), row["metrics"].get("cost_per_run"), "meets_bar" if row["meets_bar"] else "below_bar")
        return 0
    if args.cmd == "status":
        opt = db.get_optimization(args.id)
        if not opt:
            print("not found")
            return 1
        print(json.dumps({k: opt.get(k) for k in ("id", "status", "progress_json", "error", "finished_at")}, indent=1))
        for e in db.list_events(args.id):
            print(f"{e['ts']} [{e['phase']}] {e['message']}")
        return 0

    cfg = default_config(settings)
    cfg["targets"] = [t.strip() for t in args.targets.split(",") if t.strip()]
    for k, v in (("rounds", args.rounds), ("sample_size", args.sample), ("test_fraction", args.test_fraction), ("concurrency", args.concurrency), ("max_cost_usd", args.max_cost), ("test_trials", args.trials), ("race_size", args.race), ("noninferiority_pp", args.margin)):
        if v is not None:
            cfg[k] = v
    cfg["seed"] = args.seed
    opt = db.create_optimization(args.project, cfg, source=args.source)
    print(f"optimization {opt['id']} started with {json.dumps(cfg)}")
    engine = Engine(db, settings)
    seen = 0
    t = threading.Thread(target=engine.run, args=(opt["id"],), daemon=True)
    t.start()
    while t.is_alive():
        for e in db.list_events(opt["id"], after_id=seen):
            seen = e["id"]
            print(f"{e['ts'][11:19]} [{e['phase']}] {e['message']}")
            sys.stdout.flush()
        time.sleep(3)
    for e in db.list_events(opt["id"], after_id=seen):
        print(f"{e['ts'][11:19]} [{e['phase']}] {e['message']}")
    final = db.get_optimization(opt["id"])
    print("status:", final["status"], final.get("error") or "")
    if final.get("summary_json"):
        print(json.dumps({k: final["summary_json"].get(k) for k in ("headline", "baseline", "spent_usd")}, indent=1))
    return 0 if final["status"] == "done" else 1


if __name__ == "__main__":
    raise SystemExit(main())
