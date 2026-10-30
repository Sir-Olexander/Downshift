"""Downshift adapter for tau2-bench (Sierra), telecom domain by default. tau2's code is not modified.

The agent under test is tau2's own LLM agent. For one task this adapter:
  1. starts Downshift's OpenAI-compatible proxy in front of the run (downshift.proxy.ChatProxy), so every
     agent model call goes through run.chat with the harness's model, sampling, system prompt (tau2's
     policy prompt stands in as {original_system_prompt}) and runtime repairs;
  2. runs `tau2 run` for that single task in tau2's own environment, with the agent pointed at the proxy
     and the simulated user pointed straight at the provider (Nemotron 3 Super, thinking off, temperature
     0: the same user for every candidate);
  3. reads tau2's reward for the task (database state and required actions; telecom tasks need no LLM
     judge, and the communicate check uses substring matching) and grades the run with it.

Replays run every tool live (tau2's tools change its database), so reuse_tool_results is False.
Env: TAU2_DOMAIN (default telecom), TAU2_USER_MODEL (default nemotron-3-super).
"""

from __future__ import annotations

import json
import os
import shutil
import subprocess
import uuid
from pathlib import Path
from typing import Any

from downshift import AgentAdapter, Harness, Run, Task, default_table
from downshift.proxy import ChatProxy

HERE = Path(__file__).resolve().parent
TAU2 = HERE / ".venv" / "bin" / "tau2"
DOMAIN = os.environ.get("TAU2_DOMAIN", "telecom")
USER_MODEL = os.environ.get("TAU2_USER_MODEL", "nemotron-3-super")
TIMEOUT_S = int(os.environ.get("TAU2_TASK_TIMEOUT_S", "1800"))

CONTRACT = """tau2's own agent code runs the conversation: it receives the domain policy as its system prompt, talks to a
simulated customer and calls the domain's tools through the API tools field. The system prompt here must keep the
placeholder {original_system_prompt} (tau2's policy text is substituted there; without it the policy is put first
and the harness text after it). The run is graded by tau2 on the final database state and the actions taken, so
policy rules must not be contradicted. Tools and their schemas come from tau2 and cannot be renamed. Every reply
without a tool call is a message to the customer, not a final answer: do not set final_format on this step."""


class Tau2Agent(AgentAdapter):
    name = "tau2"
    reuse_tool_results = False  # tau2's tools change its database

    def run(self, task: Task, harness: Harness, run: Run) -> None:
        tau2_id = (task.meta or {}).get("tau2_id") or task.input
        provider = run.llm.provider_name
        table = default_table()
        p = table.provider(provider)
        user_args: dict[str, Any] = {"temperature": 0.0}
        extra = table.reasoning_params(USER_MODEL, provider, "off")
        if extra:
            user_args["extra_body"] = extra
        save = f"downshift_{uuid.uuid4().hex[:12]}"
        out_dir = HERE / "data" / "simulations" / save
        env = dict(os.environ)
        env["OPENAI_API_KEY"] = p.api_key() or "unused"  # the simulated user calls the provider directly
        env["OPENAI_API_BASE"] = env["OPENAI_BASE_URL"] = p.base_url
        with ChatProxy(run, harness) as proxy:
            cmd = [str(TAU2), "run", "--domain", DOMAIN, "--task-ids", tau2_id, "--num-trials", "1",
                   "--agent-llm", "openai/downshift", "--agent-llm-args", json.dumps({"api_base": proxy.base_url, "api_key": "unused", "num_retries": 2}),
                   "--user-llm", f"openai/{table.resolve(USER_MODEL, provider)}", "--user-llm-args", json.dumps(user_args),
                   "--communicate-scorer", "substring", "--save-to", save, "--max-concurrency", "1"]
            try:
                proc = subprocess.run(cmd, cwd=HERE, env=env, capture_output=True, text=True, timeout=TIMEOUT_S)
            except subprocess.TimeoutExpired:
                run.fail(f"tau2 did not finish within {TIMEOUT_S}s")
                shutil.rmtree(out_dir, ignore_errors=True)
                return
        try:
            results = json.loads((out_dir / "results.json").read_text())
            sim = (results.get("simulations") or [])[0]
        except Exception as e:
            tail = (proc.stderr or proc.stdout or "")[-600:]
            run.fail(f"tau2 produced no result ({type(e).__name__}); exit {proc.returncode}: {tail}")
            shutil.rmtree(out_dir, ignore_errors=True)
            return
        reward = (sim.get("reward_info") or {}).get("reward")
        termination = sim.get("termination_reason")
        n_msgs = len(sim.get("messages") or [])
        shutil.rmtree(out_dir, ignore_errors=True)
        if harness.step("agent").final_format:
            run.fail("final_format is not allowed on a conversational agent: every reply without a tool call goes to the customer")
            return
        if proxy.errors:
            run.fail("proxy errors: " + " | ".join(proxy.errors[:3]))
            return
        run.finish(f"tau2 {DOMAIN} task finished ({termination}); reward {reward}", [], reward=reward, termination=str(termination), messages=n_msgs, agent_calls=proxy.calls)

    def score(self, task: Task, output: dict[str, Any]) -> dict[str, Any]:
        r = output.get("reward")
        passed = r is not None and float(r) >= 1.0 - 1e-9
        return {"passed": passed, "score": float(r or 0.0), "details": f"tau2 reward {r} ({output.get('termination')})"}

    def default_harness(self) -> Harness:
        return Harness.from_dict({
            "name": f"tau2-{DOMAIN}",
            "version": 1,
            "runtime": "custom",
            "description": f"tau2-bench's LLM agent on the {DOMAIN} domain: follows the policy, talks to a simulated customer and calls the domain tools.",
            "contract": CONTRACT,
            # tau2 runs the agent at temperature 0 in our earlier measurements; Super is the baseline here
            # (Ultra scored below Super and Nano on retail at 5-7x the cost)
            "defaults": {"model": "nemotron-3-super", "temperature": 0.0, "max_tokens": None},
            "system_prompt": "{original_system_prompt}",
            "tools": {},
            "steps": [{"id": "agent", "kind": "tool_loop", "description": "The whole agent: reads the policy, converses with the customer and calls tools until the task is resolved or the customer ends the call."}],
        })


agent = Tau2Agent()
