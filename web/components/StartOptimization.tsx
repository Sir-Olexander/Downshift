"use client";

import { useRouter } from "next/navigation";
import { useState } from "react";
import { call } from "@/lib/api";
import { seriesColor } from "@/lib/format";

const TARGETS = [
  { key: "super", label: "Nemotron 3 Super", note: "Every step on Super, harness rewritten for it" },
  { key: "nano", label: "Nemotron 3 Nano", note: "Every step on Nano, the cheapest option" },
  { key: "mix", label: "Per-step mix", note: "The cheapest model that can handle each step" },
];

export function StartOptimization({ projectId, canStart, blockedReason, demoMode }: { projectId: string; canStart: boolean; blockedReason?: string | null; demoMode: boolean }) {
  const router = useRouter();
  const [targets, setTargets] = useState<string[]>(TARGETS.map((t) => t.key));
  const [rounds, setRounds] = useState(2);
  const [sample, setSample] = useState(10);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);

  function toggle(key: string) {
    setTargets((cur) => (cur.includes(key) ? cur.filter((k) => k !== key) : TARGETS.map((t) => t.key).filter((k) => k === key || cur.includes(k))));
  }

  async function start() {
    setBusy(true);
    setError(null);
    try {
      await call("/v1/optimizations", { body: { project_id: projectId, targets, rounds, sample_size: sample } });
      router.refresh();
    } catch (e) {
      setError((e as Error).message);
      setBusy(false);
    }
  }

  return (
    <div className="card progress stack" style={{ gap: 18 }}>
      <div className="row">
        <span className="eyebrow">New optimization</span>
      </div>
      <div className="field">
        <span>Cheaper options to try</span>
        <div className="choices">
          {TARGETS.map((t) => {
            const on = targets.includes(t.key);
            return (
              <label key={t.key} className={`choice ${on ? "on" : ""}`}>
                <input type="checkbox" checked={on} onChange={() => toggle(t.key)} />
                <span>
                  <span className="t">
                    <span className="swatch" style={{ background: seriesColor(t.key) }} />
                    {t.label}
                  </span>
                  <span className="d" style={{ display: "block" }}>
                    {t.note}
                  </span>
                </span>
              </label>
            );
          })}
        </div>
      </div>
      <div className="form-grid">
        <label className="field">
          <span>Rounds per option</span>
          <select className="select" value={rounds} onChange={(e) => setRounds(Number(e.target.value))} disabled={demoMode}>
            {[1, 2, 3].map((n) => (
              <option key={n} value={n}>
                {n} {n === 1 ? "round" : "rounds"}
              </option>
            ))}
          </select>
        </label>
        <label className="field">
          <span>Runs replayed per round</span>
          <input className="input" type="number" min={3} max={25} value={sample} onChange={(e) => setSample(Math.max(3, Math.min(25, Number(e.target.value) || 3)))} disabled={demoMode} />
        </label>
      </div>
      {demoMode && <div className="callout small">Demo mode keeps live runs small: one round, up to 4 runs per round, 6 held-out runs and a $3 budget. Set DOWNSHIFT_DEMO_MODE=false on the API for a full optimization.</div>}
      {error && <div className="callout err">{error}</div>}
      <div className="row">
        <button className="btn" onClick={start} disabled={busy || !canStart || !targets.length}>
          {busy ? "Starting…" : "Start optimization"}
        </button>
        <span className="small sub">{blockedReason || "Each option: propose a harness, replay, score blind against the baseline, keep the best. Results use held-out runs only."}</span>
      </div>
    </div>
  );
}
