"""Open a pull request on the demo agent repo with the new harness.yaml and a results table."""

from __future__ import annotations

import base64
import subprocess
from typing import Any

import httpx

from downshift import Harness

from .settings import Settings

API = "https://api.github.com"


def github_token(settings: Settings) -> str | None:
    if settings.github_token:
        return settings.github_token
    try:  # local convenience: reuse the gh CLI login
        out = subprocess.run(["gh", "auth", "token"], capture_output=True, text=True, timeout=5)
        tok = out.stdout.strip()
        return tok or None
    except Exception:
        return None


def _fmt_money(x: Any) -> str:
    return "n/a" if x is None else f"${float(x):.4f}"


def _fmt_pct(x: Any, signed: bool = True) -> str:
    if x is None:
        return "n/a"
    return f"{float(x):+.0f}%" if signed else f"{float(x):.0f}%"


def results_table(summary: dict[str, Any], chosen_key: str) -> str:
    base = summary.get("baseline") or {}
    lines = [
        "| Option | Task success | Quality (0-100) | Cost / run | Latency | vs baseline |",
        "|---|---|---|---|---|---|",
        f"| Baseline (Nemotron 3 Ultra) | {_fmt_pct(base.get('success_rate'), False)} | {base.get('quality')} | {_fmt_money(base.get('cost_per_run'))} | {int((base.get('latency_ms') or 0)/1000)} s | — |",
    ]
    for r in summary.get("options") or []:
        m, d = r.get("metrics") or {}, r.get("deltas") or {}
        mark = " **(this PR)**" if r.get("key") == chosen_key else ""
        lines.append(
            f"| {r.get('label')}{mark} | {_fmt_pct(m.get('success_rate'), False)} | {m.get('quality')} | {_fmt_money(m.get('cost_per_run'))} | {int((m.get('latency_ms') or 0)/1000)} s | "
            f"success {d.get('success_rate_pp', 0):+.0f} pp, quality {d.get('quality_pts', 0):+.0f}, cost {_fmt_pct(d.get('cost_pct'))} |"
        )
    return "\n".join(lines)


def pr_payload(option: dict[str, Any], optimization: dict[str, Any], settings: Settings) -> dict[str, Any]:
    summary = optimization.get("summary_json") or {}
    key = option["key"]
    row = next((r for r in summary.get("options") or [] if r.get("key") == key), None)
    d = (row or {}).get("deltas") or {}
    m = (row or {}).get("metrics") or {}
    base = summary.get("baseline") or {}
    label = option.get("label", key)
    harness = option.get("harness_json") or {}
    try:
        models_used = ", ".join(Harness.from_dict(harness).models_used())
    except Exception:
        models_used = harness.get("defaults", {}).get("model", "")
    branch = f"downshift/{key}-{optimization['id'].split('_')[-1][:6]}"
    cost_txt = f"cost {abs(d.get('cost_pct') or 0):.0f}% {'lower' if (d.get('cost_pct') or 0) <= 0 else 'higher'}"
    title = f"Run the research agent on {label}: {cost_txt}, task success {base.get('success_rate', 0):.0f}% → {m.get('success_rate', 0):.0f}%"
    changelog = "\n".join(f"- {c}" for c in (harness.get("changelog") or [])) or "- (no changelog recorded)"
    results_url = f"{settings.public_web_url.rstrip('/')}/optimizations/{optimization['id']}"
    body = f"""## What this changes

This PR replaces `{settings.harness_path}` with a version tuned for **{label}** (models: {models_used}).
No code changes: the agent loads the harness at runtime.

{changelog}

## Results on the held-out test set

{results_table(summary, key)}

Numbers come from the {summary.get('split', {}).get('test', '?')} held-out runs the optimizer never saw ({summary.get('split', {}).get('optimization', '?')} other runs were used to optimize). Each replay was scored with automatic checks (answer produced, sources listed, sources drawn from the evidence, no errors) and a blind pairwise judge on {summary.get('judge', {}).get('model', 'Nemotron 3 Ultra')} (rubric: correct, complete, supported; random A/B order). Costs use Nebius Token Factory list prices applied to recorded token counts.

{(summary.get('headline') or {}).get('verdict', '')}

Full results, harness diff and run timelines: {results_url}

_Opened by Downshift._
"""
    return {
        "repo": settings.github_repo,
        "base": settings.github_base,
        "branch": branch,
        "path": settings.harness_path,
        "title": title,
        "body": body,
        "content": option.get("harness_yaml") or "",
        "commit_message": f"Tune harness for {label} (Downshift optimization {optimization['id']})",
    }


def open_pr(payload: dict[str, Any], settings: Settings) -> dict[str, Any]:
    token = github_token(settings)
    repo = payload.get("repo")
    if not token or not repo:
        missing = [n for n, v in (("GITHUB_TOKEN (or a gh login)", token), ("GITHUB_REPO", repo)) if not v]
        return {"dry_run": True, "url": None, "reason": "Not configured: " + ", ".join(missing), **payload}
    h = {"Authorization": f"Bearer {token}", "Accept": "application/vnd.github+json", "X-GitHub-Api-Version": "2022-11-28"}
    with httpx.Client(base_url=API, headers=h, timeout=30) as gh:
        ref = gh.get(f"/repos/{repo}/git/ref/heads/{payload['base']}")
        ref.raise_for_status()
        base_sha = ref.json()["object"]["sha"]
        r = gh.post(f"/repos/{repo}/git/refs", json={"ref": f"refs/heads/{payload['branch']}", "sha": base_sha})
        if r.status_code not in (201, 422):  # 422: branch exists already
            r.raise_for_status()
        existing = gh.get(f"/repos/{repo}/contents/{payload['path']}", params={"ref": payload["branch"]})
        body: dict[str, Any] = {"message": payload["commit_message"], "content": base64.b64encode(payload["content"].encode("utf-8")).decode("ascii"), "branch": payload["branch"]}
        if existing.status_code == 200:
            body["sha"] = existing.json()["sha"]
        put = gh.put(f"/repos/{repo}/contents/{payload['path']}", json=body)
        put.raise_for_status()
        pr = gh.post(f"/repos/{repo}/pulls", json={"title": payload["title"], "head": payload["branch"], "base": payload["base"], "body": payload["body"]})
        if pr.status_code == 422:  # PR for this branch exists: find it
            owner = repo.split("/")[0]
            lst = gh.get(f"/repos/{repo}/pulls", params={"head": f"{owner}:{payload['branch']}", "state": "open"})
            lst.raise_for_status()
            items = lst.json()
            if items:
                return {"dry_run": False, "url": items[0]["html_url"], "number": items[0]["number"], "existing": True, **payload}
        pr.raise_for_status()
        data = pr.json()
        return {"dry_run": False, "url": data["html_url"], "number": data["number"], **payload}
