"""Scoring: automatic checks plus a blind, order-randomised LLM judge on Nemotron 3 Ultra."""

from __future__ import annotations

import json
import random
import re
from typing import Any

from downshift import LLM
from downshift.replay import extract_urls, norm_url

JUDGE_SYSTEM = """You are a strict grader of research answers. You compare two answers to the same question.
Grade substance, not style or length. Penalise unsupported claims, factual errors and missing parts of the question.
Answers that admit the evidence is insufficient score higher on 'supported' than answers that guess.
Respond with JSON only."""

JUDGE_USER = """Question:
{question}

Answer A:
{a}

Answer B:
{b}

Score each answer from 0 to 5 on:
- correct: the facts, dates and numbers are right; no errors
- complete: it covers every part of the question
- supported: the claims are backed by the cited sources, and sources are listed

Then say which answer is better overall ("A", "B" or "tie"; use "tie" when they are equally good).

Respond with exactly this JSON:
{{"A": {{"correct": 0, "complete": 0, "supported": 0}}, "B": {{"correct": 0, "complete": 0, "supported": 0}}, "preferred": "A|B|tie", "reason": "one or two sentences"}}"""

MIN_ANSWER_CHARS = 40


def _extract_json(text: str) -> dict[str, Any] | None:
    text = text.strip()
    text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
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


def _clamp(v: Any) -> int:
    try:
        return max(0, min(5, int(round(float(v)))))
    except (TypeError, ValueError):
        return 0


def _scores(d: Any) -> dict[str, int]:
    d = d if isinstance(d, dict) else {}
    return {k: _clamp(d.get(k)) for k in ("correct", "complete", "supported")}


def quality_score(scores: dict[str, Any] | None) -> float | None:
    """0-100: mean of the three rubric scores."""
    if not scores:
        return None
    vals = [float(scores.get(k, 0)) for k in ("correct", "complete", "supported")]
    return round(sum(vals) / (5 * len(vals)) * 100, 1)


def auto_checks(record: dict[str, Any]) -> dict[str, Any]:
    """Simple deterministic checks on a run record."""
    output = record.get("output") or {}
    answer = (output.get("answer") or "").strip()
    # Re-extract the cited URLs from the answer text, so a fix to the extractor applies to old records too.
    sources = extract_urls(answer) if answer else [s for s in (output.get("sources") or []) if isinstance(s, str)]
    events = record.get("events") or []
    tool_events = [e for e in events if e.get("type") == "tool_call"]
    # tool errors are recovered by the agent (it sees an error result); only failed model calls count
    model_errors = [e for e in events if e.get("type") == "model_call" and e.get("error")]
    # URLs the tools actually returned during this run
    seen_urls: set[str] = set()
    for e in tool_events:
        res = e.get("result")
        if isinstance(res, dict):
            for r in res.get("results") or []:
                if isinstance(r, dict) and r.get("url"):
                    seen_urls.add(norm_url(r["url"]))
            if res.get("url"):
                seen_urls.add(norm_url(res["url"]))
    cited_known = [s for s in sources if norm_url(s) in seen_urls]
    checks = {
        "answer_produced": len(answer) >= MIN_ANSWER_CHARS,
        "has_sources": len(sources) > 0,
        "sources_from_evidence": bool(sources) and len(cited_known) == len(sources),
        "tools_used": len(tool_events) > 0,
        "no_errors": record.get("status") == "ok" and not model_errors,
        "n_sources": len(sources),
        "n_unknown_sources": len(sources) - len(cited_known),
        "n_tool_calls": len(tool_events),
    }
    checks["passed"] = bool(checks["answer_produced"] and checks["has_sources"] and checks["no_errors"] and checks["sources_from_evidence"])
    return checks


def judge_pair(llm: LLM, model: str, question: str, baseline_answer: str, candidate_answer: str, *, rng: random.Random | None = None, max_chars: int = 6000) -> dict[str, Any]:
    """Blind pairwise judgement. The judge sees 'A' and 'B' in random order."""
    rng = rng or random.Random()
    candidate_first = rng.random() < 0.5
    a, b = (candidate_answer, baseline_answer) if candidate_first else (baseline_answer, candidate_answer)
    a = (a or "(no answer)")[:max_chars]
    b = (b or "(no answer)")[:max_chars]
    msgs = [
        {"role": "system", "content": JUDGE_SYSTEM},
        {"role": "user", "content": JUDGE_USER.format(question=question, a=a, b=b)},
    ]
    res = llm.chat(model, msgs, temperature=0.0, max_tokens=900, reasoning="off")
    data = _extract_json(res.content) or {}
    attempts = 1
    if not data or not isinstance(data.get("A"), dict) or not isinstance(data.get("B"), dict):
        res = llm.chat(model, msgs + [{"role": "assistant", "content": res.content}, {"role": "user", "content": "Reply with the JSON object only."}], temperature=0.0, max_tokens=900, reasoning="off")
        data = _extract_json(res.content) or {}
        attempts = 2
    if not data or not isinstance(data.get("A"), dict) or not isinstance(data.get("B"), dict):
        # unknown verdict: the run is excluded from judged metrics instead of scored as zero
        return {"model": model, "order": "candidate_first" if candidate_first else "baseline_first", "candidate": None, "baseline": None, "candidate_quality": None, "baseline_quality": None, "preferred": None, "reason": "", "parsed": False, "attempts": attempts, "raw": (res.content or "")[:400], "tokens_in": res.tokens_in, "tokens_out": res.tokens_out, "cost_usd": llm.table.cost(model, res.tokens_in, res.tokens_out), "latency_ms": res.latency_ms}
    scores_a, scores_b = _scores(data.get("A")), _scores(data.get("B"))
    pref = str(data.get("preferred", "tie")).strip().upper()
    pref = pref if pref in {"A", "B", "TIE"} else "TIE"
    if candidate_first:
        cand, base = scores_a, scores_b
        preferred = {"A": "candidate", "B": "baseline", "TIE": "tie"}[pref]
    else:
        cand, base = scores_b, scores_a
        preferred = {"A": "baseline", "B": "candidate", "TIE": "tie"}[pref]
    return {
        "model": model,
        "order": "candidate_first" if candidate_first else "baseline_first",
        "candidate": cand,
        "baseline": base,
        "candidate_quality": quality_score(cand),
        "baseline_quality": quality_score(base),
        "preferred": preferred,
        "reason": str(data.get("reason", ""))[:600],
        "parsed": True,
        "attempts": attempts,
        "tokens_in": res.tokens_in,
        "tokens_out": res.tokens_out,
        "cost_usd": llm.table.cost(model, res.tokens_in, res.tokens_out),
        "latency_ms": res.latency_ms,
    }


def is_success(scores: dict[str, Any] | None, checks: dict[str, Any] | None) -> bool:
    """A run succeeds when it produced a sourced answer without errors and the judge found it correct."""
    if not scores or not checks:
        return False
    return bool(checks.get("passed")) and int(scores.get("correct", 0)) >= 3
