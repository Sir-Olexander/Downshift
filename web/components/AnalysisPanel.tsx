import type { Summary } from "@/lib/api";

const ORDER = ["easy", "medium", "hard"] as const;
const ORD_COLOR: Record<string, string> = { easy: "var(--ord-1)", medium: "var(--ord-2)", hard: "var(--ord-3)" };

export function AnalysisPanel({ summary }: { summary: Summary }) {
  const steps = Object.entries(summary.analysis.per_step || {});
  return (
    <div className="grid-2">
      <div className="card card-pad">
        <div className="eyebrow">Step analysis · {summary.analysis.model}</div>
        <p className="sub small" style={{ margin: "6px 0 14px" }}>
          Nano labelled every step of the optimization runs by difficulty and whether it needs a strong model. This is what decides which steps can move.
        </p>
        <div className="steps">
          {steps.map(([id, s]) => {
            const total = ORDER.reduce((acc, k) => acc + (s.difficulty[k] || 0), 0) || 1;
            return (
              <div className="step-row" key={id}>
                <div>
                  <span className="name">{id}</span>
                  <span className="kind">{s.kind}</span>
                </div>
                <div>
                  <div className="ord" aria-label={ORDER.map((k) => `${k} ${s.difficulty[k] || 0}%`).join(", ")}>
                    {ORDER.map((k) => (
                      <i key={k} style={{ width: `${((s.difficulty[k] || 0) / total) * 100}%`, background: ORD_COLOR[k] }} title={`${k} ${s.difficulty[k] || 0}%`} />
                    ))}
                  </div>
                </div>
                <div className="small sub" style={{ textAlign: "right" }}>
                  {s.needs_strong_model_pct}% need Ultra
                </div>
              </div>
            );
          })}
        </div>
        <div className="ord-key">
          {ORDER.map((k) => (
            <span key={k}>
              <i style={{ background: ORD_COLOR[k] }} />
              {k}
            </span>
          ))}
        </div>
      </div>
      <div className="card card-pad">
        <div className="eyebrow">What held up, what fell short</div>
        <ul className="notes" style={{ marginTop: 12 }}>
          {summary.notes.map((n, i) => {
            const ok = n.includes("within the bar");
            return (
              <li key={i}>
                <div className="note">
                  <span className={`mark ${ok ? "ok" : "no"}`}>{ok ? "✓" : "✕"}</span>
                  <span>{n}</span>
                </div>
              </li>
            );
          })}
          {summary.analysis.recommendations.map((r, i) => (
            <li key={`r${i}`}>
              <div className="note">
                <span className="mark" style={{ background: "var(--surface-2)", color: "var(--ink-2)" }}>→</span>
                <span className="sub">{r}</span>
              </div>
            </li>
          ))}
        </ul>
      </div>
    </div>
  );
}
