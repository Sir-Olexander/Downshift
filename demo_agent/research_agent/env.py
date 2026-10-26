"""Load the repo's .env (if present) so scripts work from any working directory."""

from __future__ import annotations

from pathlib import Path

from dotenv import load_dotenv


def load_env() -> Path | None:
    here = Path(__file__).resolve()
    for parent in [here.parent, *here.parents]:
        candidate = parent / ".env"
        if candidate.exists():
            load_dotenv(candidate, override=False)
            return candidate
    load_dotenv(override=False)
    return None
