import Link from "next/link";
import type { Optimization, Summary } from "@/lib/api";
import { OpenPRButton } from "@/components/OpenPRButton";
import { pct } from "@/lib/format";

function Headline({ text }: { text: string }) {
  const parts = text.split("→");
  if (parts.length === 1) return <>{text}</>;
  return (
    <>
      {parts.map((p, i) => (
        <span key={i}>
          {i > 0 && <span className="arrow">→</span>}
          {p.trim()}
        </span>
      ))}
    </>
  );
}

export function Hero({ opt, summary }: { opt: Optimization; summary: Summary }) {
  const rec = summary.headline.recommended;
  const best = rec ?? [...summary.options].sort((a, b) => (b.metrics.quality ?? 0) - (a.metrics.quality ?? 0))[0]?.key ?? null;
  const row = summary.options.find((o) => o.key === best);
  return (
    <section className="hero">
      <div className="eyebrow">Result on {summary.split.test} held-out runs</div>
      <h1 style={{ marginTop: 10 }}>
        <Headline text={summary.headline.text} />
      </h1>
      <p className="verdict">{summary.headline.verdict}</p>
      {row && (
        <div className="actions">
          <OpenPRButton optimizationId={opt.id} optionKey={row.key} label={row.label} />
          <Link className="btn secondary" href={`/optimizations/${opt.id}/options/${row.key}`}>
            See the harness diff
          </Link>
          <span className="btn-note">
            {rec ? "Recommended:" : "Best attempt:"} {row.label} · success {pct(row.metrics.success_rate)} vs {pct(summary.baseline.success_rate)}
          </span>
        </div>
      )}
      <div className="meta">
        <span>Judge: {summary.judge.model}, blind pairwise</span>
        <span>Optimized on {summary.split.optimization} runs, tested on {summary.split.test} it never saw</span>
        <span>Spent ${summary.spent_usd.toFixed(2)} on this optimization</span>
      </div>
    </section>
  );
}
