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
from .guidance import guidance_text, lookup_guidance
from .judge import auto_checks, judge_pair
from .metrics import aggregate, bar_tolerance_pp, baseline_run_metrics, deltas, meets_bar, objective, replay_metrics
from .replay import replay_many
from .rewrite import propose_harness
from .split import split_runs

TARGETS: dict[str, dict[str, Any]] = {
    "super": {"label": "Nemotron 3 Super", "allowed": ["nemotron-3-super"], "lookup": "NVIDIA Nemotron 3 Super"},
    "nano": {"label": "Nemotron 3 Nano", "allowed": ["nemotron-3-nano"], "lookup": "NVIDIA Nemotron 3 Nano"},
    "mix": {"label": "Per-step mix", "allowed": ["nemotron-3-nano", "nemotron-3-super", "nemotron-3-ultra"], "lookup": "NVIDIA Nemotron 3 Nano"},
}
BASELINE_LABEL = "Baseline · Nemotron 3 Ultra"


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
            failed = [k for k in ("answer_produced", "has_sources", "sources_from_evidence", "no_errors") if not checks.get(k)]
            out.append({
                "task_id": x["task_id"], "question": x["question"], "reason": (x["judge"] or {}).get("reason", ""),
                "checks": ("failed: " + ", ".join(failed)) if failed else "all passed",
                "answer_excerpt": ((x["record"].get("output") or {}).get("answer") or x["record"].get("error") or "")[:240],
            })
        return out

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
        runs = [r for r in runs if r.get("status") == "ok" and (r.get("output") or {}).get("answer")]
        if len(runs) < 4:
            raise RuntimeError(f"need at least 4 successful recorded runs, found {len(runs)}")

        provider = self.settings.provider
        llm = LLM(provider, table=self.table)
        sdk = Downshift(transport=NullTransport(), llm=llm, table=self.table, project=project_id)
        tools = SearchTools()
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
        baseline_option = self.db.create_option(oid, "baseline", BASELINE_LABEL, "nemotron-3-ultra", 0, baseline_harness.to_dict(), baseline_harness.to_yaml())
        self.db.update_option(baseline_option["id"], status="done", rationale="The recorded harness, as it runs today.")

        # 3. per target ----------------------------------------------------------------------------
        targets = [t for t in cfg["targets"] if t in TARGETS] or ["super", "nano", "mix"]
        rounds = max(1, int(cfg["rounds"]))
        per_target = 80.0 / len(targets)
        baseline_test_items: list[dict[str, Any]] = []
        option_results: list[dict[str, Any]] = []

        for ti, target in enumerate(targets):
            spec = TARGETS[target]
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
            for round_no in range(1, rounds + 1):
                if spent["usd"] > float(cfg["max_cost_usd"]):
                    self._event(oid, f"Budget cap ${cfg['max_cost_usd']} reached (${spent['usd']:.2f} spent); stopping rounds for {spec['label']}.", phase=f"optimize:{target}", level="warn")
                    break
                r_pct = base_pct + per_target * (0.1 + 0.6 * (round_no - 1) / rounds)
                self._progress(oid, f"optimize:{target}", r_pct, f"{spec['label']}: round {round_no}/{rounds}, {cfg['rewrite_model']} is rewriting the harness")
                try:
                    proposal = propose_harness(llm, cfg["rewrite_model"], current=current, target=target, allowed_models=spec["allowed"], analysis_text=analysis_text, guidance=guidance, previous=previous, round_no=round_no, table=self.table, provider=llm.provider_name, base_version=baseline_harness.version)
                except Exception as e:
                    self._event(oid, f"{spec['label']} round {round_no}: rewrite failed ({e}).", phase=f"optimize:{target}", level="warn")
                    continue
                cand: Harness = proposal["harness"]
                add_cost(proposal["usage"].get("cost_usd"))
                self._event(oid, f"{spec['label']} round {round_no}: proposed harness {cand.fingerprint()} using {cand.models_used()}. " + " / ".join(cand.changelog[:4]), phase=f"optimize:{target}", data={"changelog": cand.changelog, "rationale": proposal["rationale"], "fingerprint": cand.fingerprint()})

                def on_round_progress(d: int, t: int, *, target: str = target, r_pct: float = r_pct, label: str = spec["label"], round_no: int = round_no) -> None:
                    self._progress(oid, f"optimize:{target}", r_pct + per_target * 0.5 * d / max(1, t) / rounds, f"{label}: round {round_no}/{rounds}, replayed and judged {d}/{t} runs")

                items = self._replay_and_score(oid, option["id"], cand, sample, "opt", round_no, sdk, tools, llm, cfg, add_cost, on_round_progress)
                agg = aggregate([x["metrics"] for x in items])
                base_agg = aggregate([x["baseline_metrics"] for x in items])
                score = objective(agg, base_agg)
                entry = {"round": round_no, "fingerprint": cand.fingerprint(), "models_used": cand.models_used(), "metrics": agg, "baseline_metrics": base_agg, "objective": score, "changelog": cand.changelog, "rationale": proposal["rationale"], "rewrite_usage": proposal["usage"], "worst_examples": self._worst_examples(items), "n": len(items)}
                rounds_log.append(entry)
                self.db.update_option(option["id"], rounds_json=rounds_log)
                self._event(oid, f"{spec['label']} round {round_no}: success {agg.get('success_rate')}% vs baseline {base_agg.get('success_rate')}%, quality {agg.get('quality')} vs {base_agg.get('quality')}, cost ${agg.get('cost_per_run')} vs ${base_agg.get('cost_per_run')} per run (optimization sample, n={len(items)}).", phase=f"optimize:{target}", data={"metrics": agg, "baseline": base_agg, "objective": score})
                previous.append({"round": round_no, "metrics": agg, "baseline_success_rate": base_agg.get("success_rate"), "baseline_quality": base_agg.get("quality"), "baseline_cost": base_agg.get("cost_per_run"), "worst_examples": entry["worst_examples"], "changelog": cand.changelog})
                if best is None or score > best["score"]:
                    best = {"harness": cand, "score": score, "round": round_no, "rationale": proposal["rationale"]}
                current = best["harness"] if best else current

            if best is None:
                self.db.update_option(option["id"], status="failed", rationale="No valid harness could be produced within the budget.")
                self._event(oid, f"{spec['label']}: no candidate produced.", phase=f"optimize:{target}", level="warn")
                continue

            # held-out evaluation ------------------------------------------------------------------
            t_pct = base_pct + per_target * 0.72
            self._progress(oid, f"test:{target}", t_pct, f"{spec['label']}: evaluating round-{best['round']} harness on {len(test_set)} held-out runs")
            def on_test_progress(d: int, t: int, *, target: str = target, t_pct: float = t_pct, label: str = spec["label"]) -> None:
                self._progress(oid, f"test:{target}", t_pct + per_target * 0.26 * d / max(1, t), f"{label}: held-out evaluation {d}/{t}")

            items = self._replay_and_score(oid, option["id"], best["harness"], test_set, "test", 0, sdk, tools, llm, cfg, add_cost, on_test_progress)
            agg = aggregate([x["metrics"] for x in items])
            base_agg = aggregate([x["baseline_metrics"] for x in items])
            baseline_test_items.extend(x["baseline_metrics"] for x in items)
            metrics = {"test": agg, "baseline_on_test": base_agg, "deltas": deltas(agg, base_agg), "meets_bar": meets_bar(agg, base_agg), "best_round": best["round"], "objective": best["score"], "n_test": len(items)}
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
            o["metrics"]["meets_bar"] = meets_bar(t_agg, baseline_agg)
            self.db.update_option(o["option_id"], metrics_json=o["metrics"])
        summary = self._summary(baseline_agg, option_results, len(opt_set), len(test_set), spent["usd"], cfg, tools.provider, llm.provider_name, analysis)
        self.db.update_optimization(oid, status="done", finished_at=now_iso(), summary_json=summary)
        self._progress(oid, "done", 100, summary.get("headline", {}).get("text", "done"))
        self._event(oid, "Done. " + summary.get("headline", {}).get("text", ""), phase="done", data={"spent_usd": round(spent["usd"], 4)})

    def resummarize(self, optimization_id: str) -> dict[str, Any]:
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
            o["metrics"]["meets_bar"] = meets_bar(t_agg, baseline_agg)
            self.db.update_option(o["option_id"], metrics_json=o["metrics"])
        old = opt.get("summary_json") or {}
        analysis = {"recommendations": (old.get("analysis") or {}).get("recommendations"), "per_step": (old.get("analysis") or {}).get("per_step")}
        summary = self._summary(baseline_agg, option_results, len(split.get("opt") or []), len(split.get("test") or []), float(old.get("spent_usd") or 0.0), cfg, old.get("search_provider") or "", old.get("provider") or "", analysis)
        self.db.update_optimization(optimization_id, summary_json=summary)
        self.db.add_event(optimization_id, "Recomputed checks, metrics and summary from the stored replays (judge verdicts unchanged). " + summary["headline"]["text"], phase="resummarize")
        return summary

    def _replay_and_score(self, oid: str, option_id: str, harness: Harness, records: list[dict[str, Any]], split: str, round_no: int, sdk: Downshift, tools: SearchTools, llm: LLM, cfg: dict[str, Any], add_cost: Any, on_progress: Any) -> list[dict[str, Any]]:
        """Replay each record with the harness, run checks and the blind judge, store everything."""
        done = {"n": 0}
        lock = threading.Lock()
        out: list[dict[str, Any]] = []
        judge_model = cfg["judge_model"]
        seed = int(cfg["seed"])

        def score_one(base_rec: dict[str, Any], rec: dict[str, Any]) -> None:
            checks = auto_checks(rec)
            base_checks = auto_checks(base_rec)
            judge = None
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
                out.append({"task_id": base_rec["task_id"], "question": base_rec.get("input", ""), "record": rec, "judge": judge, "checks": checks, "metrics": m, "baseline_metrics": bm})
                done["n"] += 1
                n = done["n"]
            on_progress(n, len(records))

        replay_many(sdk, harness, records, tools, concurrency=int(cfg["concurrency"]), meta={"optimization_id": oid, "option_id": option_id, "split": split, "round": round_no}, on_each=score_one)
        out.sort(key=lambda x: x["task_id"])
        return out

    @staticmethod
    def _n(x: Any, signed: bool = False) -> str:
        if x is None:
            return "n/a"
        return f"{float(x):+.0f}" if signed else f"{float(x):.0f}"

    @staticmethod
    def _summary(baseline: dict[str, Any], options: list[dict[str, Any]], n_opt: int, n_test: int, spent: float, cfg: dict[str, Any], search_provider: str, provider: str, analysis: dict[str, Any]) -> dict[str, Any]:
        rows = []
        for o in options:
            t = o["metrics"]["test"]
            rows.append({"key": o["key"], "label": o["label"], "models_used": o["models_used"], "metrics": t, "deltas": o["metrics"]["deltas"], "meets_bar": o["metrics"]["meets_bar"], "option_id": o["option_id"]})
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
        return {
            "headline": {"text": text, "verdict": verdict, "recommended": recommended["key"] if recommended else None},
            "baseline": baseline,
            "options": rows,
            "notes": notes,
            "split": {"optimization": n_opt, "test": n_test, "test_fraction": cfg.get("test_fraction"), "note": "All numbers above come from the held-out test set, which the optimizer never saw."},
            "bar": {"success_tol_pp": bar_tolerance_pp(baseline.get("n_judged") or baseline.get("n") or n_test), "quality_tol_pts": 5.0, "note": "Within the bar: task success no more than one held-out run (or 5 pp) below the baseline and quality within 5 points."},
            "spent_usd": round(spent, 4),
            "budget": {"rounds": cfg.get("rounds"), "sample_size": cfg.get("sample_size"), "max_cost_usd": cfg.get("max_cost_usd")},
            "judge": {"model": cfg.get("judge_model"), "method": "blind pairwise, random order, rubric: correct / complete / supported (0-5 each)"},
            "analysis": {"model": cfg.get("analysis_model"), "recommendations": analysis.get("recommendations"), "per_step": analysis.get("per_step")},
            "provider": provider,
            "search_provider": search_provider,
            "pricing_note": "Costs use Nebius Token Factory list prices applied to the recorded token counts.",
        }
