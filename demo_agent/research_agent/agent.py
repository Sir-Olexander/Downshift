"""The research agent. All behaviour comes from the harness; this file only interprets the step plan.

Step kinds the harness can use, in any order and with any models:
  plan        the model writes search queries for the question
  search      a tool loop: the model calls web_search / read_page until it has enough evidence
  synthesize  the model writes the final sourced answer from the collected evidence
  verify      the model checks the answer against the evidence; can trigger one rewrite
"""

from __future__ import annotations

import json
import re
from typing import Any

from downshift import Harness, Run, Step, extract_urls

from .tools import SearchTools
MAX_TOOL_RESULT_CHARS = 6000
MAX_EVIDENCE_CHARS = 14000


def _render(template: str, **values: Any) -> str:
    out = template
    for k, v in values.items():
        out = out.replace("{" + k + "}", str(v))
    return out


def _extract_json(text: str) -> dict[str, Any] | None:
    text = text.strip()
    if text.startswith("```"):
        text = re.sub(r"^```[a-zA-Z]*\n?", "", text)
        text = re.sub(r"\n?```$", "", text)
    try:
        v = json.loads(text)
        return v if isinstance(v, dict) else None
    except json.JSONDecodeError:
        pass
    m = re.search(r"\{.*\}", text, re.S)
    if m:
        try:
            v = json.loads(m.group(0))
            return v if isinstance(v, dict) else None
        except json.JSONDecodeError:
            return None
    return None


