# Example: text2sql-framework under Downshift

[text2sql-framework](https://github.com/Text2SqlAgent/text2sql-framework) (MIT) answers questions about
a SQL database with one `execute_sql` tool. These files let Downshift record, replay and optimize it.
text2sql's own code is not changed.

| file | role |
|---|---|
| `downshift_agent.py` | the adapter: builds text2sql's own `SQLGenerator`, routes its model calls through `run.chat` and its `execute_sql` calls through `run.tool`, then grades the final SQL against the Spider gold SQL with the author's benchmark rule |
| `downshift.yaml` | runs the agent with its own environment (`.venv/bin/python`) |
| `build_text2sql_set.py` | builds the test set: the author's 19 published Spider questions + 21 random Spider dev questions, on the author's merged 80-table database |

With the default harness (`init-harness`), the adapter sends exactly what text2sql sends: its own
system prompt and tool schema, and no temperature or max_tokens.

## Setup

```bash
git clone https://github.com/Text2SqlAgent/text2sql-framework && cd text2sql-framework
cp path/to/downshift/examples/text2sql/{downshift_agent.py,downshift.yaml} .
uv venv .venv && uv pip install -p .venv/bin/python -e ".[openai]" -e path/to/downshift/sdk

# data: the 20 Spider dev databases as DATA/spider_db/<db_id>.sqlite and the dev questions as
# DATA/spider_dev.json ([{"db_id", "question", "query"}], e.g. from huggingface.co/datasets/xlangai/spider)
python3 path/to/downshift/examples/text2sql/build_text2sql_set.py DATA .    # writes tasks.jsonl
export TEXT2SQL_DATA_DIR=DATA

.venv/bin/python -m downshift.runner init-harness
.venv/bin/python -m downshift.runner check
.venv/bin/python -m downshift.runner record --project text2sql      # 40 tasks on Ultra, about $0.45
```

Then register the folder as agent `text2sql` (Agents screen, or `POST /v1/agents`) and optimize:

```bash
uv run python -m app.cli optimize --project text2sql --targets super,nano --rounds 2 --sample 8   # from server/
```
