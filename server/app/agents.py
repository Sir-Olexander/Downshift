"""Agent folders: inspect a folder on disk, draft a harness.yaml for it, write it back.

The UI's onboarding uses these to go from "here is my agent's folder" to a harness the SDK can
load. Everything stays inside the configured agents root.
"""

from __future__ import annotations

import ast
import json
import re
import shlex
import subprocess
import sys
from pathlib import Path
from typing import Any

from downshift import Harness, HarnessError, default_table
from downshift.adapter import has_adapter, load_agent_config

HARNESS_FILE = "harness.yaml"
QUESTION_FILES = ("questions.json", "tasks.json", "questions.jsonl", "tasks.jsonl")
RECORD_SCRIPTS = ("record_baseline.py", "record.py")
SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".next", ".pytest_cache", ".ruff_cache", "dist", "build"}
# public helpers on a tools class that are plumbing, not tools the model calls
NOT_TOOLS = {"call", "tool_defs", "provider", "run", "main", "close", "schema", "schemas"}


class FolderError(ValueError):
    pass


def resolve_inside(root: Path, raw: str) -> Path:
    """Resolve a user-supplied path and refuse anything outside `root`."""
    if not raw or not raw.strip():
        raise FolderError("enter a folder path")
    p = Path(raw.strip()).expanduser()
    if not p.is_absolute():
        p = root / p
    p = p.resolve()
    if p != root and root not in p.parents:
        raise FolderError(f"only folders inside {root} can be used")
    return p


def slug(text: str) -> str:
    s = re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")
    return s[:48] or "agent"


def browse(root: Path, raw: str | None) -> dict[str, Any]:
    p = resolve_inside(root, raw or str(root))
    if not p.is_dir():
        raise FolderError(f"{p} is not a folder")
    dirs = []
    try:
        for c in sorted(p.iterdir(), key=lambda x: x.name.lower()):
            if c.is_dir() and not c.name.startswith(".") and c.name not in SKIP_DIRS:
                dirs.append({"name": c.name, "path": str(c), "has_harness": (c / HARNESS_FILE).is_file()})
    except PermissionError:
        pass
    return {"path": str(p), "parent": str(p.parent) if p != root else None, "root": str(root), "dirs": dirs, "has_harness": (p / HARNESS_FILE).is_file()}


def _readme_summary(folder: Path) -> str:
    for name in ("README.md", "readme.md", "README.txt", "README"):
        f = folder / name
        if f.is_file():
            for para in f.read_text(encoding="utf-8", errors="replace").split("\n\n"):
                t = " ".join(line.strip() for line in para.splitlines()).strip()
                if t and not t.startswith(("#", "```", "-", "|", ">")):
                    return t[:300]
    return ""


def _python_files(folder: Path, limit: int = 200) -> list[Path]:
    out: list[Path] = []
    for f in folder.rglob("*.py"):
        if any(part in SKIP_DIRS or part.startswith(".") for part in f.relative_to(folder).parts[:-1]):
            continue
        out.append(f)
        if len(out) >= limit:
            break
    return out


def detect_tools(folder: Path) -> dict[str, str]:
    """Best guess at the agent's tools: public functions and methods in files named tools*.py."""
    tools: dict[str, str] = {}
    for f in _python_files(folder):
        if not f.stem.startswith("tools"):
            continue
        try:
            tree = ast.parse(f.read_text(encoding="utf-8", errors="replace"))
        except SyntaxError:
            continue
        for node in ast.walk(tree):
            if not isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
                continue
            if node.name.startswith("_") or node.name in NOT_TOOLS or any(isinstance(d, ast.Name) and d.id == "property" for d in node.decorator_list):
                continue
            doc = (ast.get_docstring(node) or "").strip().split("\n\n")[0].replace("\n", " ")
            tools.setdefault(node.name, doc or f"TODO: describe what {node.name} does and returns.")
    return tools


def adapter_info(folder: Path) -> dict[str, Any] | None:
    """The adapter that lets Downshift run this agent's own code, if the folder has one."""
    if not has_adapter(folder):
        return None
    try:
        cfg = load_agent_config(folder)
    except Exception as e:
        return {"error": f"downshift.yaml: {e}"}
    py = cfg.get("python") or "python"
    return {"entry": cfg["entry"], "python": cfg.get("python"), "tasks": cfg["tasks"], "harness": cfg["harness"], "python_cmd": py}


def record_command(folder: Path, agent_id: str, adapter: dict[str, Any] | None, record_script: str | None) -> str | None:
    if adapter and not adapter.get("error"):
        return f"cd {shlex.quote(str(folder))}\n{adapter['python_cmd']} -m downshift.runner record --project {agent_id}"
    if record_script:
        return f"cd {shlex.quote(str(folder))}\nuv run python {record_script} --project {agent_id}"
    return None


