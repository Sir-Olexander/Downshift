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


def compare(db: Database, oid: str, labels_csv: Path, key_json: Path) -> dict[str, Any]:
    """Agreement between the stored judge scores of `oid` and the filled-in labels.csv.

    Each labelled item is one answer (the baseline answer of a task, or one option's candidate answer);
    key.json says which. The judge's stored scores for that answer are averaged over the times it was
    judged (the baseline answer is judged once per option). Reports agreement on correct / complete /
    supported at the pipeline's bar (score >= 3, supported >= 4), false-pass and false-fail rates,
    Cohen's kappa, whether the judge's pairwise preference matches the labels when they differ, and the
    mean score by answer source among the answers the labels call correct (a same-quality bias check).
    """
    import csv
    from collections import Counter, defaultdict

    def yn(v: str) -> bool | None:
        return {"yes": True, "no": False}.get((v or "").strip().lower())

    labels: dict[str, dict[str, Any]] = {}
    for r in csv.DictReader(open(labels_csv, encoding="utf-8")):
        labels[r["item"]] = {"correct": yn(r["correct (yes/no)"]), "complete": yn(r["complete (yes/no)"]),
                             "unsupported": yn(r["unsupported claim (yes/no)"]), "side_detail": "(side detail)" in (r.get("notes") or ""),
                             "task_id": None, "source": None}
    for item, meta in json.loads(key_json.read_text()).items():
        if item in labels:
            labels[item].update(task_id=meta["task_id"], source=meta["source"])

    options = {o["key"]: o for o in db.list_options(oid) if o["key"] != "baseline"}
    judgements: dict[tuple[str, str], list[dict[str, Any]]] = defaultdict(list)
    preferred: dict[tuple[str, str], str | None] = {}
    for ok, o in options.items():
        for split in ("test", "opt"):
            for r in db.list_replays(o["id"], split=split):
                j = r.get("judge_json") or {}
                if not j.get("parsed"):
                    continue
                judgements[(r["task_id"], "baseline")].append(j.get("baseline") or {})
                judgements[(r["task_id"], ok)].append(j.get("candidate") or {})
                if split == "test" or (ok, r["task_id"]) not in preferred:
                    preferred[(ok, r["task_id"])] = j.get("preferred")

    items = []
    unmatched = [i for i, l in labels.items() if (l["task_id"], l["source"] if l["source"] != "baseline" else "baseline") not in judgements]
    for item, lab in labels.items():
        js = judgements.get((lab["task_id"], lab["source"] if lab["source"] != "baseline" else "baseline")) or []
        if not js:
            continue
        mean = lambda k: sum(float(j.get(k) or 0) for j in js) / len(js)  # noqa: E731
        items.append({**lab, "item": item, "n_judged": len(js), "jc": mean("correct"), "jm": mean("complete"), "js": mean("supported")})

    def kappa(a: list[bool], b: list[bool]) -> float | None:
        if not a:
            return None
        pa, pb = sum(a) / len(a), sum(b) / len(b)
        po = sum(x == y for x, y in zip(a, b)) / len(a)
        pe = pa * pb + (1 - pa) * (1 - pb)
        return round((po - pe) / (1 - pe), 3) if pe < 1 else 1.0

    def matrix(bar: float, human: str, judge_key: str, flip: bool = False) -> dict[str, Any]:
        # flip: the human flag is True when there IS a problem, the judge score is high when there is not
        jj = [i[judge_key] >= bar for i in items]
        hh = [(not i[human]) if flip else i[human] for i in items]
        n = len(hh)
        agree = sum(x == y for x, y in zip(jj, hh))
        fp = sum(j and not h for j, h in zip(jj, hh))  # judge passes, labels fail
        ff = sum(not j and h for j, h in zip(jj, hh))  # judge fails, labels pass
        out = {"n": n, "bar": bar, "agree_pct": round(100 * agree / n, 1) if n else None,
               "false_pass": fp, "false_fail": ff,
               "false_pass_pct": round(100 * fp / n, 1) if n else None,
               "false_fail_pct": round(100 * ff / n, 1) if n else None,
               "kappa": kappa(jj, hh)}
        if human == "correct":
            strict = [i for i in items if not i["side_detail"]]
            jj2 = [i[judge_key] >= bar for i in strict]; hh2 = [i[human] for i in strict]
            out["agree_pct_excl_side_details"] = round(100 * sum(x == y for x, y in zip(jj2, hh2)) / len(hh2), 1) if hh2 else None
        return out

    report: dict[str, Any] = {
        "optimization_id": oid, "n_labelled": len(labels), "n_compared": len(items), "n_unmatched": len(unmatched), "unmatched": unmatched,
        "human": {"correct_yes": sum(1 for i in items if i["correct"]), "correct_no": sum(1 for i in items if not i["correct"]),
                  "complete_no": sum(1 for i in items if not i["complete"]), "unsupported_yes": sum(1 for i in items if i["unsupported"])},
        "correct_vs_labels": {"bar3": matrix(3, "correct", "jc"), "bar4": matrix(4, "correct", "jc")},
        "complete_vs_labels": {"bar3": matrix(3, "complete", "jm")},
        "supported_vs_labels": {"bar4": matrix(4, "unsupported", "js", flip=True)},
    }
    # pairwise preference against the labels
    pairs: dict[str, dict[str, Any]] = {}
    for ok in options:
        for tid in {t for (t, s) in judgements if s == ok}:
            b = next((l for l in labels.values() if l["task_id"] == tid and l["source"] == "baseline"), None)
            c = next((l for l in labels.values() if l["task_id"] == tid and l["source"] == ok), None)
            if not (b and c and b["correct"] is not None and c["correct"] is not None) or (ok, tid) not in preferred:
                continue
            pref = preferred[(ok, tid)]
            if b["correct"] and not c["correct"]:
                right = "baseline"
            elif c["correct"] and not b["correct"]:
                right = "candidate"
            else:
                right = None
            k = "labels_differ" if right else "labels_equal"
            pairs.setdefault(k, Counter())["n"] += 1
            v = "right" if pref == right else ("wrong" if pref in ("baseline", "candidate") else "tie")
            pairs[k][str(pref) if right is None else v] += 1
    report["preference"] = {k: dict(v) for k, v in pairs.items()}
    # same-quality bias: mean judge score by answer source, among answers the labels call correct
    by_source = {}
    for src in ["baseline", *options]:
        xs = [i["jc"] for i in items if i["source"] == src and i["correct"]]
        ys = [i["jc"] for i in items if i["source"] == src and not i["correct"]]
        by_source[src] = {"n": len(xs) + len(ys), "n_correct": len(xs),
                          "mean_judge_correct_if_labelled_correct": round(sum(xs) / len(xs), 2) if xs else None,
                          "mean_judge_correct_if_labelled_wrong": round(sum(ys) / len(ys), 2) if ys else None}
    report["mean_judge_correct_by_source"] = by_source
    report["items"] = [{k: i[k] for k in ("item", "task_id", "source", "correct", "complete", "unsupported", "side_detail", "n_judged", "jc", "jm", "js")} for i in items]
    return report


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    sub = ap.add_subparsers(dest="cmd", required=True)
    a = sub.add_parser("audit"); a.add_argument("id"); a.add_argument("--judges", default="nemotron-3-ultra,glm-5.3"); a.add_argument("--json", default="")
    c = sub.add_parser("compare"); c.add_argument("id"); c.add_argument("--labels", default="docs/judge-validation/labels.csv"); c.add_argument("--key", default="docs/judge-validation/key.json"); c.add_argument("--json", default="")
    p = sub.add_parser("pack"); p.add_argument("id"); p.add_argument("--out", default="docs/judge-validation")
    args = ap.parse_args(argv)
    settings = Settings.from_env()
    db = Database(settings.db_path)
    if args.cmd == "compare":
        rep = compare(db, args.id, Path(args.labels), Path(args.key))
        if args.json:
            Path(args.json).write_text(json.dumps(rep, indent=1))
        print(json.dumps({k: v for k, v in rep.items() if k != "items"}, indent=1))
        return 0
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
