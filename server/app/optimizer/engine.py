"""The optimization engine: split, analyze, rewrite, replay, score, report. One call per optimization."""

from __future__ import annotations

import random
import threading
import time
import traceback
from typing import Any

from downshift import LLM, Downshift, Harness, NullTransport, default_table
from downshift.providers import on_rate_limit
from research_agent.tools import SearchTools

from ..db import Database, now_iso
from ..settings import Settings
from .analyze import analyze_runs
from .external import ExternalAgent, ExternalAgentError
from .guidance import guidance_text, lookup_guidance
from .judge import auto_checks, ground_truth_verdict, has_ground_truth, judge_pair
from .metrics import aggregate, bar_tolerance_pp, baseline_run_metrics, deltas, meets_bar, objective, replay_metrics
from .replay import replay_many
from .rewrite import propose_harness
from .split import split_runs
from .stats import describe, holdout_stats

TARGETS: dict[str, dict[str, Any]] = {
    "super": {"label": "Nemotron 3 Super", "allowed": ["nemotron-3-super"], "lookup": "NVIDIA Nemotron 3 Super"},
    "nano": {"label": "Nemotron 3 Nano", "allowed": ["nemotron-3-nano"], "lookup": "NVIDIA Nemotron 3 Nano"},
    "mix": {"label": "Per-step mix", "allowed": ["nemotron-3-nano", "nemotron-3-super", "nemotron-3-ultra"], "lookup": "NVIDIA Nemotron 3 Nano"},
}
BASELINE_LABEL = "Baseline · Nemotron 3 Ultra"


def target_spec(target: str, table: Any = None) -> dict[str, Any] | None:
    """The fixed Nemotron targets (super, nano, mix), or `model:<id>` for any single model in the model
    table, so the optimizer can move a baseline from another family to that family's cheaper model
    (for example gpt-oss-120b -> model:gpt-oss-20b)."""
    if target in TARGETS:
        return TARGETS[target]
    if target.startswith("model:"):
        table = table or default_table()
        mid = target.split(":", 1)[1]
        if table.has(mid):
            info = table.get(mid)
            return {"label": info.display, "allowed": [mid], "lookup": f"{info.vendor} {info.display}"}
    return None


def default_config(settings: Settings) -> dict[str, Any]:
    return {
        "targets": list(settings.targets),
        "rounds": settings.opt_rounds,
        "sample_size": settings.opt_sample_size,
        "test_fraction": settings.test_fraction,
        "concurrency": settings.opt_concurrency,
        "max_cost_usd": 6.0,
        "test_limit": None,  # cap on held-out runs evaluated (live demo runs); None = all of them
        "seed": 42,
        # Try the original harness with only the model changed before any rewrite, so a rewrite has to
        # beat the plain swap to be kept (and the report shows what the swap alone does).
        "model_swap_candidate": True,
        # held-out evaluation: replays per task (trials), the non-inferiority margin, and racing: after the
        # rounds, the top candidates and the plain swap are re-scored on race_size fresh optimization tasks
        # x race_trials before one is chosen, so a lucky 20-task score does not pick the harness
        "test_trials": settings.test_trials,
        "noninferiority_pp": settings.noninferiority_pp,
        "race_size": settings.race_size,
        "race_trials": 2,
        "race_candidates": 4,
        "judge_model": settings.judge_model,
        "analysis_model": settings.analysis_model,
        "rewrite_model": settings.rewrite_model,
        "tag": None,
    }