class ResearchAgent:
    def __init__(self, harness: Harness, run: Run, tools: SearchTools):
        self.harness = harness
        self.run = run
        self.tools = tools

    # ---- public -------------------------------------------------------------------------
    def answer(self, question: str) -> dict[str, Any]:
        ctx: dict[str, Any] = {
            "question": question, "queries": [], "plan_notes": "", "evidence": [], "search_notes": "",
            "answer": "", "feedback": "", "verify": None, "synth_step": None, "retried": False, "steps_run": [],
        }
        for step in self.harness.steps:
            if not step.enabled:
                continue
            ctx["steps_run"].append(step.id)
            if step.kind == "plan":
                self._plan(step, ctx)
            elif step.kind == "search":
                self._search(step, ctx)
            elif step.kind == "synthesize":
                ctx["synth_step"] = step
                self._synthesize(step, ctx)
            elif step.kind == "verify":
                self._verify(step, ctx)
        answer = (ctx["answer"] or "").strip()
        sources = self._sources(answer)
        self.run.finish(
            answer,
            sources,
            evidence=[{"title": e["title"], "url": e["url"]} for e in ctx["evidence"]],
            queries=ctx["queries"],
            steps_run=ctx["steps_run"],
            verify=ctx["verify"],
        )
        return {"answer": answer, "sources": sources, "evidence": ctx["evidence"], "verify": ctx["verify"]}

    # ---- steps --------------------------------------------------------------------------
    def _messages(self, step: Step, user: str) -> list[dict[str, Any]]:
        msgs: list[dict[str, Any]] = [{"role": "system", "content": self.harness.system_prompt}]
        for ex in step.few_shot:
            msgs.append({"role": "user", "content": ex.input})
            msgs.append({"role": "assistant", "content": ex.output})
        msgs.append({"role": "user", "content": user})
        return msgs

    def _plan(self, step: Step, ctx: dict[str, Any]) -> None:
        user = _render(step.prompt, question=ctx["question"])
        res = self.run.chat(step, self._messages(step, user))
        data = _extract_json(res.content) or {}
        queries = data.get("queries") if isinstance(data.get("queries"), list) else None
        if not queries:
            lines = [l.strip("-*• \t") for l in res.content.splitlines() if l.strip()]
            queries = [l for l in lines if 3 < len(l) < 200 and not l.startswith("{")][:3]
        ctx["queries"] = [str(q) for q in queries][:3] or [ctx["question"]]
        ctx["plan_notes"] = str(data.get("notes") or "")

    def _search(self, step: Step, ctx: dict[str, Any]) -> None:
        queries = ctx["queries"] or [ctx["question"]]
        user = _render(step.prompt, question=ctx["question"], queries="; ".join(queries), notes=ctx["plan_notes"])
        msgs = self._messages(step, user)
        tool_defs = self.tools.tool_defs(self.harness)
        budget = step.max_tool_calls if step.max_tool_calls is not None else 6
        used = 0
        rounds = 0
        while rounds < budget + 2:
            rounds += 1
            remaining = budget - used
            res = self.run.chat(step, msgs, tools=tool_defs if remaining > 0 else None)
            msgs.append(res.assistant_message())
            if not res.tool_calls or remaining <= 0:
                ctx["search_notes"] = (res.content or "").strip()
                break
            for tc in res.tool_calls[:remaining]:
                used += 1
                result = self._call_tool(step, tc.name, tc.arguments, ctx)
                msgs.append({"role": "tool", "tool_call_id": tc.id, "name": tc.name, "content": json.dumps(result, ensure_ascii=False)[:MAX_TOOL_RESULT_CHARS]})
            for tc in res.tool_calls[remaining:]:  # over budget: tell the model instead of calling
                msgs.append({"role": "tool", "tool_call_id": tc.id, "name": tc.name, "content": json.dumps({"error": "tool budget exhausted; answer with what you have"})})
        if not ctx["evidence"] and not any(e.get("type") == "tool_call" for e in [ev.model_dump() for ev in self.run.events]):
            # the model never searched: do the planned searches so synthesis has something to work with
            for q in queries[:2]:
                self._call_tool(step, "web_search", {"query": q, "max_results": 5}, ctx)

    def _call_tool(self, step: Step, name: str, args: dict[str, Any], ctx: dict[str, Any]) -> Any:
        try:
            result = self.run.tool(name, args, lambda: self.tools.call(name, args), step=step.id)
        except Exception as e:
            return {"error": f"{type(e).__name__}: {e}"[:300]}
        self._collect_evidence(name, args, result, ctx)
        return result

    def _collect_evidence(self, name: str, args: dict[str, Any], result: Any, ctx: dict[str, Any]) -> None:
        if not isinstance(result, dict):
            return
        seen = {e["url"] for e in ctx["evidence"]}
        if name == "web_search":
            for r in result.get("results") or []:
                url = r.get("url") or ""
                if url and url not in seen:
                    ctx["evidence"].append({"title": r.get("title", ""), "url": url, "text": r.get("snippet", ""), "kind": "snippet"})
                    seen.add(url)
        elif name == "read_page" and result.get("text"):
            url = result.get("url") or args.get("url", "")
            text = result["text"][:2500]
            for e in ctx["evidence"]:
                if e["url"] == url:
                    e["text"], e["kind"] = text, "page"
                    break
            else:
                ctx["evidence"].append({"title": result.get("title", ""), "url": url, "text": text, "kind": "page"})

    def _format_evidence(self, ctx: dict[str, Any]) -> str:
        parts: list[str] = []
        total = 0
        for i, e in enumerate(ctx["evidence"], 1):
            chunk = f"[{i}] {e['title']}\nURL: {e['url']}\n{e['text']}\n"
            if total + len(chunk) > MAX_EVIDENCE_CHARS:
                break
            parts.append(chunk)
            total += len(chunk)
        if ctx.get("search_notes"):
            parts.append(f"Researcher notes: {ctx['search_notes'][:1500]}")
        return "\n".join(parts) if parts else "(no evidence was collected)"

    def _synthesize(self, step: Step, ctx: dict[str, Any]) -> None:
        user = _render(step.prompt, question=ctx["question"], evidence=self._format_evidence(ctx), feedback=ctx["feedback"])
        if ctx["feedback"] and "{feedback}" not in step.prompt:
            user += f"\n\nA reviewer found these problems with the previous draft; fix them:\n{ctx['feedback']}"
        res = self.run.chat(step, self._messages(step, user))
        if not (res.content or "").strip() and res.finish_reason == "length":
            # the model spent the whole budget thinking: one retry with twice the room (both calls stay in the trace)
            budget = self.harness.params(step).max_tokens
            res = self.run.chat(step, self._messages(step, user), max_tokens=budget * 2)
        ctx["answer"] = res.content

    def _verify(self, step: Step, ctx: dict[str, Any]) -> None:
        user = _render(step.prompt, question=ctx["question"], answer=ctx["answer"], evidence=self._format_evidence(ctx))
        res = self.run.chat(step, self._messages(step, user))
        data = _extract_json(res.content) or {}
        ok = bool(data.get("ok", True))
        problems = data.get("problems") if isinstance(data.get("problems"), list) else []
        ctx["verify"] = {"ok": ok, "problems": [str(p) for p in problems][:5], "raw": res.content[:800]}
        if not ok and step.retry_on_fail and not ctx["retried"] and ctx["synth_step"] is not None:
            ctx["retried"] = True
            ctx["feedback"] = "\n".join(f"- {p}" for p in ctx["verify"]["problems"]) or "The answer is not well supported by the evidence."
            self._synthesize(ctx["synth_step"], ctx)

    # ---- output -------------------------------------------------------------------------
    @staticmethod
    def _sources(answer: str) -> list[str]:
        return extract_urls(answer)
