"""How recorded runs reach the backend: HTTP with a local spool, or plain files when offline."""

from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any

import httpx


class HttpTransport:
    """POST runs to the Downshift backend; spool to disk if it is unreachable."""

    def __init__(self, endpoint: str, api_key: str, *, spool_dir: str | os.PathLike | None = None, timeout: float = 20.0):
        self.endpoint = endpoint.rstrip("/")
        self.api_key = api_key
        self.spool_dir = Path(spool_dir or os.environ.get("DOWNSHIFT_SPOOL_DIR") or ".downshift/spool")
        self.timeout = timeout

    def send(self, record: dict[str, Any]) -> None:
        try:
            r = httpx.post(
                f"{self.endpoint}/v1/runs",
                json=record,
                headers={"Authorization": f"Bearer {self.api_key}"},
                timeout=self.timeout,
            )
            r.raise_for_status()
        except Exception as e:
            self._spool(record)
            print(f"[downshift] backend unreachable ({e}); run {record.get('id')} spooled to {self.spool_dir}")

    def flush(self) -> int:
        """Resend spooled runs. Returns how many were delivered."""
        sent = 0
        if not self.spool_dir.exists():
            return 0
        for p in sorted(self.spool_dir.glob("*.json")):
            try:
                rec = json.loads(p.read_text(encoding="utf-8"))
                r = httpx.post(f"{self.endpoint}/v1/runs", json=rec, headers={"Authorization": f"Bearer {self.api_key}"}, timeout=self.timeout)
                r.raise_for_status()
                p.unlink()
                sent += 1
            except Exception:
                break
        return sent

    def _spool(self, record: dict[str, Any]) -> None:
        self.spool_dir.mkdir(parents=True, exist_ok=True)
        name = f"{int(time.time()*1000)}-{record.get('id','run')}.json"
        (self.spool_dir / name).write_text(json.dumps(record, ensure_ascii=False), encoding="utf-8")


class FileTransport:
    """Write each run as a JSON file (offline mode, tests, or batch import)."""

    def __init__(self, directory: str | os.PathLike):
        self.directory = Path(directory)

    def send(self, record: dict[str, Any]) -> None:
        self.directory.mkdir(parents=True, exist_ok=True)
        (self.directory / f"{record['id']}.json").write_text(json.dumps(record, ensure_ascii=False, indent=1), encoding="utf-8")


class MemoryTransport:
    def __init__(self) -> None:
        self.records: list[dict[str, Any]] = []

    def send(self, record: dict[str, Any]) -> None:
        self.records.append(record)


class NullTransport:
    def send(self, record: dict[str, Any]) -> None:
        return None