class Engine:
    def __init__(self, db: Database, settings: Settings):
        self.db = db
        self.settings = settings
        self.table = default_table()

    # ---- entry point --------------------------------------------------------------------------
    def run(self, optimization_id: str) -> None:
        opt = self.db.get_optimization(optimization_id)
        if not opt:
            return
        self.db.update_optimization(optimization_id, status="running", started_at=now_iso())
        last_note = {"t": 0.0}

        def rate_limited(message: str, waited: float) -> None:
            # surface provider rate limits in the live log, at most once a minute
            if time.time() - last_note["t"] < 60:
                return
            last_note["t"] = time.time()
            short = message.split("{")[0][:60] + ("usage limit reached" if "usage limit" in message else "too many concurrent requests" if "concurrent" in message else "rate limited")
            self.db.add_event(optimization_id, f"Provider rate limit: {short}. Waiting; the run resumes on its own (waited {int(waited)}s on this call).", level="warn", phase="waiting")

        remove_listener = on_rate_limit(rate_limited)
        try:
            self._run(opt)
        except Exception as e:
            err = f"{type(e).__name__}: {e}"
            self.db.add_event(optimization_id, f"Optimization failed: {err}", level="error", phase="failed", data={"traceback": traceback.format_exc()[-4000:]})
            self.db.update_optimization(optimization_id, status="failed", error=err[:2000], finished_at=now_iso(), progress_json={"phase": "failed", "percent": 100, "detail": err[:300]})
        finally:
            remove_listener()

    # ---- helpers --------------------------------------------------------------------------------
    def _progress(self, oid: str, phase: str, percent: float, detail: str = "", **extra: Any) -> None:
        self.db.update_optimization(oid, progress_json={"phase": phase, "percent": round(min(100.0, max(0.0, percent)), 1), "detail": detail, "updated_at": now_iso(), **extra})

    def _event(self, oid: str, message: str, *, phase: str = "", level: str = "info", data: dict[str, Any] | None = None) -> None:
        self.db.add_event(oid, message, level=level, phase=phase, data=data)

    @staticmethod
    def _analysis_text(analysis: dict[str, Any]) -> str:
        lines = [f"{analysis.get('runs_labelled', 0)} baseline runs labelled."]
        for step, d in (analysis.get("per_step") or {}).items():
            diff = ", ".join(f"{k} {v}%" for k, v in sorted((d.get("difficulty") or {}).items()))
            lines.append(f"- step '{step}' ({d.get('kind')}): difficulty {diff or 'n/a'}; {d.get('needs_strong_model_pct')}% of runs judged to need a strong model. e.g. {'; '.join(d.get('sample_reasons') or [])[:300]}")
        lines.append("Question types: " + ", ".join(f"{k or 'unknown'} {v}" for k, v in (analysis.get("question_types") or {}).items()))
        lines.append("Recommendations: " + " | ".join(analysis.get("recommendations") or []))
        return "\n".join(lines)

    @staticmethod
    def _worst_examples(items: list[dict[str, Any]], n: int = 3) -> list[dict[str, Any]]:
        ranked = sorted(items, key=lambda x: (x["metrics"].get("success"), x["metrics"].get("quality") or 0))
        out = []
        for x in ranked[:n]:
            checks = x["checks"]
            failed = [k for k in ("answer_produced", "has_sources", "sources_from_evidence", "no_errors", "ground_truth") if k in checks and not checks.get(k)]
            events = x["record"].get("events") or []
            last_call = next((e for e in reversed(events) if e.get("type") == "model_call"), None)
            final_message = (((last_call or {}).get("response") or {}).get("content") or "").strip()
            out.append({
                "task_id": x["task_id"], "question": x["question"], "reason": (x["judge"] or {}).get("reason", ""),
                # what the model actually said last: a prose answer where the agent expected a code block is
                # invisible in the extracted answer (empty) but obvious here
                "final_message": final_message[:300],
                "checks": ("failed: " + ", ".join(failed)) if failed else "all passed",
                "answer_excerpt": ((x["record"].get("output") or {}).get("answer") or x["record"].get("error") or "")[:240],
            })
        return out

    @staticmethod
    def _failure_summary(items: list[dict[str, Any]], n: int = 6) -> list[str]:
        """Failed runs grouped by what went wrong (the grader's or judge's reason with numbers blanked), most
        common first, so the rewriter targets the commonest failure class instead of single tasks."""
        import re as _re
        from collections import Counter

        def cls(x: dict[str, Any]) -> str:
            j = x.get("judge") or {}
            if j.get("method") == "ground_truth":
                why = str((j.get("candidate") or {}).get("details") or "")
            else:
                why = str(j.get("reason") or "")
            if x["record"].get("status") != "ok":
                why = "run error: " + str(x["record"].get("error") or "")
            why = _re.sub(r"\d+(\.\d+)?", "N", why)
            why = _re.sub(r"(Response:|near|such (table|column):).*", r"\1 ...", why)
            return why.strip()[:90] or "failed"

        fails = [x for x in items if not x["metrics"].get("success")]
        counts = Counter(cls(x) for x in fails)
        return [f"{c} of {len(items)} runs: {k}" for k, c in counts.most_common(n)]

    def _replayer(self, project_id: str, harness: Harness, sdk: Downshift, tools: SearchTools) -> tuple[Any, str]:
        """How replays run: the built-in research agent in-process, or the project's own agent code
        through its adapter (harness runtime: custom)."""
        if harness.runtime == "research":
            def research(h: Harness, records: list[dict[str, Any]], *, concurrency: int, meta: dict[str, Any], on_each: Any) -> list[dict[str, Any]]:
                return replay_many(sdk, h, records, tools, concurrency=concurrency, meta=meta, on_each=on_each)
            return research, "the built-in research agent"
        try:
            agent = ExternalAgent.for_project(self.db, self.settings, project_id)
        except ExternalAgentError as e:
            raise RuntimeError(str(e)) from e
        return agent.replay_many, f"the agent's own code ({agent.describe()})"

    @staticmethod
    def _model_swap(h: Harness, model: str, target: str) -> Harness:
        data = h.to_dict()
        data["defaults"]["model"] = model
        for step in data["steps"]:
            if step.get("model"):
                step["model"] = model
        data["version"] = f"{h.version}-{target}-swap"
        data["changelog"] = [f"Model swap only: every step on {model}; prompts and settings unchanged."]
        return Harness.from_dict(data)

    @staticmethod
    def _scoring(records: list[dict[str, Any]]) -> str:
        graded = sum(1 for r in records if has_ground_truth(r))
        if graded and graded == len(records):
            return "ground_truth"
        return "mixed" if graded else "judge"

    # ---- the pipeline ---------------------------------------------------------------------------
    def _run(self, opt: dict[str, Any]) -> None:
        oid = opt["id"]
        cfg = {**default_config(self.settings), **(opt.get("config_json") or {})}
        project_id = opt["project_id"]
        project = self.db.get_project(project_id)
        if not project or not project.get("harness_json"):
            raise RuntimeError(f"project '{project_id}' has no recorded harness; record baseline runs first")
        baseline_harness = Harness.from_dict(project["harness_json"])
        runs = [r["record_json"] for r in self.db.latest_runs_per_task(project_id, tag=cfg.get("tag"))]
        # A graded run counts even when its answer was wrong or empty: that is a baseline failure,
        # and leaving it out would flatter the baseline.
        runs = [r for r in runs if r.get("status") == "ok" and ((r.get("output") or {}).get("answer") or has_ground_truth(r))]
        if len(runs) < 4:
            raise RuntimeError(f"need at least 4 successful recorded runs, found {len(runs)}")

        provider = self.settings.provider
        llm = LLM(provider, table=self.table)
        sdk = Downshift(transport=NullTransport(), llm=llm, table=self.table, project=project_id)
        tools = SearchTools()
        replayer, runs_with = self._replayer(project_id, baseline_harness, sdk, tools)
        scoring = self._scoring(runs)
        self._event(oid, f"Replays run {runs_with}. Scoring: " + {"ground_truth": "each task's correct answer, graded by the agent's own grader (no LLM judge).", "mixed": "the correct answer where a task has one, the blind LLM judge otherwise.", "judge": "blind pairwise LLM judge."}[scoring], phase="split")
        spent = {"usd": 0.0}
        spent_lock = threading.Lock()

        def add_cost(x: float | None) -> None:
            with spent_lock:
                spent["usd"] += float(x or 0.0)

        # 1. split -------------------------------------------------------------------------------
        opt_set, test_set = split_runs(runs, float(cfg["test_fraction"]), int(cfg["seed"]))
        self.db.update_optimization(oid, split_json={"opt": [r["task_id"] for r in opt_set], "test": [r["task_id"] for r in test_set], "seed": cfg["seed"], "test_fraction": cfg["test_fraction"]})
        self._event(oid, f"Split {len(runs)} recorded runs into {len(opt_set)} for optimization and {len(test_set)} held out for testing (seed {cfg['seed']}). Results are reported on the held-out set only.", phase="split")
        self._progress(oid, "split", 2, f"{len(opt_set)} optimization / {len(test_set)} test runs")
        rng = random.Random(int(cfg["seed"]))
        sample = opt_set if len(opt_set) <= int(cfg["sample_size"]) else sorted(rng.sample(opt_set, int(cfg["sample_size"])), key=lambda r: r["task_id"])
        test_limit = cfg.get("test_limit")
        if test_limit and len(test_set) > int(test_limit):
            test_set = sorted(rng.sample(test_set, int(test_limit)), key=lambda r: r["task_id"])
            self._event(oid, f"Live demo budget: evaluating on {len(test_set)} of the held-out runs.", phase="split", level="warn")

        # 2. analyze with Nano ---------------------------------------------------------------------
        self._progress(oid, "analyze", 4, f"labelling {len(opt_set)} runs with {cfg['analysis_model']}")
        analysis = analyze_runs(
            llm, cfg["analysis_model"], opt_set,
            cache_get=self.db.get_labels, cache_set=self.db.set_labels, concurrency=int(cfg["concurrency"]),
            on_progress=lambda d, t: self._progress(oid, "analyze", 4 + 8 * d / max(1, t), f"labelled {d}/{t} runs with {cfg['analysis_model']}"),
        )
        add_cost(analysis.get("cost_usd"))
        analysis_text = self._analysis_text(analysis)
        self._event(oid, f"Nemotron 3 Nano labelled {analysis.get('runs_labelled')} runs (${analysis.get('cost_usd', 0):.4f}). " + " ".join(analysis.get("recommendations") or []), phase="analyze", data={"per_step": analysis.get("per_step"), "question_types": analysis.get("question_types")})

        # baseline option row ------------------------------------------------------------------------
        base_models = baseline_harness.models_used()
        base_label = BASELINE_LABEL if base_models == ["nemotron-3-ultra"] else "Baseline · " + " + ".join(self.table.get(m).display if self.table.has(m) else m for m in base_models)
        baseline_option = self.db.create_option(oid, "baseline", base_label, ",".join(base_models), 0, baseline_harness.to_dict(), baseline_harness.to_yaml())
        self.db.update_option(baseline_option["id"], status="done", rationale="The recorded harness, as it runs today.")

        # 3. per target ----------------------------------------------------------------------------
        targets = [t for t in cfg["targets"] if target_spec(t, self.table)] or ["super", "nano", "mix"]
        rounds = max(1, int(cfg["rounds"]))
        per_target = 80.0 / len(targets)
        baseline_test_items: list[dict[str, Any]] = []
        option_results: list[dict[str, Any]] = []

        for ti, target in enumerate(targets):
            spec = target_spec(target, self.table)
            base_pct = 12 + ti * per_target
            option = self.db.create_option(oid, target, spec["label"], ",".join(spec["allowed"]), ti + 1, None, None)
            self.db.update_option(option["id"], status="optimizing")
            self._progress(oid, f"optimize:{target}", base_pct, f"{spec['label']}: looking up prompting guidance")
            search_hits = lookup_guidance(tools, spec["lookup"])
            guidance = guidance_text(spec["allowed"], self.table, search_hits)
            self._event(oid, f"{spec['label']}: starting; {len(search_hits)} guidance results from {tools.provider}.", phase=f"optimize:{target}", data={"guidance_results": search_hits})

            current = baseline_harness
            previous: list[dict[str, Any]] = []
            best: dict[str, Any] | None = None
            rounds_log: list[dict[str, Any]] = []
            if cfg.get("model_swap_candidate", True) and len(spec["allowed"]) == 1:
                swap = self._model_swap(baseline_harness, spec["allowed"][0], target)
                self._progress(oid, f"optimize:{target}", base_pct + per_target * 0.05, f"{spec['label']}: trying the model swap alone (no prompt changes)")
                items = self._replay_and_score(oid, option["id"], swap, sample, "opt", 0, replayer, llm, cfg, add_cost, lambda d, t, label=spec["label"]: self._progress(oid, f"optimize:{target}", base_pct + per_target * 0.05, f"{label}: model swap alone, {d}/{t} runs"))
                agg = aggregate([x["metrics"] for x in items])
                base_agg = aggregate([x["baseline_metrics"] for x in items])
                score = objective(agg, base_agg)
                entry = {"round": 0, "kind": "model_swap", "fingerprint": swap.fingerprint(), "models_used": swap.models_used(), "metrics": agg, "baseline_metrics": base_agg, "objective": score, "changelog": swap.changelog, "rationale": "The original harness with only the model changed.", "worst_examples": self._worst_examples(items), "n": len(items), "harness": swap.to_dict()}
                rounds_log.append(entry)
                self.db.update_option(option["id"], rounds_json=rounds_log)
                self._event(oid, f"{spec['label']} model swap alone (no prompt changes): success {agg.get('success_rate')}% vs baseline {base_agg.get('success_rate')}%, cost ${agg.get('cost_per_run')} vs ${base_agg.get('cost_per_run')} per run (optimization sample, n={len(items)}). Rewrites must beat this.", phase=f"optimize:{target}", data={"metrics": agg, "baseline": base_agg, "objective": score})
                previous.append({"round": "0 (model swap only, prompts unchanged)", "metrics": agg, "baseline_success_rate": base_agg.get("success_rate"), "baseline_quality": base_agg.get("quality"), "baseline_cost": base_agg.get("cost_per_run"), "worst_examples": entry["worst_examples"], "failure_summary": self._failure_summary(items), "changelog": swap.changelog})
                best = {"harness": swap, "score": score, "round": 0, "rationale": "The model swap alone did at least as well as any rewrite on the optimization sample, so the prompts are kept as they are."}
            for round_no in range(1, rounds + 1):
                if spent["usd"] > float(cfg["max_cost_usd"]):
                    self._event(oid, f"Budget cap ${cfg['max_cost_usd']} reached (${spent['usd']:.2f} spent); stopping rounds for {spec['label']}.", phase=f"optimize:{target}", level="warn")
                    break
                r_pct = base_pct + per_target * (0.1 + 0.6 * (round_no - 1) / rounds)
                self._progress(oid, f"optimize:{target}", r_pct, f"{spec['label']}: round {round_no}/{rounds}, {cfg['rewrite_model']} is rewriting the harness")
                try:
                    proposal = propose_harness(llm, cfg["rewrite_model"], current=current, target=target, allowed_models=spec["allowed"], analysis_text=analysis_text, guidance=guidance, previous=previous, round_no=round_no, table=self.table, provider=llm.provider_name, base_version=baseline_harness.version, scoring=scoring)
                except Exception as e:
                    self._event(oid, f"{spec['label']} round {round_no}: rewrite failed ({e}).", phase=f"optimize:{target}", level="warn")
                    continue
                cand: Harness = proposal["harness"]
                add_cost(proposal["usage"].get("cost_usd"))
                self._event(oid, f"{spec['label']} round {round_no}: proposed harness {cand.fingerprint()} using {cand.models_used()}. " + " / ".join(cand.changelog[:4]), phase=f"optimize:{target}", data={"changelog": cand.changelog, "rationale": proposal["rationale"], "fingerprint": cand.fingerprint()})

                def on_round_progress(d: int, t: int, *, target: str = target, r_pct: float = r_pct, label: str = spec["label"], round_no: int = round_no) -> None:
                    self._progress(oid, f"optimize:{target}", r_pct + per_target * 0.5 * d / max(1, t) / rounds, f"{label}: round {round_no}/{rounds}, replayed and judged {d}/{t} runs")

                items = self._replay_and_score(oid, option["id"], cand, sample, "opt", round_no, replayer, llm, cfg, add_cost, on_round_progress)
                agg = aggregate([x["metrics"] for x in items])
                base_agg = aggregate([x["baseline_metrics"] for x in items])
                score = objective(agg, base_agg)
                entry = {"round": round_no, "fingerprint": cand.fingerprint(), "models_used": cand.models_used(), "metrics": agg, "baseline_metrics": base_agg, "objective": score, "changelog": cand.changelog, "rationale": proposal["rationale"], "rewrite_usage": proposal["usage"], "worst_examples": self._worst_examples(items), "n": len(items), "harness": cand.to_dict()}
                rounds_log.append(entry)
                self.db.update_option(option["id"], rounds_json=rounds_log)
                self._event(oid, f"{spec['label']} round {round_no}: success {agg.get('success_rate')}% vs baseline {base_agg.get('success_rate')}%, quality {agg.get('quality')} vs {base_agg.get('quality')}, cost ${agg.get('cost_per_run')} vs ${base_agg.get('cost_per_run')} per run (optimization sample, n={len(items)}).", phase=f"optimize:{target}", data={"metrics": agg, "baseline": base_agg, "objective": score})
                previous.append({"round": round_no, "metrics": agg, "baseline_success_rate": base_agg.get("success_rate"), "baseline_quality": base_agg.get("quality"), "baseline_cost": base_agg.get("cost_per_run"), "worst_examples": entry["worst_examples"], "failure_summary": self._failure_summary(items), "changelog": cand.changelog})
                if best is None or score > best["score"]:
                    best = {"harness": cand, "score": score, "round": round_no, "rationale": proposal["rationale"]}
                current = best["harness"] if best else current

            if best is None:
                self.db.update_option(option["id"], status="failed", rationale="No valid harness could be produced within the budget.")
                self._event(oid, f"{spec['label']}: no candidate produced.", phase=f"optimize:{target}", level="warn")
                continue

            # racing: the top candidates and the plain swap on fresh optimization tasks before choosing ------
            best = self._race(oid, option["id"], spec["label"], target, rounds_log, best, sample, opt_set, replayer, llm, cfg, add_cost, base_pct + per_target * 0.62)
            swap_entry = next((r for r in rounds_log if r.get("kind") == "model_swap" and r.get("harness")), None)

            # held-out evaluation ------------------------------------------------------------------
            # persist the chosen harness first, so an interrupted run can be resumed with `app.cli redo`
            self.db.update_option(option["id"], status="testing", harness_json=best["harness"].to_dict(), harness_yaml=best["harness"].to_yaml(), rationale=best["rationale"], metrics_json={"best_round": best["round"], "objective": best["score"]})
            t_pct = base_pct + per_target * 0.72
            self._progress(oid, f"test:{target}", t_pct, f"{spec['label']}: evaluating round-{best['round']} harness on {len(test_set)} held-out runs")
            def on_test_progress(d: int, t: int, *, target: str = target, t_pct: float = t_pct, label: str = spec["label"]) -> None:
                self._progress(oid, f"test:{target}", t_pct + per_target * 0.26 * d / max(1, t), f"{label}: held-out evaluation {d}/{t}")

            trials = max(1, int(cfg.get("test_trials") or 1))
            items: list[dict[str, Any]] = []
            for trial in range(trials):
                def on_trial_progress(d: int, t: int, *, trial: int = trial) -> None:
                    on_test_progress(trial * len(test_set) + d, trials * len(test_set))
                items.extend(self._replay_and_score(oid, option["id"], best["harness"], test_set, "test", trial, replayer, llm, cfg, add_cost, on_trial_progress))
            agg = aggregate([x["metrics"] for x in items])
            base_agg = aggregate([x["baseline_metrics"] for x in items])
            baseline_test_items.extend(x["baseline_metrics"] for x in items if x.get("trial", 0) == 0)
            # the plain swap on the same held-out tasks, so "the rewrite beats the swap" is a paired test too
            swap_items: list[dict[str, Any]] | None = None
            if swap_entry is not None and best["round"] != 0:
                swap_h = Harness.from_dict(swap_entry["harness"])
                swap_items = []
                for trial in range(trials):
                    swap_items.extend(self._replay_and_score(oid, option["id"], swap_h, test_set, "test_swap", trial, replayer, llm, cfg, add_cost, lambda d, t: None))
            stats = holdout_stats(items, swap_items=swap_items, margin_pp=float(cfg.get("noninferiority_pp") or 10.0), seed=int(cfg["seed"]))
            if swap_items is not None:
                stats["swap_metrics"] = aggregate([x["metrics"] for x in swap_items])
            self._event(oid, f"{spec['label']} held-out statistics: {describe(stats)}", phase=f"test:{target}", data={"stats": stats})
            metrics = {"test": agg, "baseline_on_test": base_agg, "deltas": deltas(agg, base_agg), "meets_bar": stats["verdict"] == "non_inferior", "verdict": stats["verdict"], "stats": stats, "best_round": best["round"], "objective": best["score"], "n_test": len(test_set), "trials": trials}
            self.db.update_option(option["id"], status="done", harness_json=best["harness"].to_dict(), harness_yaml=best["harness"].to_yaml(), metrics_json=metrics, rationale=best["rationale"])
            option_results.append({"key": target, "label": spec["label"], "metrics": metrics, "models_used": best["harness"].models_used(), "option_id": option["id"]})
            self._event(oid, f"{spec['label']} on the held-out set (n={len(items)}): success {agg.get('success_rate')}% (baseline {base_agg.get('success_rate')}%), quality {agg.get('quality')} ({base_agg.get('quality')}), cost ${agg.get('cost_per_run')} ({base_agg.get('cost_per_run')}) per run, latency {agg.get('latency_ms')} ms ({base_agg.get('latency_ms')}).", phase=f"test:{target}", data={"metrics": metrics})

        # 4. baseline metrics and summary ---------------------------------------------------------------
        # The baseline is scored inside every pairwise judge call, so pool those scores for one
        # baseline estimate and measure every option against the same number.
        baseline_agg = aggregate(baseline_test_items)
        if baseline_agg.get("n"):
            baseline_agg["n"] = len({(x.get("task_id")) for x in baseline_test_items} - {None}) or len(test_set)
            baseline_agg["n_comparisons"] = len(baseline_test_items)
        self.db.update_option(baseline_option["id"], metrics_json={"test": baseline_agg, "baseline_on_test": baseline_agg, "deltas": deltas(baseline_agg, baseline_agg), "meets_bar": True, "n_test": len(test_set)})
        for o in option_results:
            t_agg = o["metrics"]["test"]
            o["metrics"]["baseline_in_comparisons"] = o["metrics"]["baseline_on_test"]
            o["metrics"]["baseline_on_test"] = baseline_agg
            o["metrics"]["deltas"] = deltas(t_agg, baseline_agg)
            o["metrics"]["meets_bar"] = o["metrics"].get("verdict") == "non_inferior" if o["metrics"].get("stats") else meets_bar(t_agg, baseline_agg)
            self.db.update_option(o["option_id"], metrics_json=o["metrics"])
        summary = self._summary(baseline_agg, option_results, len(opt_set), len(test_set), spent["usd"], cfg, tools.provider, llm.provider_name, analysis, scoring=scoring, runtime=baseline_harness.runtime)
        self.db.update_optimization(oid, status="done", finished_at=now_iso(), summary_json=summary)
        self._progress(oid, "done", 100, summary.get("headline", {}).get("text", "done"))
        self._event(oid, "Done. " + summary.get("headline", {}).get("text", ""), phase="done", data={"spent_usd": round(spent["usd"], 4)})

    def _race(self, oid: str, option_id: str, label: str, target: str, rounds_log: list[dict[str, Any]], best: dict[str, Any], sample: list[dict[str, Any]], opt_set: list[dict[str, Any]], replayer: Any, llm: LLM, cfg: dict[str, Any], add_cost: Any, pct: float) -> dict[str, Any]:
        """Re-score the two best candidates and the plain swap on optimization tasks none of them has seen
        (race_size of them, race_trials each) and pick by success, then cost. A rewrite is chosen over the
        swap only if it passes more task-trials there; ties go to the swap (simpler, and the rewrite has
        not shown anything). Nothing here touches the held-out set."""
        race_size = int(cfg.get("race_size") or 0)
        trials = max(1, int(cfg.get("race_trials") or 1))
        with_harness = [r for r in rounds_log if r.get("harness")]
        if race_size <= 0 or len(with_harness) < 2:
            return best
        seen = {r["task_id"] for r in sample}
        pool = [r for r in opt_set if r["task_id"] not in seen]
        if len(pool) < 4:
            return best
        rng = random.Random(int(cfg["seed"]) + 7)
        pool = sorted(rng.sample(pool, min(race_size, len(pool))), key=lambda r: r["task_id"])
        # every candidate races (three rounds give at most four): ranking by the small-sample objective first
        # dropped the minimal rewrite on a cost tie-break in the Phase 1 run
        ranked = sorted(with_harness, key=lambda r: r.get("objective", 0), reverse=True)
        contenders = ranked[: max(2, int(cfg.get("race_candidates") or 4))]
        swap = next((r for r in with_harness if r.get("kind") == "model_swap"), None)
        if swap is not None and swap not in contenders:
            contenders.append(swap)
        self._event(oid, f"{label}: racing {len(contenders)} candidates (rounds {[c['round'] for c in contenders]}) on {len(pool)} unseen optimization tasks x {trials} trials.", phase=f"optimize:{target}")
        results = []
        for i, c in enumerate(contenders):
            h = Harness.from_dict(c["harness"])
            items: list[dict[str, Any]] = []
            for trial in range(trials):
                items.extend(self._replay_and_score(oid, option_id, h, pool, "race", 100 * (c["round"] + 1) + trial, replayer, llm, cfg, add_cost, lambda d, t, i=i: self._progress(oid, f"optimize:{target}", pct, f"{label}: racing candidate {i + 1}/{len(contenders)}, {d}/{t} replays")))
            agg = aggregate([x["metrics"] for x in items])
            wins = sum(1 for x in items if x["metrics"].get("success"))
            results.append({"round": c["round"], "kind": c.get("kind", "rewrite"), "wins": wins, "n": len(items), "metrics": agg, "harness": h, "entry": c})
            c["race"] = {"wins": wins, "n": len(items), "success_rate": agg.get("success_rate"), "cost_per_run": agg.get("cost_per_run")}
            self._event(oid, f"{label} race: round-{c['round']} harness passed {wins}/{len(items)} task-trials at ${agg.get('cost_per_run')} per run.", phase=f"optimize:{target}", data={"race": c["race"]})
        self.db.update_option(option_id, rounds_json=rounds_log)
        swap_res = next((r for r in results if r["kind"] == "model_swap"), None)
        rewrites = [r for r in results if r["kind"] != "model_swap"]
        chosen = max(results, key=lambda r: (r["wins"], -(r["metrics"].get("cost_per_run") or 0.0)))
        if swap_res is not None and (not rewrites or max(r["wins"] for r in rewrites) <= swap_res["wins"]):
            chosen = swap_res
        reason = f"chosen by the race on {len(pool)} unseen optimization tasks x {trials} trials: {chosen['wins']}/{chosen['n']} task-trials" + (f" (plain swap {swap_res['wins']}/{swap_res['n']})" if swap_res is not None and chosen is not swap_res else "")
        self._event(oid, f"{label}: {reason}; keeping the round-{chosen['round']} harness.", phase=f"optimize:{target}")
        entry = chosen["entry"]
        return {"harness": chosen["harness"], "score": entry.get("objective", best["score"]), "round": chosen["round"], "rationale": (entry.get("rationale") or best["rationale"] or "") + f" [{reason}]"}

    def verify(self, optimization_id: str, *, trials: int = 2) -> dict[str, Any]:
        """Fresh runs, after the fact: every finished option's chosen harness, the plain swap and the
        baseline harness again on the held-out tasks, `trials` times each with new model calls, scored
        the same way and stored under split 'verify'. Returns Downshift's replay numbers next to them."""
        opt = self.db.get_optimization(optimization_id)
        if not opt:
            raise RuntimeError("optimization not found")
        cfg = {**default_config(self.settings), **(opt.get("config_json") or {})}
        project = self.db.get_project(opt["project_id"])
        baseline_harness = Harness.from_dict(project["harness_json"])
        split = opt.get("split_json") or {}
        test_ids = set(split.get("test") or [])
        runs = [r["record_json"] for r in self.db.latest_runs_per_task(opt["project_id"], tag=cfg.get("tag"))]
        test_set = sorted([r for r in runs if r["task_id"] in test_ids], key=lambda r: r["task_id"])
        if not test_set:
            raise RuntimeError("no held-out runs found for this optimization")
        llm = LLM(self.settings.provider, table=self.table)
        sdk = Downshift(transport=NullTransport(), llm=llm, table=self.table, project=opt["project_id"])
        replayer, _ = self._replayer(opt["project_id"], baseline_harness, sdk, SearchTools())
        spent = {"usd": 0.0}

        def add_cost(x: float | None) -> None:
            spent["usd"] += float(x or 0.0)

        arms: list[tuple[str, str, Harness, dict[str, Any] | None]] = [("baseline", "baseline harness (fresh)", baseline_harness, None)]
        for o in self.db.list_options(optimization_id):
            if o["key"] == "baseline" or not o.get("harness_json"):
                continue
            arms.append((o["key"], f"{o['label']} (chosen harness)", Harness.from_dict(o["harness_json"]), o))
            swap = next((r for r in (o.get("rounds_json") or []) if r.get("kind") == "model_swap" and r.get("harness")), None)
            if swap is not None and (o.get("metrics_json") or {}).get("best_round") != 0:
                arms.append((f"{o['key']}-swap", f"{o['label']} (plain swap)", Harness.from_dict(swap["harness"]), None))
        out: dict[str, Any] = {"optimization_id": optimization_id, "n_tasks": len(test_set), "trials": trials, "arms": []}
        baseline_option = self.db.get_option_by_key(optimization_id, "baseline")
        for key, label, h, option in arms:
            # arms without their own option row (the baseline, the plain swaps) are stored under the baseline
            # option; the round number tells them apart: 1000+ baseline and chosen harnesses, 2000+ swaps
            option_id = (option or baseline_option or {}).get("id")
            base_round = 2000 if key.endswith("-swap") else 1000
            items: list[dict[str, Any]] = []
            for trial in range(trials):
                items.extend(self._replay_and_score(optimization_id, option_id, h, test_set, "verify", base_round + trial, replayer, llm, cfg, add_cost, lambda d, t: None))
            stats = holdout_stats(items, margin_pp=float(cfg.get("noninferiority_pp") or 10.0), seed=int(cfg["seed"]))
            per_trial = [sum(1 for x in items if x["trial"] == base_round + t and x["metrics"].get("success")) for t in range(trials)]
            claimed = (((option or {}).get("metrics_json") or {}).get("test") or {}).get("success_rate") if option else None
            row = {"key": key, "label": label, "passes_per_trial": per_trial, "fresh": stats, "claimed_success_rate": claimed, "cost_per_run": aggregate([x["metrics"] for x in items]).get("cost_per_run")}
            out["arms"].append(row)
            self._event(optimization_id, f"verify: {label}: {per_trial} of {len(test_set)} per trial; {describe(stats)}" + (f"; Downshift's replay said {claimed}%" if claimed is not None else ""), phase="verify", data=row)
            if option:
                m = dict(option.get("metrics_json") or {})
                m["verify"] = row
                self.db.update_option(option["id"], metrics_json=m)
        out["spent_usd"] = round(spent["usd"], 4)
        return out

    def redo_test_replays(self, optimization_id: str, option_key: str, *, only_failed: bool = True) -> dict[str, Any]:
        """Replay (again) the held-out tasks of one option whose replay is missing, errored or unjudged,
        for example after a provider outage, then rebuild the summary. Successful replays are kept."""
        opt = self.db.get_optimization(optimization_id)
        if not opt:
            raise RuntimeError("optimization not found")
        option = self.db.get_option_by_key(optimization_id, option_key)
        if not option:
            raise RuntimeError(f"option '{option_key}' not found")
        if not option.get("harness_json"):
            rounds = [r for r in (option.get("rounds_json") or []) if r.get("harness")]
            if not rounds:
                raise RuntimeError(f"option '{option_key}' has no stored harness and no completed round to recover one from")
            best = max(rounds, key=lambda r: r.get("objective", 0))
            recovered = Harness.from_dict(best["harness"])
            self.db.update_option(option["id"], harness_json=recovered.to_dict(), harness_yaml=recovered.to_yaml(), rationale=best.get("rationale"), metrics_json={"best_round": best.get("round"), "objective": best.get("objective")})
            option = self.db.get_option(option["id"]) or option
            self._event(optimization_id, f"Recovered the round-{best.get('round')} harness for {option['label']} from the stored rounds.", phase=f"redo:{option_key}")
        cfg = {**default_config(self.settings), **(opt.get("config_json") or {})}
        harness = Harness.from_dict(option["harness_json"])
        test_ids = (opt.get("split_json") or {}).get("test") or []
        runs = {r["task_id"]: r["record_json"] for r in self.db.latest_runs_per_task(opt["project_id"], tag=cfg.get("tag"))}
        todo: list[str] = []
        for tid in test_ids:
            rep = self.db.find_replay(option["id"], tid, "test")
            judge = (rep or {}).get("judge_json") or {}
            failed = rep is None or rep.get("status") != "ok" or not judge or "error" in judge
            if (failed or not only_failed) and tid in runs:
                todo.append(tid)
        if not todo:
            return {"redone": 0, "summary": opt.get("summary_json")}
        self.db.delete_replays(option["id"], "test", todo)
        llm = LLM(self.settings.provider, table=self.table)
        sdk = Downshift(transport=NullTransport(), llm=llm, table=self.table, project=opt["project_id"])
        tools = SearchTools()
        replayer, _ = self._replayer(opt["project_id"], harness, sdk, tools)
        spent = {"usd": 0.0}
        lock = threading.Lock()

        def add_cost(x: float | None) -> None:
            with lock:
                spent["usd"] += float(x or 0.0)

        self._event(optimization_id, f"Redoing {len(todo)} held-out replays for {option['label']} ({', '.join(todo)}).", phase=f"redo:{option_key}")
        self._replay_and_score(optimization_id, option["id"], harness, [runs[t] for t in todo], "test", 0, replayer, llm, cfg, add_cost, lambda d, n: self._progress(optimization_id, f"redo:{option_key}", 90 + 9 * d / max(1, n), f"{option['label']}: redoing held-out replays {d}/{n}"))
        metrics = dict(option.get("metrics_json") or {})
        if "best_round" not in metrics and option.get("rounds_json"):
            best = max(option["rounds_json"], key=lambda r: r.get("objective", 0))
            metrics.update({"best_round": best.get("round"), "objective": best.get("objective")})
        self.db.update_option(option["id"], status="done", metrics_json=metrics)
        if opt.get("status") != "done":
            self.db.update_optimization(optimization_id, status="done", finished_at=now_iso(), error=None)
        summary = self.resummarize(optimization_id, extra_spent_usd=spent["usd"])
        self._progress(optimization_id, "done", 100, summary.get("headline", {}).get("text", "done"))
        return {"redone": len(todo), "summary": summary}

    def resummarize(self, optimization_id: str, *, extra_spent_usd: float = 0.0) -> dict[str, Any]:
        """Recompute automatic checks, per-run metrics, option aggregates and the summary from the stored
        replays. Judge verdicts are kept as they are. Use after a fix to the checks or the bar."""
        opt = self.db.get_optimization(optimization_id)
        if not opt or opt.get("status") != "done":
            raise RuntimeError("only completed optimizations can be resummarized")
        cfg = {**default_config(self.settings), **(opt.get("config_json") or {})}
        split = opt.get("split_json") or {}
        options = self.db.list_options(optimization_id)
        baseline_option = next((o for o in options if o["key"] == "baseline"), None)
        if baseline_option is None:
            raise RuntimeError("no baseline option stored")
        baseline_runs = {r["task_id"]: r["record_json"] for r in self.db.latest_runs_per_task(opt["project_id"], tag=cfg.get("tag"))}
        option_results: list[dict[str, Any]] = []
        baseline_test_items: list[dict[str, Any]] = []
        judge_methods: set[str] = set()
        for o in options:
            if o["key"] == "baseline" or o["status"] != "done":
                continue
            items = []
            for rep in self.db.list_replays(o["id"], split="test"):
                base_rec = self.db.get_run(rep["baseline_run_id"]) if rep.get("baseline_run_id") else None
                base_rec = (base_rec or {}).get("record_json") or baseline_runs.get(rep["task_id"])
                if not base_rec:
                    continue
                rec = rep["record_json"]
                judge = rep.get("judge_json") or {}
                judge_methods.add(judge.get("method") or "judge")
                checks, base_checks = auto_checks(rec), auto_checks(base_rec)
                m, bm = replay_metrics(rec, judge, checks), baseline_run_metrics(base_rec, judge, base_checks)
                bm["task_id"] = rep["task_id"]
                self.db.update_replay(rep["id"], checks_json={"candidate": checks, "baseline": base_checks}, metrics_json={"candidate": m, "baseline": bm})
                items.append({"metrics": m, "baseline_metrics": bm})
            if not items:
                continue
            agg = aggregate([x["metrics"] for x in items])
            base_agg = aggregate([x["baseline_metrics"] for x in items])
            baseline_test_items.extend(x["baseline_metrics"] for x in items)
            metrics = dict(o.get("metrics_json") or {})
            metrics.update({"test": agg, "baseline_in_comparisons": base_agg, "n_test": len(items)})
            option_results.append({"key": o["key"], "label": o["label"], "metrics": metrics, "models_used": Harness.from_dict(o["harness_json"]).models_used() if o.get("harness_json") else [], "option_id": o["id"]})
        baseline_agg = aggregate(baseline_test_items)
        if baseline_agg.get("n"):
            baseline_agg["n"] = len({x.get("task_id") for x in baseline_test_items} - {None}) or len(split.get("test") or [])
            baseline_agg["n_comparisons"] = len(baseline_test_items)
        self.db.update_option(baseline_option["id"], metrics_json={"test": baseline_agg, "baseline_on_test": baseline_agg, "deltas": deltas(baseline_agg, baseline_agg), "meets_bar": True, "n_test": len(split.get("test") or [])})
        for o in option_results:
            t_agg = o["metrics"]["test"]
            o["metrics"]["baseline_on_test"] = baseline_agg
            o["metrics"]["deltas"] = deltas(t_agg, baseline_agg)
            o["metrics"]["meets_bar"] = o["metrics"].get("verdict") == "non_inferior" if o["metrics"].get("stats") else meets_bar(t_agg, baseline_agg)
            self.db.update_option(o["option_id"], metrics_json=o["metrics"])
        old = opt.get("summary_json") or {}
        analysis = {"recommendations": (old.get("analysis") or {}).get("recommendations"), "per_step": (old.get("analysis") or {}).get("per_step")}
        scoring = "ground_truth" if judge_methods == {"ground_truth"} else ("mixed" if "ground_truth" in judge_methods else "judge")
        project = self.db.get_project(opt["project_id"]) or {}
        runtime = (project.get("harness_json") or {}).get("runtime") or "research"
        summary = self._summary(baseline_agg, option_results, len(split.get("opt") or []), len(split.get("test") or []), float(old.get("spent_usd") or 0.0) + float(extra_spent_usd or 0.0), cfg, old.get("search_provider") or SearchTools().provider, old.get("provider") or (self.settings.provider or "ollama"), analysis, scoring=scoring, runtime=runtime)
        self.db.update_optimization(optimization_id, summary_json=summary)
        self.db.add_event(optimization_id, "Recomputed checks, metrics and summary from the stored replays (judge verdicts unchanged). " + summary["headline"]["text"], phase="resummarize")
        return summary

    def _replay_and_score(self, oid: str, option_id: str, harness: Harness, records: list[dict[str, Any]], split: str, round_no: int, replayer: Any, llm: LLM, cfg: dict[str, Any], add_cost: Any, on_progress: Any) -> list[dict[str, Any]]:
        """Replay each record with the harness, run checks and score it (ground truth when the baseline
        run was graded against the task's correct answer, the blind judge otherwise); store everything."""
        done = {"n": 0}
        lock = threading.Lock()
        out: list[dict[str, Any]] = []
        judge_model = cfg["judge_model"]
        seed = int(cfg["seed"])

        def score_one(base_rec: dict[str, Any], rec: dict[str, Any]) -> None:
            checks = auto_checks(rec)
            base_checks = auto_checks(base_rec)
            if has_ground_truth(base_rec):  # the task has a correct answer: no judge needed
                judge = ground_truth_verdict(base_rec, rec)
            else:
                try:
                    judge = judge_pair(llm, judge_model, base_rec.get("input", ""), (base_rec.get("output") or {}).get("answer", ""), (rec.get("output") or {}).get("answer", ""), rng=random.Random(f"{seed}:{option_id}:{split}:{round_no}:{base_rec['task_id']}"))
                    add_cost(judge.get("cost_usd"))
                except Exception as e:
                    judge = {"error": f"{type(e).__name__}: {e}"[:300], "preferred": None, "candidate": None, "baseline": None}
            m = replay_metrics(rec, judge, checks)
            bm = baseline_run_metrics(base_rec, judge, base_checks)
            bm["task_id"] = base_rec["task_id"]
            add_cost(m.get("cost_usd"))
            self.db.insert_replay({"optimization_id": oid, "option_id": option_id, "task_id": base_rec["task_id"], "baseline_run_id": base_rec["id"], "split": split, "round": round_no, "status": rec.get("status"), "record_json": rec, "judge_json": judge, "checks_json": {"candidate": checks, "baseline": base_checks}, "metrics_json": {"candidate": m, "baseline": bm}})
            with lock:
                out.append({"task_id": base_rec["task_id"], "question": base_rec.get("input", ""), "record": rec, "judge": judge, "checks": checks, "metrics": m, "baseline_metrics": bm, "trial": round_no})
                done["n"] += 1
                n = done["n"]
            on_progress(n, len(records))

        replayer(harness, records, concurrency=int(cfg["concurrency"]), meta={"optimization_id": oid, "option_id": option_id, "split": split, "round": round_no}, on_each=score_one)
        out.sort(key=lambda x: x["task_id"])
        return out

    @staticmethod
    def _n(x: Any, signed: bool = False) -> str:
        if x is None:
            return "n/a"
        return f"{float(x):+.0f}" if signed else f"{float(x):.0f}"

    @staticmethod
    def _summary(baseline: dict[str, Any], options: list[dict[str, Any]], n_opt: int, n_test: int, spent: float, cfg: dict[str, Any], search_provider: str, provider: str, analysis: dict[str, Any], scoring: str = "judge", runtime: str = "research") -> dict[str, Any]:
        rows = []
        for o in options:
            t = o["metrics"]["test"]
            rows.append({"key": o["key"], "label": o["label"], "models_used": o["models_used"], "metrics": t, "deltas": o["metrics"]["deltas"], "meets_bar": o["metrics"]["meets_bar"], "verdict": o["metrics"].get("verdict"), "stats": o["metrics"].get("stats"), "option_id": o["option_id"]})
        qualifying = [r for r in rows if r["meets_bar"] and r["metrics"].get("cost_per_run") is not None]
        recommended = min(qualifying, key=lambda r: r["metrics"]["cost_per_run"]) if qualifying else None
        if recommended:
            d = recommended["deltas"]
            text = f"Task success {Engine._n(baseline.get('success_rate'))}% → {Engine._n(recommended['metrics'].get('success_rate'))}%, cost {'down' if (d.get('cost_pct') or 0) <= 0 else 'up'} {abs(d.get('cost_pct') or 0):.0f}%"
            verdict = f"{recommended['label']} keeps quality within the bar at {abs(d.get('cost_pct') or 0):.0f}% {'lower' if (d.get('cost_pct') or 0) <= 0 else 'higher'} cost per run."
        else:
            best = max(rows, key=lambda r: (r["metrics"].get("quality") or 0)) if rows else None
            text = "No cheaper option met the quality bar" if best is None else f"No cheaper option met the bar: best was {best['label']} at {Engine._n(best['metrics'].get('success_rate'))}% success vs {Engine._n(baseline.get('success_rate'))}%"
            verdict = "Keep the baseline for now; see the per-option notes for what fell short."
        notes = []
        for r in rows:
            d = r["deltas"]
            n = Engine._n
            if r["meets_bar"]:
                notes.append(f"{r['label']}: within the bar ({n(d.get('success_rate_pp'), True)} pp success, {n(d.get('quality_pts'), True)} quality, {n(d.get('cost_pct'), True)}% cost).")
            else:
                notes.append(f"{r['label']}: falls short ({n(d.get('success_rate_pp'), True)} pp success, {n(d.get('quality_pts'), True)} quality at {n(d.get('cost_pct'), True)}% cost).")
            if r.get("stats"):
                notes.append(f"{r['label']} statistics: {describe(r['stats'])}.")
        return {
            "headline": {"text": text, "verdict": verdict, "recommended": recommended["key"] if recommended else None},
            "baseline": baseline,
            "options": rows,
            "notes": notes,
            "split": {"optimization": n_opt, "test": n_test, "test_fraction": cfg.get("test_fraction"), "note": "All numbers above come from the held-out test set, which the optimizer never saw."},
            "bar": {"success_tol_pp": bar_tolerance_pp(n_test or baseline.get("n")), "quality_tol_pts": 5.0, "margin_pp": cfg.get("noninferiority_pp", 10.0), "trials": cfg.get("test_trials", 1),
                    "note": f"Within the bar: non-inferior to the baseline on the held-out tasks, paired per task: the lower 90% bound of the success difference stays above -{cfg.get('noninferiority_pp', 10.0)} pp. 'Inconclusive' means the point estimate is above the margin but the interval is not."},
            "spent_usd": round(spent, 4),
            "budget": {"rounds": cfg.get("rounds"), "sample_size": cfg.get("sample_size"), "max_cost_usd": cfg.get("max_cost_usd")},
            "judge": {
                "ground_truth": {"model": None, "method": "ground truth: each task's correct answer, graded by the agent's own grader; quality = mean grader score (0-100). No LLM judge."},
                "mixed": {"model": cfg.get("judge_model"), "method": "ground truth where the task has a correct answer, otherwise blind pairwise LLM judge (correct / complete / supported, 0-5 each)"},
                "judge": {"model": cfg.get("judge_model"), "method": "blind pairwise, random order, rubric: correct / complete / supported (0-5 each)"},
            }[scoring],
            "scoring": scoring,
            "runtime": runtime,
            "analysis": {"model": cfg.get("analysis_model"), "recommendations": analysis.get("recommendations"), "per_step": analysis.get("per_step")},
            "provider": provider,
            "search_provider": search_provider,
            "pricing_note": "Costs use Nebius Token Factory list prices applied to the recorded token counts.",
        }
