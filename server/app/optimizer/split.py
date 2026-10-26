"""Deterministic split of recorded runs into an optimization set and a held-out test set."""

from __future__ import annotations

import random
from typing import Any


def split_runs(runs: list[dict[str, Any]], test_fraction: float = 0.4, seed: int = 42) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """Returns (optimization_set, test_set). Same input and seed -> same split, every time."""
    ordered = sorted(runs, key=lambda r: r["task_id"])
    rng = random.Random(seed)
    rng.shuffle(ordered)
    n_test = max(1, round(len(ordered) * test_fraction)) if len(ordered) > 1 else 0
    test = sorted(ordered[:n_test], key=lambda r: r["task_id"])
    opt = sorted(ordered[n_test:], key=lambda r: r["task_id"])
    return opt, test
