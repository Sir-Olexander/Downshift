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

SCHEMA_DOC_CUSTOM = """The harness is YAML with these fields:
name, version, description, runtime (keep "custom"), contract (keep exactly as given),
defaults: {model, temperature, max_tokens, reasoning?}   # reasoning: on|off|low|medium|high; temperature/max_tokens may be null (= provider default)
system_prompt (string),
tools: {<tool name>: {description, parameters?}}   # keep every tool name; you may only rewrite descriptions
steps: list of {id, kind, description?, prompt?, model?, temperature?, max_tokens?, reasoning?, max_tool_calls?, few_shot?, enabled?}
changelog: list of short strings describing what you changed and why.

The agent's own code runs the steps: you cannot add, remove, rename or reorder steps, change a step's
kind, or rename tools. You can rewrite the system prompt, step prompts and tool descriptions, add
few_shot examples ({input, output} pairs shown before the step's user message), and set the model,
temperature, max_tokens, reasoning and max_tool_calls per step or in defaults. Whatever you write must
still satisfy the contract, because the agent's code depends on it.

few_shot examples are plain text turns: the model never sees real tool calls in them. Never write a
tool call as text in a few_shot output (no {"tool": ...} or execute_sql(...) lines): the model copies
the format, writes its tool calls as text instead of calling the tool, and the agent stops. Use
few_shot only to show the final reply format. Use only syntax and names that the recorded runs show
work in this agent's environment."""

USER_CUSTOM = """Goal: make this agent work as well as possible on the target model(s) below, at the lowest cost.
{target_instructions}

Target model notes:
{guidance}

Current harness (the prompts and models the agent's code uses live in this file):
```yaml
{harness}
```

The agent's steps (run by its own code, in this order):
{steps}

Contract (what the agent's code requires; the new harness must keep satisfying it):
{contract}

How runs are scored: {scoring}

What the step analysis found on recorded baseline runs (labelled by Nemotron 3 Nano):
{analysis}

{history}

Rules:
- Output the complete new harness (every field), not a diff. Keep name, runtime, contract, every step id and kind, and every tool name.
- Only use these model ids: {allowed_models}. {model_rule}
- Smaller models need explicit output formats, short numbered rules and clear stop conditions. Look at how failed runs went wrong and target that.
- Reasoning (thinking) tokens count against max_tokens: if you set max_tokens on a step with reasoning on, leave plenty of room, or the answer comes back empty.
- Correctness first. Cut cost (thinking off, fewer calls, fewer tokens) only where the recorded runs show the step does not need it; a cheaper step that fails the task costs more than it saves.
- Fill `changelog` with 3-6 short lines describing the changes.

{schema}

Respond with the YAML in one ```yaml block, then "Rationale:" and two or three sentences."""

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
- Correctness first; then fewer, cheaper model calls where the recorded runs show a step does not need the strong setting (for example a tight max_tool_calls, or no plan step if the search step can plan for itself).
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
            line = f"  worst example: Q: {ex.get('question','')[:140]} | verdict: {ex.get('reason','')[:220]} | checks: {ex.get('checks','')} | output: {ex.get('answer_excerpt','')[:200]!r}"
            final = (ex.get('final_message') or '').strip()
            if final and final[:120] != (ex.get('answer_excerpt') or '')[:120]:
                line += f" | the model's final message: {final[:260]!r}"
            parts.append(line)
        if p.get("changelog"):
            parts.append("  that round's changelog: " + " / ".join(p["changelog"][:6]))
    parts.append("Fix the failure patterns above. Keep what worked. If a change made things worse, revert it.")
    return "\n".join(parts)


def _extract_yaml(text: str) -> str | None:
    # The closing fence must start a line: prompts inside the YAML (indented block scalars) can
    # themselves mention ```sql blocks, and those must not end the YAML early.
    m = re.search(r"```ya?ml[^\n]*\n(.*?)\n```[ \t]*(?:\n|$)", text, re.S)
    if m:
        return m.group(1)
    m = re.search(r"```[ \t]*\n(name:.*?)\n```[ \t]*(?:\n|$)", text, re.S)
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


def _steps_text(h: Harness) -> str:
    lines = []
    for s in h.steps:
        tools = f", up to {s.max_tool_calls} tool calls" if s.max_tool_calls is not None else ""
        lines.append(f"- {s.id} (kind: {s.kind}{tools}{'' if s.enabled else ', disabled'}): {s.description or 'no description'}")
    lines.append("Tools: " + (", ".join(f"{name} ({spec.description[:120]})" for name, spec in h.tools.items()) or "none"))
    return "\n".join(lines)


