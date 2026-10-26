"""Export the database to the seed file (and import it): `python -m app.seed export|import [path]`."""

from __future__ import annotations

import sys

from .db import Database
from .settings import Settings


def main(argv: list[str]) -> int:
    settings = Settings.from_env()
    cmd = argv[1] if len(argv) > 1 else "export"
    path = argv[2] if len(argv) > 2 else str(settings.seed_path)
    db = Database(settings.db_path)
    if cmd == "export":
        db.export_to_file(path)
        print(f"exported {settings.db_path} -> {path}")
        return 0
    if cmd == "import":
        counts = db.import_from_file(path)
        print(f"imported {path} -> {settings.db_path}: {counts}")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
