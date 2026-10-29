"""Replay: run an agent again with a new harness, serving recorded tool results when they match.

A tool call is served from the recording when it is the same tool with the same or very similar
arguments (same URL, or a search query with enough word overlap). Anything else runs live, which is
safe for read-only tools. Every tool event says which of the two happened.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Callable
from urllib.parse import urlsplit

from .tracing import Run, ToolCallEvent, now_iso

_WORD = re.compile(r"[a-z0-9]+")
# A URL runs until whitespace, a quote, an angle bracket or a CJK bracket; parentheses are allowed
# because Wikipedia titles use them (…/Trieste_(bathyscaphe)). Unbalanced closers are stripped after.
_URL = re.compile(r"https?://[^\s<>\"'\u3010\u3011]+")
_STOP = {"the", "a", "an", "of", "in", "on", "and", "or", "to", "for", "is", "what", "who", "when", "where", "how", "why", "which", "does", "do", "did", "was", "were", "are", "be"}


class ReplayMiss(LookupError):
    pass


def _words(s: str) -> set[str]:
    return {w for w in _WORD.findall(s.lower()) if w not in _STOP}


def jaccard(a: str, b: str) -> float:
    wa, wb = _words(a), _words(b)
    if not wa and not wb:
        return 1.0
    if not wa or not wb:
        return 0.0
    return len(wa & wb) / len(wa | wb)


def clean_url(u: str) -> str:
    """Strip trailing punctuation and unbalanced closing brackets from a URL found in prose."""
    u = u.rstrip(".,;:!?\"'")
    while u:
        last = u[-1]
        if last == ")" and u.count("(") < u.count(")"):
            u = u[:-1]
        elif last == "]" and u.count("[") < u.count("]"):
            u = u[:-1]
        elif last in ".,;:!?\"'":
            u = u[:-1]
        else:
            break
    return u


def extract_urls(text: str) -> list[str]:
    """Every distinct http(s) URL in `text`, in order of first appearance."""
    out: list[str] = []
    for m in _URL.finditer(text or ""):
        u = clean_url(m.group(0))
        if u and u not in out:
            out.append(u)
    return out


def norm_url(u: str) -> str:
    try:
        parts = urlsplit(u.strip())
    except ValueError:
        return u.strip().lower()
    host = (parts.netloc or "").lower()
    if host.startswith("www."):
        host = host[4:]
    path = (parts.path or "/").rstrip("/") or "/"
    query = f"?{parts.query}" if parts.query else ""
    return f"{host}{path}{query}"


def canonical_args(args: dict[str, Any]) -> str:
    def norm(v: Any) -> Any:
        if isinstance(v, str):
            return " ".join(v.lower().split())
        if isinstance(v, dict):
            return {k: norm(x) for k, x in sorted(v.items())}
        if isinstance(v, list):
            return [norm(x) for x in v]
        return v

    return json.dumps(norm(args), sort_keys=True, ensure_ascii=False)


@dataclass
class ReplayHit:
    result: Any
    latency_ms: int
    matched_args: dict[str, Any]
    score: float
    kind: str  # "exact" | "similar"


class ReplayCache:
    """Index of the tool calls of a recorded run."""

    def __init__(self, events: list[dict[str, Any]], *, min_similarity: float = 0.6):
        self.min_similarity = min_similarity
        self.by_name: dict[str, list[dict[str, Any]]] = {}
        for ev in events:
            if ev.get("type") != "tool_call" or ev.get("error"):
                continue
            self.by_name.setdefault(ev["name"], []).append(ev)
        self.hits = 0
        self.misses = 0

    def lookup(self, name: str, args: dict[str, Any]) -> ReplayHit | None:
        cands = self.by_name.get(name, [])
        if not cands:
            self.misses += 1
            return None
        key = canonical_args(args)
        for ev in cands:
            if canonical_args(ev.get("args") or {}) == key:
                self.hits += 1
                return ReplayHit(ev.get("result"), int(ev.get("latency_ms") or 0), ev.get("args") or {}, 1.0, "exact")
        best: tuple[float, dict[str, Any]] | None = None
        for ev in cands:
            score = self._similarity(args, ev.get("args") or {})
            if score is not None and (best is None or score > best[0]):
                best = (score, ev)
        if best and best[0] >= self.min_similarity:
            score, ev = best
            self.hits += 1
            return ReplayHit(ev.get("result"), int(ev.get("latency_ms") or 0), ev.get("args") or {}, score, "similar")
        self.misses += 1
        return None

    @staticmethod
    def _similarity(a: dict[str, Any], b: dict[str, Any]) -> float | None:
        if "url" in a and "url" in b:
            return 1.0 if norm_url(str(a["url"])) == norm_url(str(b["url"])) else 0.0
        if "query" in a and "query" in b:
            return jaccard(str(a["query"]), str(b["query"]))
        return None


class ReplayRun(Run):
    """A Run whose tool calls are answered from a recording when they match.

    reuse_tool_results=False runs every tool live: use it for agents whose tools change state
    (a recorded "refund issued" must not stand in for a refund the replay never made)."""

    def __init__(self, *, recorded: dict[str, Any], allow_live: bool = True, reuse_tool_results: bool = True, **kwargs: Any):
        meta = dict(kwargs.pop("meta", None) or {})
        meta.setdefault("replay_of", recorded.get("id"))
        super().__init__(meta=meta, mode="replay", **kwargs)
        self.recorded = recorded
        self.cache = ReplayCache(recorded.get("events") or [])
        self.allow_live = allow_live
        self.reuse_tool_results = reuse_tool_results

    def tool(self, name: str, args: dict[str, Any], fn: Callable[[], Any], *, step: str | None = None) -> Any:
        if not self.reuse_tool_results:
            return super().tool(name, args, fn, step=step)
        hit = self.cache.lookup(name, args)
        if hit is not None:
            ev = ToolCallEvent(
                index=len(self.rec.events),
                step=step,
                ts=now_iso(),
                name=name,
                args=args,
                result=hit.result,
                latency_ms=hit.latency_ms,
                source="recorded",
                matched_args={"args": hit.matched_args, "score": round(hit.score, 3), "match": hit.kind},
            )
            self._add(ev)
            return hit.result
        if not self.allow_live:
            raise ReplayMiss(f"no recorded result for {name}({args}) and live calls are disabled")
        return super().tool(name, args, fn, step=step)
