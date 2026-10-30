import sys
from pathlib import Path

SERVER = Path(__file__).resolve().parents[1]
if str(SERVER) not in sys.path:
    sys.path.insert(0, str(SERVER))

from app.optimizer.stats import describe, holdout_stats, noninferiority_verdict, paired_delta, pass_rates, per_task, superiority_verdict, wilson  # noqa: E402


def _items(cand: dict[str, list[bool]], base: dict[str, bool]):
    out = []
    for t, trials in cand.items():
        for ok in trials:
            out.append({"task_id": t, "metrics": {"judged": True, "success": ok}, "baseline_metrics": {"judged": True, "success": base[t]}})
    return out


def test_wilson_is_wide_on_16_tasks():
    lo, hi = wilson(11, 16)
    assert lo < 50 and hi > 85  # about 44-86: one replay of 16 tasks says little


def test_pass_rates_and_per_task():
    pt = per_task(_items({"a": [True, False], "b": [True, True]}, {"a": True, "b": True}))
    assert pt == {"a": [1.0, 0.0], "b": [1.0, 1.0]}
    assert pass_rates(pt) == {"pass1": 75.0, "passk": 50.0}


def test_paired_delta_and_verdicts():
    # 20 tasks: candidate equals baseline everywhere -> delta 0, non-inferior at a 10 pp margin? only if the
    # interval is tight enough; identical outcomes give a zero-width interval
    cand = {f"t{i}": [True] for i in range(20)}
    base = {f"t{i}": [True] for i in range(20)}
    d = paired_delta(cand, base)
    assert d["pp"] == 0.0 and d["ci90"] == [0.0, 0.0]
    assert noninferiority_verdict(d, 10.0) == "non_inferior"
    # candidate loses 4 of 16 tasks the baseline passed: point estimate -25 -> inferior
    cand = {f"t{i}": [i >= 4] for i in range(16)}
    base = {f"t{i}": [True] for i in range(16)}
    d = paired_delta(cand, base)
    assert d["pp"] == -25.0 and noninferiority_verdict(d, 10.0) == "inferior"
    # candidate wins 6 of 16 the swap lost, loses none -> better
    cand = {f"t{i}": [True] for i in range(16)}
    swap = {f"t{i}": [i >= 6] for i in range(16)}
    d = paired_delta(cand, swap)
    assert d["pp"] == 37.5 and superiority_verdict(d) == "better"
    # mixed wins and losses on few tasks -> undecided / inconclusive
    cand = {f"t{i}": [i % 2 == 0] for i in range(8)}
    swap = {f"t{i}": [i % 2 == 1] for i in range(8)}
    assert superiority_verdict(paired_delta(cand, swap)) == "undecided"


def test_holdout_stats_end_to_end():
    cand = {f"t{i}": [True, i % 4 != 0] for i in range(16)}
    base = {f"t{i}": i % 5 != 0 for i in range(16)}
    swap_items = _items({f"t{i}": [i % 2 == 0] for i in range(16)}, base)
    s = holdout_stats(_items(cand, base), swap_items=swap_items, margin_pp=10.0)
    assert s["n_tasks"] == 16 and s["trials"] == 2
    assert s["pass1"] == 87.5 and s["passk"] == 75.0
    assert s["verdict"] in {"non_inferior", "inconclusive", "inferior"}
    assert s["vs_swap"] in {"better", "undecided", "worse"}
    text = describe(s)
    assert "16 tasks × 2 trial(s)" in text and "pass^k" in text and "vs plain swap" in text
