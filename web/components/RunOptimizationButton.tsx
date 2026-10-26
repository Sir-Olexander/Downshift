"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";

export function RunOptimizationButton({ projectId }: { projectId: string }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [msg, setMsg] = useState<string | null>(null);

  async function start() {
    setBusy(true);
    setMsg(null);
    try {
      const res = await fetch("/api/v1/optimizations", { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify({ project_id: projectId }) });
      const data = await res.json().catch(() => ({}));
      if (res.status === 202 && data.id) {
        router.push(`/optimizations/${data.id}`);
        return;
      }
      setMsg(typeof data.detail === "string" ? data.detail : `Could not start (${res.status}).`);
    } catch (e) {
      setMsg(`Could not reach the API: ${(e as Error).message}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <span className="row" style={{ gap: 8 }}>
      {msg && <span className="small sub">{msg}</span>}
      <button className="btn small" onClick={start} disabled={busy} title="Runs a small, rate-limited live optimization">
        {busy ? "Starting…" : "Run optimization"}
      </button>
    </span>
  );
}