def adapter_default_harness(folder: Path, timeout: float = 60.0) -> str:
    """Ask the agent's adapter for its default harness, in the agent's own Python (not imported here)."""
    info = adapter_info(folder) or {}
    py = info.get("python")
    python = str((folder / py) if py and not Path(py).is_absolute() else (py or sys.executable))
    proc = subprocess.run([python, "-m", "downshift.runner", "init-harness", "--stdout", "--folder", str(folder)], cwd=str(folder), capture_output=True, text=True, timeout=timeout)
    if proc.returncode != 0:
        raise FolderError(f"the adapter could not produce a harness: {(proc.stderr or proc.stdout).strip()[-400:]}")
    return proc.stdout


def inspect_folder(root: Path, raw: str) -> dict[str, Any]:
    folder = resolve_inside(root, raw)
    if not folder.exists():
        raise FolderError(f"{folder} does not exist")
    if not folder.is_dir():
        raise FolderError(f"{folder} is not a folder")
    harness_path = folder / HARNESS_FILE
    harness_yaml = harness_path.read_text(encoding="utf-8", errors="replace") if harness_path.is_file() else None
    harness_info = validate_yaml(harness_yaml) if harness_yaml is not None else None
    questions = next((q for q in QUESTION_FILES if (folder / q).is_file()), None)
    record = next((r for r in RECORD_SCRIPTS if (folder / r).is_file()), None)
    py = _python_files(folder)
    uses_sdk = any("downshift" in f.read_text(encoding="utf-8", errors="replace") for f in py[:80])
    name = (harness_info or {}).get("name") or slug(folder.name)
    adapter = adapter_info(folder)
    if adapter and not adapter.get("error"):
        questions = adapter["tasks"] if (folder / adapter["tasks"]).is_file() else questions
    tools = {k: "" for k in (harness_info or {}).get("tools") or []} if (harness_info or {}).get("ok") else detect_tools(folder)
    return {
        "path": str(folder), "name": name, "suggested_id": slug(name),
        "description": _readme_summary(folder), "harness_yaml": harness_yaml, "harness": harness_info,
        "questions_file": questions, "record_script": record, "python_files": len(py), "uses_sdk": uses_sdk or bool(adapter),
        "tools": tools, "adapter": adapter, "record_command": record_command(folder, slug(name), adapter, record),
    }


def validate_yaml(text: str) -> dict[str, Any]:
    try:
        h = Harness.from_yaml(text)
        h.validate_models(default_table())
    except HarnessError as e:
        return {"ok": False, "error": str(e)}
    return {"ok": True, "name": h.name, "runtime": h.runtime, "fingerprint": h.fingerprint(), "models_used": h.models_used(), "steps": [s.id for s in h.steps if s.enabled], "tools": list(h.tools)}


def draft_harness(name: str, description: str, tools: dict[str, str], model: str = "nemotron-3-ultra") -> str:
    """A starting harness in the shape the SDK runs: plan, search (tool loop), synthesize."""
    tool_specs = tools or {
        "web_search": "Search the web. Returns results with a title, URL and a short snippet.",
        "read_page": "Fetch the readable text of a page by URL.",
    }
    data = {
        "name": slug(name),
        "version": 1,
        "description": description or f"{name}: describe in one sentence what the agent does.",
        "defaults": {"model": model, "temperature": 0.2, "max_tokens": 2000},
        "system_prompt": "You are a careful assistant. Use your tools to gather evidence before answering.\n\nRules:\n- Base every claim on what the tools returned.\n- Be concise and precise. If the evidence does not settle the question, say so.\n",
        "tools": {k: {"description": v} for k, v in tool_specs.items()},
        "steps": [
            {"id": "plan", "kind": "plan", "max_tokens": 1200, "prompt": 'Question: {question}\n\nWrite 1 to 3 search queries that together would answer the question.\nRespond with JSON only, in this shape:\n{"queries": ["..."], "notes": "what a complete answer needs to cover"}\n'},
            {"id": "search", "kind": "search", "max_tool_calls": 6, "prompt": "Question: {question}\nSuggested queries: {queries}\n\nUse the tools to find relevant sources and confirm key facts.\nStop when you have enough evidence, then reply with a short note on what you found.\n"},
            {"id": "synthesize", "kind": "synthesize", "max_tokens": 3000, "prompt": 'Question: {question}\n\nEvidence:\n{evidence}\n\nWrite the answer in 2 to 6 sentences. Support claims with inline [n] markers.\nFinish with a "Sources:" section listing the URLs you cited, one per line.\n'},
        ],
    }
    return Harness.from_dict(data).to_yaml()


def write_harness(folder: Path, text: str, *, overwrite: bool) -> dict[str, Any]:
    info = validate_yaml(text)
    if not info["ok"]:
        raise HarnessError(info["error"])
    target = folder / HARNESS_FILE
    if target.exists() and not overwrite:
        raise FolderError(f"{target} already exists")
    target.write_text(text if text.endswith("\n") else text + "\n", encoding="utf-8")
    return {**info, "path": str(target)}
