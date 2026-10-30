"""Statistics for held-out results: intervals, paired differences on the same tasks, and verdicts.

Why this exists: a pass rate on 16 tasks has a 95% interval of about ±22 points, and a single replay
per task cannot separate a rewrite from the plain swap. So every held-out comparison is paired per task
(the same tasks, candidate against baseline and against the plain swap), uncertainty comes from a
bootstrap over tasks (trials of one task stay together), and the "bar" is a non-inferiority test with
an explicit margin and an "inconclusive" verdict instead of a point-estimate rule.
See docs/research/evaluation-methodology.md for the sources.
"""

from __future__ import annotations

import math
import random
from typing import Any


def wilson(k: int, n: int, z: float = 1.96) -> tuple[float | None, float | None]:
    """Wilson score interval for k successes in n, in percent."""
    if n <= 0:
        return (None, None)
    p = k / n
    d = 1 + z * z / n
    c = p + z * z / (2 * n)
    h = z * math.sqrt(p * (1 - p) / n + z * z / (4 * n * n))
    return (round(100 * (c - h) / d, 1), round(100 * (c + h) / d, 1))


def per_task(items: list[dict[str, Any]], key: str = "metrics") -> dict[str, list[float]]:
    """task_id -> one 0/1 per trial (unjudged runs are left out)."""
    out: dict[str, list[float]] = {}
    for x in items:
        m = x.get(key) or {}
        if m.get("judged") is False:
            continue
        out.setdefault(str(x["task_id"]), []).append(1.0 if m.get("success") else 0.0)
    return out


def pass_rates(pt: dict[str, list[float]]) -> dict[str, float | None]:
    """pass^1: mean per-task success rate; pass^k: share of tasks passed in every trial."""
    n = len(pt)
    if not n:
        return {"pass1": None, "passk": None}
    pass1 = 100 * sum(sum(v) / len(v) for v in pt.values()) / n
    passk = 100 * sum(1 for v in pt.values() if all(v)) / n
    return {"pass1": round(pass1, 1), "passk": round(passk, 1)}


def paired_delta(cand: dict[str, list[float]], base: dict[str, list[float]], *, iters: int = 2000, seed: int = 0) -> dict[str, Any] | None:
    """Mean per-task difference (candidate minus base) with bootstrap intervals over tasks, in points."""
    tasks = sorted(set(cand) & set(base))
    if not tasks:
        return None
    diffs = [sum(cand[t]) / len(cand[t]) - sum(base[t]) / len(base[t]) for t in tasks]
    n = len(diffs)
    mean = sum(diffs) / n
    rng = random.Random(seed)
    boots = sorted(sum(diffs[rng.randrange(n)] for _ in range(n)) / n for _ in range(iters))

    def q(a: float) -> float:
        return boots[min(len(boots) - 1, max(0, int(a * len(boots))))]

    se = (sum((d - mean) ** 2 for d in diffs) / (n - 1)) ** 0.5 / n**0.5 if n > 1 else 0.0
    return {
        "n_tasks": n,
        "pp": round(100 * mean, 1),
        "ci95": [round(100 * q(0.025), 1), round(100 * q(0.975), 1)],
        "ci90": [round(100 * q(0.05), 1), round(100 * q(0.95), 1)],
        "se_pp": round(100 * se, 1),
        # the smallest paired difference this comparison could detect at 80% power, roughly 2.8 SE
        "mde_pp": round(100 * 2.8 * se, 1),
    }


def noninferiority_verdict(delta: dict[str, Any] | None, margin_pp: float) -> str:
    """non_inferior: the lower 90% bound of the paired delta is above -margin; inconclusive: only the
    point estimate is; inferior: not even that."""
    if delta is None:
        return "unknown"
    if delta["ci90"][0] > -margin_pp:
        return "non_inferior"
    if delta["pp"] > -margin_pp:
        return "inconclusive"
    return "inferior"


def superiority_verdict(delta: dict[str, Any] | None) -> str:
    if delta is None:
        return "unknown"
    lo, hi = delta["ci95"]
    if lo > 0:
        return "better"
    if hi < 0:
        return "worse"
    return "undecided"


def holdout_stats(items: list[dict[str, Any]], *, swap_items: list[dict[str, Any]] | None = None, margin_pp: float = 10.0, seed: int = 0) -> dict[str, Any]:
    """Everything the results table needs about one option's held-out replays (any number of trials)."""
    cand = per_task(items, "metrics")
    base = {t: v[:1] for t, v in per_task(items, "baseline_metrics").items()}  # one recorded baseline run per task
    rates = pass_rates(cand)
    k = int(sum(sum(v) for v in cand.values()))
    n = sum(len(v) for v in cand.values())
    d_base = paired_delta(cand, base, seed=seed)
    out: dict[str, Any] = {
        "n_tasks": len(cand),
        "trials": max((len(v) for v in cand.values()), default=0),
        "pass1": rates["pass1"],
        "passk": rates["passk"],
        "success_ci95": list(wilson(k, n)),
        "margin_pp": margin_pp,
        "delta_vs_baseline": d_base,
        "verdict": noninferiority_verdict(d_base, margin_pp),
    }
    if swap_items is not None:
        swap = per_task(swap_items, "metrics")
        d_swap = paired_delta(cand, swap, seed=seed + 1)
        out["swap_pass1"] = pass_rates(swap)["pass1"]
        out["delta_vs_swap"] = d_swap
        out["vs_swap"] = superiority_verdict(d_swap)
    return out


def describe(stats: dict[str, Any] | None) -> str:
    """One line for logs, READMEs and PR bodies."""
    if not stats:
        return ""
    d = stats.get("delta_vs_baseline") or {}
    ci = stats.get("success_ci95") or [None, None]
    parts = [f"{stats.get('n_tasks')} tasks × {stats.get('trials')} trial(s)", f"pass^1 {stats.get('pass1')}%"]
    if (stats.get("trials") or 1) > 1:
        parts.append(f"pass^k {stats.get('passk')}%")
    if ci[0] is not None:
        parts.append(f"95% CI {ci[0]}-{ci[1]}%")
    if d:
        parts.append(f"paired Δ vs baseline {d['pp']:+.1f} pp (90% CI {d['ci90'][0]:+.1f} to {d['ci90'][1]:+.1f})")
    parts.append({"non_inferior": f"non-inferior within {stats.get('margin_pp')} pp", "inconclusive": f"inconclusive at a {stats.get('margin_pp')} pp margin", "inferior": "inferior", "unknown": "no verdict"}.get(stats.get("verdict"), ""))
    ds = stats.get("delta_vs_swap")
    if ds:
        parts.append(f"vs plain swap {ds['pp']:+.1f} pp (95% CI {ds['ci95'][0]:+.1f} to {ds['ci95'][1]:+.1f}): {stats.get('vs_swap')}")
    return "; ".join(p for p in parts if p)
