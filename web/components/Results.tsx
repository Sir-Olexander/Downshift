import Link from "next/link";
import { AnalysisPanel } from "@/components/AnalysisPanel";
import { CostQualityChart, type ChartPoint } from "@/components/CostQualityChart";
import { Hero } from "@/components/Hero";
import { MethodStrip } from "@/components/MethodStrip";
import { ResultsTable } from "@/components/ResultsTable";
import type { Optimization } from "@/lib/api";
import { seriesColor, when } from "@/lib/format";

export function Results({ opt }: { opt: Optimization }) {
  const s = opt.summary!;
  const rec = s.headline.recommended;
  const points: ChartPoint[] = [
    { key: "baseline", label: "Baseline (Ultra)", cost: s.baseline.cost_per_run ?? 0, quality: s.baseline.quality ?? 0, success: s.baseline.success_rate, baseline: true },
    ...s.options.map((o) => ({ key: o.key, label: o.label, cost: o.metrics.cost_per_run ?? 0, quality: o.metrics.quality ?? 0, success: o.metrics.success_rate, recommended: o.key === rec, meets: o.meets_bar })),
  ];
  return (
    <>
      <Hero opt={opt} summary={s} />
      <section className="section">
        <div className="section-head">
          <h2>Cost against quality</h2>
          <p>
            {opt.project_id} · optimization {opt.id} · finished {when(opt.finished_at)}
            {opt.source === "seed" ? " · precomputed" : ""}
          </p>
        </div>
        <div className="grid-2">
          <div className="card">
            <CostQualityChart points={points} />
            <div className="legend" aria-label="Legend">
              {points.map((p) => (
                <span key={p.key}>
                  <span className={`swatch ${p.baseline ? "ring" : ""}`} style={p.baseline ? undefined : { background: seriesColor(p.key) }} />
                  {p.label}
                </span>
              ))}
            </div>
          </div>
          <div className="card" style={{ overflow: "auto" }}>
            <ResultsTable baseline={s.baseline} rows={s.options} recommended={rec} optimizationId={opt.id} />
            <div className="small muted" style={{ padding: "10px 20px 14px" }}>
              Quality is the judge&apos;s mean rubric score; success needs a sourced, error-free answer the judge rated correct. Open an option to see its harness diff and every replayed run.
            </div>
          </div>
        </div>
      </section>
      <section className="section">
        <MethodStrip summary={s} />
      </section>
      <section className="section">
        <div className="section-head">
          <h2>Why the cheaper models land where they do</h2>
          <p>
            <Link href={`/optimizations/${opt.id}/options/${rec ?? s.options[0]?.key ?? "baseline"}`}>Open the {rec ? "recommended" : "best"} option →</Link>
          </p>
        </div>
        <AnalysisPanel summary={s} />
      </section>
    </>
  );
}
