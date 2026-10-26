"""Rewrite: Nemotron 3 Ultra proposes a new harness for the target model.

It may change the system prompt, tool descriptions, few-shot examples, the step plan (add or drop
steps, add a verify step with a retry), the model per step and sampling/reasoning settings.
"""

from __future__ import annotations

import re
from typing import Any

from downshift import LLM, Harness, HarnessError, ModelTable

SCHEMA_DOC = """The harness is YAML with exactly these fields:
name (string), version (int or string), description (string),
defaults: {model, temperature, max_tokens, reasoning?}  # reasoning: on|off|low|medium|high
system_prompt (string),
tools: {web_search: {description}, read_page: {description}}   # keep both tool names; only descriptions change
steps: list of {id, kind, prompt, model?, temperature?, max_tokens?, reasoning?, max_tool_calls?, few_shot?, retry_on_fail?, enabled?}
changelog: list of short strings describing what you changed and why.

Step kinds and the placeholders their prompt may use:
- plan: writes search queries. Placeholders: {question}. The agent expects JSON {"queries": [...], "notes": "..."}.
- search: a tool loop with web_search / read_page until the model answers without a tool call. Placeholders: {question}, {queries}, {notes}. max_tool_calls caps the loop.
- synthesize: writes the final answer from the evidence. Placeholders: {question}, {evidence}, {feedback}. The answer must cite [n] markers and end with a "Sources:" list of URLs (the scorer checks that cited URLs come from the evidence).
- verify: checks the answer. Placeholders: {question}, {answer}, {evidence}. The agent expects JSON {"ok": true|false, "problems": [...]}. With retry_on_fail: true a failed check reruns synthesize once with the problems as {feedback}.
Steps run in order. At least one search step and one synthesize step must be enabled. few_shot items are {input, output} pairs shown before the step's user message."""

SYSTEM = """You are an expert at adapting LLM agent harnesses to smaller, cheaper models without losing task quality.
You return a complete, valid harness YAML inside a single ```yaml block, followed by a short "Rationale:" paragraph."""

USER = """Goal: make this research agent work as well as possible on the target model(s) below, at the lowest cost.
{target_instructions}

Target model notes:
{guidance}

Current harness (the agent's behaviour lives entirely in this file):
```yaml
{harness}
```

What the step analysis found on recorded baseline runs (labelled by Nemotron 3 Nano):
{analysis}

{history}

Rules:
- Output the complete new harness (every field), not a diff. Keep the tool names web_search and read_page.
- Only use these model ids: {allowed_models}. {model_rule}
- Keep prompts concrete. Smaller models need explicit output formats, short numbered rules and clear stop conditions.
- The final answer must keep inline [n] citations and the "Sources:" list of URLs taken from the evidence, because the scorer checks sources.
- Prefer fewer, cheaper model calls: for example reasoning off for mechanical steps, a tight max_tool_calls, and no plan step if the search step can plan for itself.
- Add a verify step with retry_on_fail only if you think the target model needs the safety net; it costs an extra call.
- Fill `changelog` with 3-6 short lines describing the changes.

{schema}

Respond with the YAML in one ```yaml block, then "Rationale:" and two or three sentences."""


def _target_instructions(target: str, allowed: list[str]) -> tuple[str, str]:
    if target == "mix":
        return (
            "Target: a per-step mix. Assign each step the cheapest model that can do it well (use the step analysis). "
            "Keep Nemotron 3 Ultra only for steps that clearly need it. The harness must not use Ultra for every step.",
            "The mix must use at least one model other than nemotron-3-ultra.",
        )
    model = allowed[0]
    return (
        f"Target: run every step on {model}.",
        f"Every step (and defaults.model) must use {model}.",
    )


