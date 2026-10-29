"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { call } from "@/lib/api";

export function RemoveAgentButton({ id, name }: { id: string; name: string }) {
  const router = useRouter();
  const [busy, setBusy] = useState(false);

  async function remove() {
    if (!window.confirm(`Remove ${name} from Downshift?\n\nThe folder and its harness.yaml stay on disk, and recorded runs and results are kept.`)) return;
    setBusy(true);
    try {
      await call(`/v1/agents/${encodeURIComponent(id)}`, { method: "DELETE" });
      router.refresh();
    } catch (e) {
      window.alert((e as Error).message);
    } finally {
      setBusy(false);
    }
  }

  return (
    <button className="link-btn" onClick={remove} disabled={busy} aria-label={`Remove ${name}`}>
      {busy ? "Removing…" : "Remove"}
    </button>
  );
}
