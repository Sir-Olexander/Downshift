"""Every demo agent folder has a valid harness that the shared runtime can run, and a task list."""

import json
from pathlib import Path

import pytest
from downshift import Harness, default_table

REPO = Path(__file__).resolve().parents[2]
FOLDERS = [REPO / "demo_agent", *sorted(p for p in (REPO / "demo_agents").iterdir() if p.is_dir())]
RUNTIME_TOOLS = {"web_search", "read_page"}


@pytest.mark.parametrize("folder", FOLDERS, ids=lambda p: p.name)
def test_demo_agent_folder(folder: Path) -> None:
    harness = Harness.from_yaml((folder / "harness.yaml").read_text(encoding="utf-8"))
    harness.validate_models(default_table())
    assert set(harness.tools) <= RUNTIME_TOOLS
    assert any(s.kind == "synthesize" for s in harness.steps)
    tasks = json.loads((folder / "questions.json").read_text(encoding="utf-8"))
    ids = [t["id"] for t in tasks]
    assert len(tasks) >= 10 and len(ids) == len(set(ids))
    assert all(t["question"].strip() for t in tasks)
    assert (folder / "record_baseline.py").is_file()