def _history_text(previous: list[dict[str, Any]]) -> str:
    if not previous:
        return "This is the first round: no candidates have been tried yet."
    parts = ["Previous rounds on the optimization set (held-out test set is never used here):"]
    for p in previous:
        m = p.get("metrics") or {}
        parts.append(
            f"- round {p.get('round')}: success {m.get('success_rate')}% (baseline {p.get('baseline_success_rate')}%), "
            f"quality {m.get('quality')}/100 (baseline {p.get('baseline_quality')}), cost ${m.get('cost_per_run')}/run "
            f"(baseline ${p.get('baseline_cost')}), checks passed {m.get('checks_pass_rate')}%"
        )
        for ex in p.get("worst_examples") or []:
            parts.append(f"  worst example: Q: {ex.get('question','')[:140]} | judge: {ex.get('reason','')[:220]} | checks: {ex.get('checks','')}")
        if p.get("changelog"):
            parts.append("  that round's changelog: " + " / ".join(p["changelog"][:6]))
    parts.append("Fix the failure patterns above. Keep what worked. If a change made things worse, revert it.")
    return "\n".join(parts)


def _extract_yaml(text: str) -> str | None:
    m = re.search(r"```ya?ml\s*\n(.*?)```", text, re.S)
    if m:
        return m.group(1)
    m = re.search(r"```\s*\n(name:.*?)```", text, re.S)
    if m:
        return m.group(1)
    if text.strip().startswith("name:"):
        return text.split("Rationale:")[0]
    return None


def _extract_rationale(text: str) -> str:
    m = re.search(r"Rationale:\s*(.+)$", text, re.S)
    return (m.group(1).strip() if m else "").split("```")[0].strip()[:1200]


def _check_target(h: Harness, target: str, allowed: list[str]) -> None:
    used = h.models_used()
    bad = [m for m in used if m not in allowed]
    if bad:
        raise HarnessError(f"models {bad} are not allowed for this target (allowed: {allowed})")
    if target == "mix":
        if used == ["nemotron-3-ultra"]:
            raise HarnessError("the mix must move at least one step off nemotron-3-ultra")
    else:
        if any(m != allowed[0] for m in used):
            raise HarnessError(f"every step must use {allowed[0]} for this target, got {used}")


def propose_harness(llm: LLM, model: str, *, current: Harness, target: str, allowed_models: list[str], analysis_text: str, guidance: str, previous: list[dict[str, Any]], round_no: int, table: ModelTable, provider: str, base_version: str | int | None = None) -> dict[str, Any]:
    target_instructions, model_rule = _target_instructions(target, allowed_models)
    user = USER.format(
        target_instructions=target_instructions, guidance=guidance, harness=current.to_yaml(), analysis=analysis_text,
        history=_history_text(previous), allowed_models=", ".join(allowed_models), model_rule=model_rule, schema=SCHEMA_DOC,
    )
    msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]
    usage = {"tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0, "attempts": 0}
    last_error = ""
    for attempt in range(3):
        usage["attempts"] += 1
        res = llm.chat(model, msgs, temperature=0.4, max_tokens=4000, reasoning="on")
        usage["tokens_in"] += res.tokens_in
        usage["tokens_out"] += res.tokens_out
        usage["cost_usd"] += llm.table.cost(model, res.tokens_in, res.tokens_out) or 0.0
        yaml_text = _extract_yaml(res.content)
        try:
            if not yaml_text:
                raise HarnessError("no ```yaml block found in the response")
            h = Harness.from_yaml(yaml_text)
            h.validate_models(table, provider)
            _check_target(h, target, allowed_models)
        except HarnessError as e:
            last_error = str(e)
            msgs.append({"role": "assistant", "content": res.content})
            msgs.append({"role": "user", "content": f"That harness is invalid: {e}\nReturn the corrected complete harness in one ```yaml block, then the Rationale."})
            continue
        base = base_version if base_version is not None else current.version
        version = f"{base}-{target}-r{round_no}" if round_no else f"{base}-{target}"
        h = h.copy_with(version=version)
        return {"harness": h, "rationale": _extract_rationale(res.content), "usage": usage, "raw": res.content[:20000]}
    raise HarnessError(f"the rewriter did not produce a valid harness after {usage['attempts']} attempts: {last_error}")
