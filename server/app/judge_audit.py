"""Audit the LLM judge on a finished optimization's held-out pairs, and export a human-labelling pack.

    uv run python -m app.judge_audit audit <optimization id> --judges nemotron-3-ultra,glm-5.3
    uv run python -m app.judge_audit pack  <optimization id> --out docs/judge-validation

audit: every held-out (baseline, candidate) pair is judged twice by each judge, once in each order.
Reports position consistency (the same winner in both orders), how often each judge prefers the
baseline, ties, and agreement between judges. A judge from another family is the check for
self-preference (the baseline here is Nemotron 3 Ultra, the default judge is Nemotron 3 Ultra too).
pack: a CSV of every distinct answer (baseline runs and held-out candidates) in random order without
model labels, with empty columns for a human to fill in, and a separate key file. Human labels are what
the judge is finally validated against (docs/research/evaluation-methodology.md, section 7e).
"""

from __future__ import annotations

import argparse
import csv
import json
import random
import sys
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Any

from downshift import LLM, default_table

from .db import Database
from .optimizer.judge import judge_pair
from .settings import Settings


class _Fixed:
    def __init__(self, v: float):
        self.v = v

    def random(self) -> float:
        return self.v


def _pairs(db: Database, oid: str, splits: tuple[str, ...] = ("test",)) -> list[dict[str, Any]]:
    out = []
    for o in db.list_options(oid):
        if o["key"] == "baseline":
            continue
        for r in [x for sp in splits for x in db.list_replays(o["id"], split=sp)]:
            base = db.get_run(r["baseline_run_id"]) if hasattr(db, "get_run") else None
            base_rec = (base or {}).get("record_json") or {}
            out.append({"option": o["key"], "task_id": r["task_id"], "question": base_rec.get("input") or r["record_json"].get("input", ""),
                        "baseline": (base_rec.get("output") or {}).get("answer", ""), "candidate": (r["record_json"].get("output") or {}).get("answer", ""),
                        "stored": (r.get("judge_json") or {}).get("preferred")})
    return out


def audit(db: Database, settings: Settings, oid: str, judges: list[str], workers: int = 3) -> dict[str, Any]:
    pairs = _pairs(db, oid)
    llm = LLM(settings.provider, table=default_table())

    def judge_both(args: tuple[str, dict[str, Any]]) -> dict[str, Any]:
        model, p = args
        a = judge_pair(llm, model, p["question"], p["baseline"], p["candidate"], rng=_Fixed(0.1))  # candidate shown first
        b = judge_pair(llm, model, p["question"], p["baseline"], p["candidate"], rng=_Fixed(0.9))  # baseline shown first
        return {"judge": model, "option": p["option"], "task_id": p["task_id"], "cand_first": a.get("preferred"), "base_first": b.get("preferred"), "cost": float(a.get("cost_usd") or 0) + float(b.get("cost_usd") or 0)}

    with ThreadPoolExecutor(max_workers=workers) as pool:
        rows = list(pool.map(judge_both, [(j, p) for j in judges for p in pairs]))
    report: dict[str, Any] = {"optimization_id": oid, "n_pairs": len(pairs), "judges": {}}
    for j in judges:
        rs = [r for r in rows if r["judge"] == j and r["cand_first"] and r["base_first"]]
        n = len(rs)
        consistent = sum(1 for r in rs if r["cand_first"] == r["base_first"])
        prefs = [x for r in rs for x in (r["cand_first"], r["base_first"])]
        report["judges"][j] = {
            "n_pairs_parsed": n,
            "position_consistency_pct": round(100 * consistent / n, 1) if n else None,
            "prefers_baseline_pct": round(100 * prefs.count("baseline") / len(prefs), 1) if prefs else None,
            "prefers_candidate_pct": round(100 * prefs.count("candidate") / len(prefs), 1) if prefs else None,
            "tie_pct": round(100 * prefs.count("tie") / len(prefs), 1) if prefs else None,
            "cost_usd": round(sum(r["cost"] for r in rows if r["judge"] == j), 4),
        }
    if len(judges) >= 2:
        a, b = judges[0], judges[1]
        by = {(r["option"], r["task_id"], r["judge"]): r for r in rows}
        agree = total = 0
        for p in pairs:
            ra, rb = by.get((p["option"], p["task_id"], a)), by.get((p["option"], p["task_id"], b))
            if ra and rb and ra["cand_first"] and rb["cand_first"] and ra["cand_first"] == ra["base_first"] and rb["cand_first"] == rb["base_first"]:
                total += 1
                agree += ra["cand_first"] == rb["cand_first"]
        report["agreement_on_consistent_pairs"] = {"judges": [a, b], "n": total, "agree_pct": round(100 * agree / total, 1) if total else None}
    report["rows"] = rows
    return report


def pack(db: Database, oid: str, out: Path, seed: int = 7) -> int:
    items = []
    seen = set()
    for p in _pairs(db, oid, ("test", "opt")):
        for source, text in (("baseline", p["baseline"]), (p["option"], p["candidate"])):
            key = (p["task_id"], source)
            if key in seen or not (text or "").strip():
                continue
            seen.add(key)
            items.append({"task_id": p["task_id"], "source": source, "question": p["question"], "answer": text})
    random.Random(seed).shuffle(items)
    out.mkdir(parents=True, exist_ok=True)
    with (out / "labels.csv").open("w", newline="", encoding="utf-8") as f:
        w = csv.writer(f)
        w.writerow(["item", "question", "answer", "correct (yes/no)", "complete (yes/no)", "unsupported claim (yes/no)", "notes"])
        for i, it in enumerate(items, 1):
            w.writerow([f"i{i:03d}", it["question"], it["answer"], "", "", "", ""])
    (out / "key.json").write_text(json.dumps({f"i{i:03d}": {"task_id": it["task_id"], "source": it["source"]} for i, it in enumerate(items, 1)}, indent=1))
    return len(items)


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("audit"); a.add_argument("id"); a.add_argument("--judges", default="nemotron-3-ultra,glm-5.3"); a.add_argument("--json", default="")
    p = sub.add_parser("pack"); p.add_argument("id"); p.add_argument("--out", default="docs/judge-validation")
    args = ap.parse_args(argv)
    settings = Settings.from_env()
    db = Database(settings.db_path)
    if args.cmd == "pack":
        print(f"{pack(db, args.id, Path(args.out))} items written to {args.out}/labels.csv (key in key.json)")
        return 0
    rep = audit(db, settings, args.id, [j.strip() for j in args.judges.split(",") if j.strip()])
    if args.json:
        Path(args.json).write_text(json.dumps(rep, indent=1))
    print(json.dumps({k: v for k, v in rep.items() if k != "rows"}, indent=1))
    return 0


if __name__ == "__main__":
    sys.exit(main())
