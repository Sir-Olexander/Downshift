"""Analysis: Nemotron 3 Nano labels every recorded step (kind, difficulty, whether it needs a strong model).

This is cheap, runs once per recorded run (cached), and tells the rewriter which steps can move to a
smaller model.
"""

from __future__ import annotations

import json
import re
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from typing import Any, Callable

from downshift import LLM

SYSTEM = """You label the steps of a recorded run of an LLM research agent so an optimizer can decide
which steps a smaller, cheaper model could handle. Be realistic: short, mechanical steps (writing search
queries, choosing a tool call) are usually easy; writing a correct, complete, well-cited answer from messy
evidence is harder. Respond with JSON only."""

USER = """Question: {question}
Question type guess and overall difficulty are yours to decide.

Recorded steps (in order):
{steps}

Respond with exactly this JSON:
{{"question_type": "fact|explain|compare|multi_hop", "question_difficulty": "easy|medium|hard",
 "steps": [{{"step": "<step id>", "kind": "search|read|synthesize|plan|verify", "difficulty": "easy|medium|hard",
            "needs_strong_model": true, "reason": "short reason"}}]}}
Include one entry per distinct step id."""


def _extract_json(text: str) -> dict[str, Any] | None:
    text = re.sub(r"^```[a-zA-Z]*\n?", "", text.strip())
    text = re.sub(r"\n?```$", "", text)
    try:
        v = json.loads(text)
        return v if isinstance(v, dict) else None
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            return None
        try:
            v = json.loads(m.group(0))
            return v if isinstance(v, dict) else None
        except json.JSONDecodeError:
            return None


def _summarise_steps(record: dict[str, Any]) -> str:
    lines = []
    by_step: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for e in record.get("events") or []:
        if e.get("type") == "model_call":
            by_step[e["step"]].append(e)
    for step_id, calls in by_step.items():
        tool_names = []
        last_content = ""
        for c in calls:
            for tc in (c.get("response") or {}).get("tool_calls") or []:
                tool_names.append(f"{tc.get('name')}({json.dumps(tc.get('arguments'), ensure_ascii=False)[:80]})")
            if (c.get("response") or {}).get("content"):
                last_content = c["response"]["content"]
        tokens_out = sum(int(c.get("tokens_out") or 0) for c in calls)
        lines.append(
            f"- step '{step_id}': {len(calls)} model call(s), {tokens_out} output tokens; "
            f"tool calls: {', '.join(tool_names) if tool_names else 'none'}; "
            f"final text: {last_content.strip()[:300]!r}"
        )
    return "\n".join(lines) if lines else "(no model calls recorded)"


def label_run(llm: LLM, model: str, record: dict[str, Any]) -> dict[str, Any]:
    msgs = [
        {"role": "system", "content": SYSTEM},
        {"role": "user", "content": USER.format(question=record.get("input", ""), steps=_summarise_steps(record))},
    ]
    res = llm.chat(model, msgs, temperature=0.0, max_tokens=700, reasoning="off")
    data = _extract_json(res.content) or {}
    steps = []
    for s in data.get("steps") or []:
        if not isinstance(s, dict):
            continue
        steps.append({
            "step": str(s.get("step", "")),
            "kind": str(s.get("kind", "")),
            "difficulty": str(s.get("difficulty", "medium")).lower(),
            "needs_strong_model": bool(s.get("needs_strong_model", False)),
            "reason": str(s.get("reason", ""))[:200],
        })
    return {
        "run_id": record.get("id"),
        "task_id": record.get("task_id"),
        "question_type": str(data.get("question_type", "")),
        "question_difficulty": str(data.get("question_difficulty", "")).lower(),
        "steps": steps,
        "model": model,
        "parsed": bool(data),
        "tokens_in": res.tokens_in,
        "tokens_out": res.tokens_out,
        "cost_usd": llm.table.cost(model, res.tokens_in, res.tokens_out),
    }


def summarise_labels(labels: list[dict[str, Any]]) -> dict[str, Any]:
    per_step: dict[str, dict[str, Any]] = {}
    for lab in labels:
        for s in lab.get("steps") or []:
            d = per_step.setdefault(s["step"], {"n": 0, "difficulty": Counter(), "needs_strong_model": 0, "kinds": Counter(), "reasons": []})
            d["n"] += 1
            d["difficulty"][s["difficulty"]] += 1
            d["needs_strong_model"] += 1 if s["needs_strong_model"] else 0
            d["kinds"][s["kind"]] += 1
            if len(d["reasons"]) < 3 and s.get("reason"):
                d["reasons"].append(s["reason"])
    out_steps = {}
    for step, d in per_step.items():
        n = d["n"] or 1
        out_steps[step] = {
            "n": d["n"],
            "kind": d["kinds"].most_common(1)[0][0] if d["kinds"] else "",
            "difficulty": {k: round(100 * v / n) for k, v in d["difficulty"].items()},
            "needs_strong_model_pct": round(100 * d["needs_strong_model"] / n),
            "sample_reasons": d["reasons"],
        }
    qtypes = Counter(l.get("question_type", "") for l in labels)
    qdiff = Counter(l.get("question_difficulty", "") for l in labels)
    recommendations = []
    for step, d in out_steps.items():
        if d["needs_strong_model_pct"] <= 35:
            recommendations.append(f"step '{step}' ({d['kind']}): a small model should handle it ({d['needs_strong_model_pct']}% judged to need a strong model)")
        elif d["needs_strong_model_pct"] >= 65:
            recommendations.append(f"step '{step}' ({d['kind']}): keep a strong model ({d['needs_strong_model_pct']}% judged to need one)")
        else:
            recommendations.append(f"step '{step}' ({d['kind']}): borderline ({d['needs_strong_model_pct']}% need a strong model); try a mid-size model or add a check")
    return {
        "runs_labelled": len(labels),
        "per_step": out_steps,
        "question_types": dict(qtypes),
        "question_difficulty": dict(qdiff),
        "recommendations": recommendations,
        "cost_usd": round(sum(float(l.get("cost_usd") or 0.0) for l in labels), 5),
    }


def analyze_runs(llm: LLM, model: str, records: list[dict[str, Any]], *, cache_get: Callable[[str], dict[str, Any] | None], cache_set: Callable[[str, dict[str, Any]], None], concurrency: int = 4, on_progress: Callable[[int, int], None] | None = None) -> dict[str, Any]:
    labels: list[dict[str, Any]] = []
    todo = []
    for r in records:
        cached = cache_get(r["id"])
        if cached:
            labels.append(cached)
        else:
            todo.append(r)
    done = len(labels)
    if on_progress:
        on_progress(done, len(records))
    with ThreadPoolExecutor(max_workers=max(1, concurrency)) as pool:
        futs = {pool.submit(label_run, llm, model, r): r for r in todo}
        for fut in as_completed(futs):
            r = futs[fut]
            try:
                lab = fut.result()
            except Exception as e:
                lab = {"run_id": r["id"], "task_id": r.get("task_id"), "steps": [], "error": f"{type(e).__name__}: {e}"[:300], "parsed": False, "cost_usd": 0.0}
            if lab.get("parsed"):
                cache_set(r["id"], lab)
            labels.append(lab)
            done += 1
            if on_progress:
                on_progress(done, len(records))
    summary = summarise_labels(labels)
    summary["labels"] = labels
    return summary
