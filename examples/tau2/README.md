# Example: tau2-bench under Downshift, through the proxy

[tau2-bench](https://github.com/sierra-research/tau2-bench) (MIT) simulates customer-service conversations and
grades the final database state and actions. Its agent calls its model through LiteLLM with a configurable
`api_base`, so the adapter needs no access to tau2's internals: for each task it starts Downshift's
OpenAI-compatible proxy (`downshift.proxy.ChatProxy`) in front of the run and runs `tau2 run` for that one task
with the agent pointed at the proxy. The simulated customer calls the provider directly (Nemotron 3 Super,
thinking off, temperature 0, the same for every candidate). The grade is tau2's own reward; the telecom domain's
test tasks need no LLM judge (the communicate check uses substring matching).

Super is the baseline for this agent: on retail, Ultra scored below Super and Nano at 5-7 times the cost.

```bash
git clone https://github.com/sierra-research/tau2-bench && cd tau2-bench && uv sync --frozen
cp path/to/downshift/examples/tau2/{downshift_agent.py,downshift.yaml} .
uv pip install -p .venv/bin/python --no-deps -e path/to/downshift/sdk
python3 path/to/downshift/examples/tau2/build_tasks.py . telecom test      # 40 tasks
.venv/bin/python -m downshift.runner init-harness && .venv/bin/python -m downshift.runner check
.venv/bin/python -m downshift.runner record --project tau2-telecom --provider ollama --concurrency 3
```

Cost: telecom conversations are long (20-50 agent calls); a Super run averaged about $0.19 at Token Factory
list prices in the smoke test, so 40 tasks cost about $7-8 per Super arm.
