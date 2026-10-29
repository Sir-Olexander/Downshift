import Link from "next/link";
import { notFound } from "next/navigation";
import { HarnessDiff, StepModelsTable } from "@/components/HarnessDiff";
import { OpenPRButton } from "@/components/OpenPRButton";
import { ApiDown } from "@/components/States";
import { Foot, TopBar } from "@/components/TopBar";
import { api } from "@/lib/api";
import { deltaClass, money, pct, seconds, seriesColor, signed } from "@/lib/format";

export const dynamic = "force-dynamic";

export default async function OptionPage({ params }: { params: Promise<{ id: string; key: string }> }) {
  const { id, key } = await params;
  let o;
  try {
    o = await api.option(id, key);
    if (!o) notFound();
  } catch (e) {
    if ((e as { digest?: string }).digest?.startsWith("NEXT_")) throw e;
    return (
      <main className="shell">
        <TopBar />
        <div className="section">
          <ApiDown message={(e as Error).message} />
        </div>
      </main>
    );
  }
  const m = o.metrics;
  const t = m?.test;
  const b = m?.baseline_on_test;
  const d = m?.deltas;
  const test = o.replays.filter((r) => r.split === "test");
  const isBaseline = o.key === "baseline";
  const existingPr = o.prs.find((p) => p.url)?.url ?? null;
  return (
    <main className="shell">
      <TopBar crumbs={[{ label: "Results", href: `/optimizations/${o.optimization.id}` }, { label: o.label }]} projectId={o.optimization.project_id} active="results" />
      <section className="section">
        <div className="row" style={{ gap: 10 }}>
          <span className={`swatch ${isBaseline ? "ring" : ""}`} style={isBaseline ? undefined : { background: seriesColor(o.key) }} />
          <h2>{o.label}</h2>
          {m && !isBaseline && <span className={`pill ${m.meets_bar ? "good" : "warn"}`}>{m.meets_bar ? "within the quality bar" : "below the quality bar"}</span>}
          {o.key === o.optimization.summary?.headline.recommended && <span className="tag">Recommended</span>}
        </div>
        <p className="sub" style={{ marginTop: 8, maxWidth: "70ch" }}>
          {o.rationale || o.harness?.description}
        </p>
        {t && b && d && (
          <div className="metric-row" style={{ marginTop: 18 }}>
            {[
              { k: "Task success", v: pct(t.success_rate), d: `${signed(d.success_rate_pp)} pp vs ${pct(b.success_rate)}`, c: deltaClass(d.success_rate_pp, true) },
              { k: "Quality", v: String(t.quality ?? "–"), d: `${signed(d.quality_pts)} vs ${b.quality}`, c: deltaClass(d.quality_pts, true) },
              { k: "Cost per run", v: money(t.cost_per_run), d: `${signed(d.cost_pct, 0, "%")} vs ${money(b.cost_per_run)}`, c: deltaClass(d.cost_pct, false) },
              { k: "Latency", v: seconds(t.latency_ms), d: `${signed(d.latency_pct, 0, "%")} vs ${seconds(b.latency_ms)}`, c: deltaClass(d.latency_pct, false) },
              { k: "Judge preferred it", v: pct(t.win_rate), d: `${pct(t.tie_rate)} ties · n=${t.n}`, c: "flat" },
            ].map((x) => (
              <div className="card metric" key={x.k}>
                <div className="k">{x.k}</div>
                <div className="v">{x.v}</div>
                <div className={`d delta ${x.c}`}>{x.d}</div>
              </div>
            ))}
          </div>
        )}
        {!isBaseline && (
          <div style={{ marginTop: 18 }}>
            <OpenPRButton optimizationId={o.optimization.id} optionKey={o.key} label={o.label} existingUrl={existingPr} />
          </div>
        )}
      </section>

      {o.harness && (
        <section className="section">
          <div className="section-head">
            <h2>Model per step</h2>
            <p>{o.models_used.join(", ")}</p>
          </div>
          <div className="card" style={{ overflow: "auto" }}>
            <StepModelsTable before={isBaseline ? null : o.baseline_harness} after={o.harness} />
          </div>
        </section>
      )}

      {!isBaseline && o.harness_yaml && o.baseline_harness_yaml && (
        <section className="section">
          <div className="section-head">
            <h2>Harness diff</h2>
            <p>demo_agent/harness.yaml · the whole behaviour change, reviewable</p>
          </div>
          {o.changelog.length > 0 && (
            <div className="card card-pad" style={{ marginBottom: 14 }}>
              <div className="eyebrow">Changelog written by the optimizer</div>
              <ul style={{ margin: "8px 0 0", paddingLeft: 18 }} className="sub small">
                {o.changelog.map((c, i) => (
                  <li key={i}>{c}</li>
                ))}
              </ul>
            </div>
          )}
          <HarnessDiff left={o.baseline_harness_yaml} right={o.harness_yaml} leftTitle="Baseline harness" rightTitle={`${o.label} harness`} />
        </section>
      )}

      {o.rounds.length > 0 && (
        <section className="section">
          <div className="section-head">
            <h2>Optimization rounds</h2>
            <p>on the optimization sample only, never the test set</p>
          </div>
          <div className="card card-pad rounds">
            {o.rounds.map((r) => (
              <div className="r" key={r.round}>
                <div className="n">
                  {r.round === 0 ? "Model swap" : `Round ${r.round}`}
                  {m?.best_round === r.round && (
                    <div>
                      <span className="tag soft">kept</span>
                    </div>
                  )}
                </div>
                <div className="cl">
                  <div className="mono small" style={{ marginBottom: 4 }}>
                    {r.models_used.join(", ")} · {r.fingerprint}
                  </div>
                  {r.changelog.slice(0, 4).map((c, i) => (
                    <div key={i}>· {c}</div>
                  ))}
                  {r.worst_examples?.[0] && (
                    <div className="muted small" style={{ marginTop: 6 }}>
                      Worst: &ldquo;{r.worst_examples[0].question}&rdquo; — {r.worst_examples[0].reason || r.worst_examples[0].checks}
                    </div>
                  )}
                </div>
                <div className="m">
                  success {pct(r.metrics.success_rate)} ({pct(r.baseline_metrics.success_rate)})
                  <br />
                  quality {r.metrics.quality} ({r.baseline_metrics.quality})
                  <br />
                  {money(r.metrics.cost_per_run)} ({money(r.baseline_metrics.cost_per_run)})
                </div>
              </div>
            ))}
          </div>
        </section>
      )}

      {test.length > 0 && (
        <section className="section">
          <div className="section-head">
            <h2>Held-out runs</h2>
            <p>{test.length} replays · click one to compare it with the baseline run</p>
          </div>
          <div className="card" style={{ overflow: "auto" }}>
            <table className="replays">
              <thead>
                <tr>
                  <th>Question</th>
                  <th>Judge</th>
                  <th className="num">Quality</th>
                  <th>Checks</th>
                  <th className="num">Cost</th>
                  <th className="num">Latency</th>
                  <th className="num">Tools</th>
                </tr>
              </thead>
              <tbody>
                {test.map((r) => {
                  const cm = r.metrics?.candidate;
                  const ck = r.checks?.candidate;
                  return (
                    <tr key={r.id}>
                      <td>
                        <Link href={`/optimizations/${o.optimization.id}/options/${o.key}/runs/${r.task_id}`} className="q" title={r.question || r.task_id}>
                          {r.question || r.task_id}
                        </Link>
                        <span className="small muted mono">{r.task_id}</span>
                      </td>
                      <td className="pref">
                        {r.judge?.method === "ground_truth" ? (
                          r.judge.candidate?.passed ? <span className="pill good">correct</span> : <span className="pill bad">wrong</span>
                        ) : r.judge?.preferred === "candidate" ? <span className="pill good">preferred</span> : r.judge?.preferred === "tie" ? <span className="pill">tie</span> : r.judge?.preferred === "baseline" ? <span className="pill bad">baseline better</span> : <span className="pill">no verdict</span>}
                      </td>
                      <td className="num">{cm?.quality ?? "–"}</td>
                      <td>
                        {ck &&
                          (
                            [
                              ["ground_truth", "G"],
                              ["answer_produced", "A"],
                              ["has_sources", "S"],
                              ["sources_from_evidence", "E"],
                              ["no_errors", "✓"],
                            ] as const
                          ).filter(([k]) => ck[k] !== undefined).map(([k, lbl]) => (
                            <span key={k} className={`check ${ck[k] ? "ok" : "no"}`} title={k.replace(/_/g, " ")}>
                              {lbl}
                            </span>
                          ))}
                      </td>
                      <td className="num">{money(cm?.cost_usd)}</td>
                      <td className="num">{seconds(cm?.latency_ms)}</td>
                      <td className="num">
                        {cm?.tool_calls ?? 0}
                        {cm?.tool_calls_live ? <span className="muted"> ({cm.tool_calls_live} live)</span> : null}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
            <div className="small muted" style={{ padding: "10px 12px 14px" }}>
              Checks: G matches the task's correct answer · A answer produced · S sources listed · E every cited source came from the evidence · ✓ no errors (only the checks that apply to this agent are shown).
            </div>
          </div>
        </section>
      )}
      <Foot />
    </main>
  );
}
