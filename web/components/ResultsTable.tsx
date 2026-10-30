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
        </tr>
      </thead>
      <tbody>
        <tr>
          <td>
            <div className="opt">
              <span className="swatch ring" />
              <div>
                <div className="name">Baseline</div>
                <div className="models">N3 Ultra · every step</div>
              </div>
            </div>
          </td>
          <td className="num">
            {pct(baseline.success_rate)}
            <div className="delta flat">reference</div>
          </td>
          <td className="num">
            {baseline.quality ?? "–"}
            <div className="delta flat">n={baseline.n}</div>
          </td>
          <td className="num">{money(baseline.cost_per_run)}</td>
          <td className="num">{seconds(baseline.latency_ms)}</td>
        </tr>
        {rows.map((r) => (
          <tr key={r.key}>
            <td>
              <div className="opt">
                <span className="swatch" style={{ background: seriesColor(r.key) }} />
                <div>
                  <div className="name">
                    <Link href={`/optimizations/${optimizationId}/options/${r.key}`}>{r.label}</Link>
                  </div>
                  <div className="models">
                    {r.models_used.map(shortModel).join(" + ")}
                    {r.key === recommended && (
                      <>
                        {" "}
                        <span className="tag">Recommended</span>
                      </>
                    )}
                    {!r.meets_bar && (
                      <>
                        {" "}
                        <span className="tag soft">{r.verdict === "inconclusive" ? "Inconclusive" : "Below the bar"}</span>
                      </>
                    )}
                  </div>
                </div>
              </div>
            </td>
            <td className="num">
              {pct(r.metrics.success_rate)}
              <div>
                <Delta v={r.deltas.success_rate_pp} upGood suffix=" pp" />
              </div>
              {r.stats && (
                <div className="delta flat" title="Held-out tasks × trials; 95% Wilson interval on pooled trials; paired difference against the baseline on the same tasks with a 90% bootstrap interval">
                  {r.stats.n_tasks}×{r.stats.trials}
                  {r.stats.success_ci95[0] != null ? ` · CI ${r.stats.success_ci95[0]}–${r.stats.success_ci95[1]}%` : ""}
                  {r.stats.trials > 1 && r.stats.passk != null ? ` · pass^k ${r.stats.passk}%` : ""}
                  {r.stats.delta_vs_baseline ? ` · Δ ${signed(r.stats.delta_vs_baseline.pp, 1, " pp")} [${signed(r.stats.delta_vs_baseline.ci90[0], 1)}, ${signed(r.stats.delta_vs_baseline.ci90[1], 1)}]` : ""}
                  {r.stats.delta_vs_swap ? ` · vs swap ${signed(r.stats.delta_vs_swap.pp, 1, " pp")} (${r.stats.vs_swap})` : ""}
                </div>
              )}
            </td>
            <td className="num">
              {r.metrics.quality ?? "–"}
              <div>
                <Delta v={r.deltas.quality_pts} upGood digits={1} />
              </div>
            </td>
            <td className="num">
              {money(r.metrics.cost_per_run)}
              <div>
                <Delta v={r.deltas.cost_pct} upGood={false} suffix="%" />
              </div>
            </td>
            <td className="num">
              {seconds(r.metrics.latency_ms)}
              <div>
                <Delta v={r.deltas.latency_pct} upGood={false} suffix="%" />
              </div>
            </td>
          </tr>
        ))}
      </tbody>
    </table>
  );
}
