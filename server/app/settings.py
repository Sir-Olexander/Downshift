"""Server settings, from environment variables (a repo-root .env is loaded if present)."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path

from dotenv import load_dotenv

SERVER_DIR = Path(__file__).resolve().parents[1]
REPO_DIR = SERVER_DIR.parent


def _load_env() -> None:
    for candidate in (REPO_DIR / ".env", SERVER_DIR / ".env"):
        if candidate.exists():
            load_dotenv(candidate, override=False)
    load_dotenv(override=False)


def _bool(name: str, default: bool) -> bool:
    v = os.environ.get(name)
    if v is None or v == "":
        return default
    return v.strip().lower() in {"1", "true", "yes", "on"}


def _int(name: str, default: int) -> int:
    try:
        return int(os.environ.get(name, "") or default)
    except ValueError:
        return default


@dataclass
class Settings:
    data_dir: Path
    db_path: Path
    seed_path: Path
    api_keys: set[str]
    provider: str | None
    demo_mode: bool
    max_live_optimizations_per_hour: int
    cors_origins: list[str]
    # optimizer budget defaults
    opt_rounds: int
    opt_sample_size: int
    opt_concurrency: int
    test_fraction: float
    judge_model: str
    analysis_model: str
    rewrite_model: str
    # GitHub PR
    github_token: str | None
    github_repo: str | None
    github_base: str
    harness_path: str
    public_web_url: str
    targets: list[str] = field(default_factory=lambda: ["super", "nano", "mix"])

    @classmethod
    def from_env(cls) -> "Settings":
        _load_env()
        data_dir = Path(os.environ.get("DOWNSHIFT_DATA_DIR") or SERVER_DIR / "data")
        keys = {k.strip() for k in (os.environ.get("DOWNSHIFT_API_KEYS") or "ds_dev").split(",") if k.strip()}
        return cls(
            data_dir=data_dir,
            db_path=Path(os.environ.get("DOWNSHIFT_DB_PATH") or data_dir / "downshift.sqlite3"),
            seed_path=Path(os.environ.get("DOWNSHIFT_SEED_PATH") or SERVER_DIR / "seed" / "seed.json.gz"),
            api_keys=keys,
            provider=os.environ.get("DOWNSHIFT_PROVIDER") or None,
            demo_mode=_bool("DOWNSHIFT_DEMO_MODE", True),
            max_live_optimizations_per_hour=_int("DOWNSHIFT_MAX_LIVE_PER_HOUR", 2),
            cors_origins=[o.strip() for o in (os.environ.get("DOWNSHIFT_CORS_ORIGINS") or "http://localhost:3000").split(",") if o.strip()],
            opt_rounds=_int("DOWNSHIFT_OPT_ROUNDS", 2),
            opt_sample_size=_int("DOWNSHIFT_OPT_SAMPLE", 10),
            opt_concurrency=_int("DOWNSHIFT_OPT_CONCURRENCY", 4),
            test_fraction=float(os.environ.get("DOWNSHIFT_TEST_FRACTION") or 0.4),
            judge_model=os.environ.get("DOWNSHIFT_JUDGE_MODEL") or "nemotron-3-ultra",
            analysis_model=os.environ.get("DOWNSHIFT_ANALYSIS_MODEL") or "nemotron-3-nano",
            rewrite_model=os.environ.get("DOWNSHIFT_REWRITE_MODEL") or "nemotron-3-ultra",
            github_token=os.environ.get("GITHUB_TOKEN") or None,
            github_repo=os.environ.get("GITHUB_REPO") or None,
            github_base=os.environ.get("GITHUB_BASE_BRANCH") or "main",
            harness_path=os.environ.get("GITHUB_HARNESS_PATH") or "demo_agent/harness.yaml",
            public_web_url=os.environ.get("DOWNSHIFT_PUBLIC_WEB_URL") or "http://localhost:3000",
        )
