"""Per-run and aggregate metrics, plus the objective used to pick the best candidate."""

from __future__ import annotations

from typing import Any

from .judge import is_success, quality_score


def replay_metrics(record: dict[str, Any], judge: dict[str, Any] | None, checks: dict[str, Any]) -> dict[str, Any]:
    totals = record.get("totals") or {}
    scores = (judge or {}).get("candidate")
    return {
        "success": is_success(scores, checks),
        "quality": quality_score(scores),
        "checks_passed": bool(checks.get("passed")),
        "cost_usd": float(totals.get("cost_usd") or 0.0),
        "latency_ms": int(totals.get("latency_ms") or 0),
        "tokens_in": int(totals.get("tokens_in") or 0),
        "tokens_out": int(totals.get("tokens_out") or 0),
        "model_calls": int(totals.get("model_calls") or 0),
        "tool_calls": int(totals.get("tool_calls") or 0),
        "tool_calls_recorded": int(totals.get("tool_calls_recorded") or 0),
        "tool_calls_live": int(totals.get("tool_calls_live") or 0),
        "preferred": (judge or {}).get("preferred"),
        "status": record.get("status"),
    }


def baseline_run_metrics(record: dict[str, Any], judge: dict[str, Any] | None, checks: dict[str, Any]) -> dict[str, Any]:
    totals = record.get("totals") or {}
    scores = (judge or {}).get("baseline")
    return {
        "success": is_success(scores, checks),
        "quality": quality_score(scores),
        "checks_passed": bool(checks.get("passed")),
        "cost_usd": float(totals.get("cost_usd") or 0.0),
        "latency_ms": int(totals.get("latency_ms") or 0),
        "tokens_in": int(totals.get("tokens_in") or 0),
        "tokens_out": int(totals.get("tokens_out") or 0),
        "model_calls": int(totals.get("model_calls") or 0),
        "tool_calls": int(totals.get("tool_calls") or 0),
        "tool_calls_recorded": 0,
        "tool_calls_live": int(totals.get("tool_calls") or 0),
        "status": record.get("status"),
    }


def _mean(xs: list[float]) -> float | None:
    return round(sum(xs) / len(xs), 4) if xs else None


def aggregate(items: list[dict[str, Any]]) -> dict[str, Any]:
    n = len(items)
    if n == 0:
        return {"n": 0, "success_rate": None, "quality": None, "cost_per_run": None, "latency_ms": None}
    qualities = [float(i["quality"]) for i in items if i.get("quality") is not None]
    prefs = [i.get("preferred") for i in items if i.get("preferred")]
    wins = sum(1 for p in prefs if p == "candidate")
    ties = sum(1 for p in prefs if p == "tie")
    tool_calls = sum(i.get("tool_calls", 0) for i in items)
    live = sum(i.get("tool_calls_live", 0) for i in items)
    return {
        "n": n,
        "success_rate": round(100 * sum(1 for i in items if i.get("success")) / n, 1),
        "checks_pass_rate": round(100 * sum(1 for i in items if i.get("checks_passed")) / n, 1),
        "quality": round(sum(qualities) / len(qualities), 1) if qualities else None,
        "cost_per_run": _mean([float(i.get("cost_usd") or 0.0) for i in items]),
        "latency_ms": int(sum(int(i.get("latency_ms") or 0) for i in items) / n),
        "tokens_in": int(sum(int(i.get("tokens_in") or 0) for i in items) / n),
        "tokens_out": int(sum(int(i.get("tokens_out") or 0) for i in items) / n),
        "win_rate": round(100 * wins / len(prefs), 1) if prefs else None,
        "tie_rate": round(100 * ties / len(prefs), 1) if prefs else None,
        "live_tool_call_share": round(100 * live / tool_calls, 1) if tool_calls else 0.0,
        "errors": sum(1 for i in items if i.get("status") != "ok"),
    }


def deltas(option: dict[str, Any], baseline: dict[str, Any]) -> dict[str, Any]:
    def pct(a: Any, b: Any) -> float | None:
        if a is None or b in (None, 0):
            return None
        return round(100 * (float(a) - float(b)) / float(b), 1)

    def diff(a: Any, b: Any) -> float | None:
        if a is None or b is None:
            return None
        return round(float(a) - float(b), 1)

    return {
        "success_rate_pp": diff(option.get("success_rate"), baseline.get("success_rate")),
        "quality_pts": diff(option.get("quality"), baseline.get("quality")),
        "cost_pct": pct(option.get("cost_per_run"), baseline.get("cost_per_run")),
        "latency_pct": pct(option.get("latency_ms"), baseline.get("latency_ms")),
    }


def objective(metrics: dict[str, Any], baseline: dict[str, Any], *, tolerance_pp: float = 5.0) -> float:
    """Higher is better. Quality first, with a penalty when success drops more than the tolerance,
    and a small bonus for cost savings so equal-quality candidates prefer the cheaper harness."""
    q = float(metrics.get("quality") or 0.0)
    s = float(metrics.get("success_rate") or 0.0)
    bs = float(baseline.get("success_rate") or 0.0)
    penalty = max(0.0, (bs - tolerance_pp) - s) * 2.0
    cost_bonus = 0.0
    if baseline.get("cost_per_run") and metrics.get("cost_per_run") is not None:
        saving = 1.0 - float(metrics["cost_per_run"]) / float(baseline["cost_per_run"])
        cost_bonus = max(-10.0, min(10.0, saving * 10.0))
    return round(q - penalty + cost_bonus, 3)


def meets_bar(option: dict[str, Any], baseline: dict[str, Any], *, success_tol_pp: float = 5.0, quality_tol_pts: float = 5.0) -> bool:
    d = deltas(option, baseline)
    return (d["success_rate_pp"] is not None and d["success_rate_pp"] >= -success_tol_pp) and (d["quality_pts"] is not None and d["quality_pts"] >= -quality_tol_pts)
