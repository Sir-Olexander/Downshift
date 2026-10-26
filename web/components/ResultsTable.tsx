import Link from "next/link";
import type { Metrics, SummaryRow } from "@/lib/api";
import { deltaClass, money, pct, seconds, seriesColor, shortModel, signed } from "@/lib/format";

function Delta({ v, upGood, suffix, digits = 0 }: { v: number | null | undefined; upGood: boolean; suffix?: string; digits?: number }) {
  return <span className={`delta ${deltaClass(v, upGood)}`}>{signed(v, digits, suffix)}</span>;
}

export function ResultsTable({ baseline, rows, recommended, optimizationId }: { baseline: Metrics; rows: SummaryRow[]; recommended: string | null; optimizationId: string }) {
  return (
    <table className="results">
      <thead>
        <tr>
          <th>Option</th>
          <th className="num">Task success</th>
          <th className="num">Quality</th>
          <th className="num">Cost / run</th>
          <th className="num">Latency</th>
          <th>vs baseline</th>
        </tr>
      </thead>
      <tbody>
        <tr>
          <td>
            <div className="opt">
              <span className="swatch ring" />
              <div>
                <div className="name">Baseline</div>
                <div className="models">nemotron-3-ultra · every step</div>
              </div>
            </div>
          </td>
          <td className="num">{pct(baseline.success_rate)}</td>
          <td className="num">{baseline.quality ?? "–"}</td>
          <td className="num">{money(baseline.cost_per_run)}</td>
          <td className="num">{seconds(baseline.latency_ms)}</td>
          <td className="muted small">reference, n={baseline.n}</td>
        </tr>
        {rows.map((r) => (
          <tr key={r.key}>
            <td>
              <div className="opt">
                <span className="swatch" style={{ background: seriesColor(r.key) }} />
                <div>
                  <div className="name">
                    <Link href={`/optimizations/${optimizationId}/options/${r.key}`}>{r.label}</Link>
                    {r.key === recommended && (
                      <>
                        {" "}
                        <span className="tag">Recommended</span>
                      </>
                    )}
                    {!r.meets_bar && (
                      <>
                        {" "}
                        <span className="tag soft">Below the bar</span>
                      </>
                    )}
                  </div>
                  <div className="models">{r.models_used.map(shortModel).join(" + ")}</div>
                </div>
              </div>
            </td>
            <td className="num">{pct(r.metrics.success_rate)}</td>
            <td className="num">{r.metrics.quality ?? "–"}</td>
            <td className="num">{money(r.metrics.cost_per_run)}</td>
            <td className="num">{seconds(r.metrics.latency_ms)}</td>
            <td>
              <div className="row" style={{ gap: 10 }}>
                <Delta v={r.deltas.success_rate_pp} upGood suffix=" pp" />
                <Delta v={r.deltas.quality_pts} upGood suffix=" q" />
                <Delta v={r.deltas.cost_pct} upGood={false} suffix="% cost" />
                <Delta v={r.deltas.latency_pct} upGood={false} suffix="% time" />
              </div>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
