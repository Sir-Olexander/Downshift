"use client";

import { useState } from "react";

type PRResult = { dry_run: boolean; url: string | null; number?: number; reason?: string; title?: string; branch?: string; body?: string; repo?: string | null; path?: string; existing?: boolean; detail?: string };

export function OpenPRButton({ optimizationId, optionKey, label, existingUrl }: { optimizationId: string; optionKey: string; label: string; existingUrl?: string | null }) {
  const [busy, setBusy] = useState(false);
  const [result, setResult] = useState<PRResult | null>(existingUrl ? { dry_run: false, url: existingUrl } : null);
  const [error, setError] = useState<string | null>(null);

  async function call(dryRun: boolean) {
    setBusy(true);
    setError(null);
    try {
      const res = await fetch(`/api/v1/optimizations/${optimizationId}/options/${optionKey}/pr`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ dry_run: dryRun }) });
      const data = (await res.json().catch(() => ({}))) as PRResult;
      if (!res.ok) {
        setError(typeof data.detail === "string" ? data.detail : `GitHub request failed (${res.status}).`);
        return;
      }
      setResult(data);
    } catch (e) {
      setError(`Could not reach the API: ${(e as Error).message}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="stack" style={{ gap: 10 }}>
      <div className="row" style={{ gap: 8 }}>
        {result?.url ? (
          <a className="btn" href={result.url} target="_blank" rel="noreferrer">
            View pull request{result.number ? ` #${result.number}` : ""} ↗
          </a>
        ) : (
          <button className="btn" onClick={() => call(false)} disabled={busy}>
            {busy ? "Opening…" : `Open pull request for ${label}`}
          </button>
        )}
        <button className="btn secondary" onClick={() => call(true)} disabled={busy}>
          Preview PR
        </button>
      </div>
      {error && <div className="callout err">{error}</div>}
      {result && !result.url && (
        <div className="card card-pad pr-preview stack">
          <div className="small">
            {result.dry_run && result.reason && result.reason !== "preview" ? (
              <>
                <b>Not opened.</b> {result.reason}. Set <span className="kbd">GITHUB_REPO</span> (owner/name) and a token on the API server, then try again. This is what would be opened:
              </>
            ) : (
              <b>Preview of the pull request</b>
            )}
          </div>
          <div className="small">
            <b>{result.title}</b>
            <br />
            <span className="sub">
              branch <span className="kbd">{result.branch}</span> → <span className="kbd">{result.repo || "(repo not set)"}</span>, file <span className="kbd">{result.path}</span>
            </span>
          </div>
          <pre>{result.body}</pre>
        </div>
      )}
    </div>
  );
}
