"""Write the latest optimization's results into the README (between the results markers).

    uv run python -m app.report readme            # update README.md in place
    uv run python -m app.report markdown [id]     # print the markdown only
"""

from __future__ import annotations

import re
import sys
from typing import Any

from .db import Database
from .github_pr import results_table
from .settings import REPO_DIR, Settings

START = "<!-- results:start -->"
END = "<!-- results:end -->"


def results_markdown(opt: dict[str, Any], options: list[dict[str, Any]]) -> str:
    s = opt.get("summary_json") or {}
    head = s.get("headline") or {}
    rec_key = head.get("recommended")
    lines = [
        START,
        f"**{head.get('text', '')}** · {head.get('verdict', '')}",
        "",
        results_table(s, rec_key or ""),
        "",
        f"Held-out test set: {s.get('split', {}).get('test')} runs the optimizer never saw ({s.get('split', {}).get('optimization')} runs were used to optimize). "
        f"Judge: {s.get('judge', {}).get('model')}, blind pairwise in random order. Models served via {'Ollama Cloud' if s.get('provider') == 'ollama' else s.get('provider')}, "
        f"search via {s.get('search_provider')}. Optimization spend: ${float(s.get('spent_usd') or 0):.2f}.",
        "",
    ]
    notes = s.get("notes") or []
    if notes:
        lines.append("What held up and what fell short:")
        lines.extend(f"- {n}" for n in notes)
        lines.append("")
    per_step = (s.get("analysis") or {}).get("per_step") or {}
    if per_step:
        lines.append(f"Step analysis by {s.get('analysis', {}).get('model')} (share of optimization runs where the step needed a strong model):")
        lines.extend(f"- `{step}` ({d.get('kind')}): {d.get('needs_strong_model_pct')}%" for step, d in per_step.items())
        lines.append("")
    for o in options:
        if o["key"] == "baseline" or not o.get("harness_json"):
            continue
        cl = (o["harness_json"].get("changelog") or [])[:4]
        if cl:
            lines.append(f"{o['label']} harness changes: " + " · ".join(cl))
    lines.append("")
    lines.append(f"Optimization id `{opt['id']}`; open it in the UI for the harness diffs and every replayed run.")
    lines.append(END)
    return "\n".join(lines)


def main(argv: list[str]) -> int:
    settings = Settings.from_env()
    db = Database(settings.db_path)
    cmd = argv[1] if len(argv) > 1 else "markdown"
    opt_id = argv[2] if len(argv) > 2 else None
    opt = db.get_optimization(opt_id) if opt_id else next((o for o in db.list_optimizations(limit=50) if o["status"] == "done"), None)
    if not opt or opt.get("status") != "done":
        print("no completed optimization found", file=sys.stderr)
        return 1
    md = results_markdown(opt, db.list_options(opt["id"]))
    if cmd == "markdown":
        print(md)
        return 0
    if cmd == "readme":
        readme = REPO_DIR / "README.md"
        text = readme.read_text(encoding="utf-8")
        if START in text and END in text:
            text = re.sub(re.escape(START) + r".*?" + re.escape(END), lambda _m: md, text, flags=re.S)
        elif "RESULTS_PLACEHOLDER" in text:
            text = text.replace("RESULTS_PLACEHOLDER", md)
        else:
            print("README has no results markers", file=sys.stderr)
            return 1
        readme.write_text(text, encoding="utf-8")
        print(f"updated {readme}")
        return 0
    print(__doc__)
    return 2


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
