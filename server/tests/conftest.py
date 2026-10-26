import os
import sys
from pathlib import Path

import pytest

SERVER_DIR = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(SERVER_DIR))


@pytest.fixture()
def client(tmp_path, monkeypatch):
    """A TestClient on a fresh temp database, no seed, no provider needed."""
    monkeypatch.setenv("DOWNSHIFT_DB_PATH", str(tmp_path / "t.sqlite3"))
    monkeypatch.setenv("DOWNSHIFT_SEED_PATH", str(tmp_path / "missing.json.gz"))
    monkeypatch.setenv("DOWNSHIFT_API_KEYS", "test-key")
    monkeypatch.setenv("DOWNSHIFT_PROVIDER", "ollama")
    for m in [m for m in list(sys.modules) if m == "app" or m.startswith("app.")]:
        del sys.modules[m]
    from fastapi.testclient import TestClient
    import app.main as main

    with TestClient(main.app) as c:
        yield c