def _check_few_shot(h: Harness) -> None:
    """Reject few_shot outputs that write tool calls as text: models imitate them and stop calling tools."""
    for step in h.steps:
        for ex in step.few_shot:
            for name in h.tools:
                if re.search(rf'["\']?(?:tool|name|function)["\']?\s*:\s*["\']{re.escape(name)}["\']|\b{re.escape(name)}\s*\(', ex.output):
                    raise HarnessError(f"step '{step.id}': a few_shot output writes a {name} tool call as text; few_shot outputs must not contain tool calls (show only the final reply)")


def _check_custom(h: Harness, current: Harness) -> Harness:
    """The rewriter may only change what the harness controls, never the agent's structure.
    Returns the harness with name, runtime, contract and tool schemas restored from `current`."""
    if h.runtime != "custom":
        raise HarnessError("keep runtime: custom")
    want = [(s.id, s.kind) for s in current.steps]
    got = [(s.id, s.kind) for s in h.steps]
    if got != want:
        raise HarnessError(f"the steps must stay exactly {want} (id, kind) in this order; got {got}")
    if set(h.tools) != set(current.tools):
        raise HarnessError(f"the tools must stay exactly {sorted(current.tools)}; got {sorted(h.tools)}")
    data = h.to_dict()
    data["name"] = current.name
    data["runtime"] = "custom"
    if current.contract:
        data["contract"] = current.contract
    for name, spec in current.tools.items():
        if spec.parameters is not None:
            data["tools"][name]["parameters"] = spec.parameters
    for s_new, s_old in zip(data["steps"], current.steps):
        if s_old.description and not s_new.get("description"):
            s_new["description"] = s_old.description
    return Harness.from_dict(data)


def propose_harness(llm: LLM, model: str, *, current: Harness, target: str, allowed_models: list[str], analysis_text: str, guidance: str, previous: list[dict[str, Any]], round_no: int, table: ModelTable, provider: str, base_version: str | int | None = None, scoring: str = "judge") -> dict[str, Any]:
    target_instructions, model_rule = _target_instructions(target, allowed_models)
    if current.runtime == "custom":
        scoring_text = {
            "ground_truth": "each run is graded pass/fail against the task's correct answer by the agent's own grader. Success rate is what counts.",
            "mixed": "graded against the task's correct answer where there is one, otherwise compared with the baseline answer by an LLM judge.",
        }.get(scoring, "an LLM judge compares each answer with the baseline answer for correctness and completeness.")
        user = USER_CUSTOM.format(
            target_instructions=target_instructions, guidance=guidance, harness=current.to_yaml(), steps=_steps_text(current),
            contract=current.contract or "(none stated)", scoring=scoring_text, analysis=analysis_text,
            history=_history_text(previous), allowed_models=", ".join(allowed_models), model_rule=model_rule, schema=SCHEMA_DOC_CUSTOM,
        )
    else:
        user = USER.format(
            target_instructions=target_instructions, guidance=guidance, harness=current.to_yaml(), analysis=analysis_text,
            history=_history_text(previous), allowed_models=", ".join(allowed_models), model_rule=model_rule, schema=SCHEMA_DOC,
        )
    msgs = [{"role": "system", "content": SYSTEM}, {"role": "user", "content": user}]
    usage = {"tokens_in": 0, "tokens_out": 0, "cost_usd": 0.0, "attempts": 0}
    last_error = ""
    for attempt in range(3):
        usage["attempts"] += 1
        res = llm.chat(model, msgs, temperature=0.4, max_tokens=8000, reasoning="on")
        usage["tokens_in"] += res.tokens_in
        usage["tokens_out"] += res.tokens_out
        usage["cost_usd"] += llm.table.cost(model, res.tokens_in, res.tokens_out) or 0.0
        yaml_text = _extract_yaml(res.content)
        try:
            if not yaml_text:
                raise HarnessError("no ```yaml block found in the response")
            h = Harness.from_yaml(yaml_text)
            _check_few_shot(h)
            if current.runtime == "custom":
                h = _check_custom(h, current)
            elif h.runtime != "research":
                raise HarnessError("keep the research runtime (do not set runtime)")
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
