import type { RunEvent, RunRecord } from "@/lib/api";
import { money, seconds, shortModel } from "@/lib/format";

function clip(s: string | null | undefined, n: number): string {
  if (!s) return "";
  return s.length > n ? s.slice(0, n) + " …" : s;
}

function Event({ e }: { e: RunEvent }) {
  if (e.type === "model_call") {
    const tcs = e.response?.tool_calls || [];
    return (
      <div className="ev">
        <span className="ic m">M</span>
        <div>
          <div className="line">
            <span className="name">{e.step}</span>
            <span className="badge">{shortModel(e.model)}</span>
            <span className="mono">
              {e.tokens_in}→{e.tokens_out} tok · {seconds(e.latency_ms)} · {money(e.cost_usd)}
            </span>
            {e.params?.reasoning != null && <span className="mono">reasoning {String(e.params.reasoning)}</span>}
            {e.error && <span className="pill bad">error</span>}
          </div>
          <details>
            <summary>{tcs.length ? `asked for ${tcs.map((t) => t.name).join(", ")}` : clip(e.response?.content, 90) || "(empty)"}</summary>
            {tcs.length > 0 && <pre>{tcs.map((t) => `${t.name}(${JSON.stringify(t.arguments)})`).join("\n")}</pre>}
            {e.response?.content && <pre>{clip(e.response.content, 2500)}</pre>}
            {e.response?.reasoning && <pre className="muted">{clip(e.response.reasoning, 800)}</pre>}
            {e.error && <pre>{e.error}</pre>}
          </details>
        </div>
      </div>
    );
  }
  const args = JSON.stringify(e.args);
  return (
    <div className="ev">
      <span className="ic t">T</span>
      <div>
        <div className="line">
          <span className="name">{e.name}</span>
          <span className={`badge ${e.source === "recorded" ? "rec" : ""}`}>{e.source === "recorded" ? "recorded result" : "live call"}</span>
          <span className="mono">{seconds(e.latency_ms)}</span>
          {e.error && <span className="pill bad">error</span>}
        </div>
        <details>
          <summary>{clip(args, 100)}</summary>
          <pre>{clip(JSON.stringify(e.result, null, 1), 2500)}</pre>
          {e.matched_args && <pre className="muted">matched recorded call ({e.matched_args.match}, score {e.matched_args.score}): {JSON.stringify(e.matched_args.args)}</pre>}
        </details>
      </div>
    </div>
  );
}

export function RunTimeline({ record, title }: { record: RunRecord; title: string }) {
  const t = record.totals;
  return (
    <div className="card" style={{ overflow: "hidden" }}>
      <div className="totals">
        <b style={{ color: "var(--ink)" }}>{title}</b>
        <span>{t.model_calls} model calls</span>
        <span>
          {t.tool_calls} tool calls{t.tool_calls_recorded ? ` (${t.tool_calls_recorded} recorded)` : ""}
        </span>
        <span>
          {t.tokens_in}→{t.tokens_out} tok
        </span>
        <span>{seconds(t.latency_ms)}</span>
        <span>{money(t.cost_usd)}</span>
      </div>
      <div className="timeline">
        {record.events.map((e) => (
          <Event key={e.index} e={e} />
        ))}
      </div>
    </div>
  );
}

export function AnswerCard({ record, title, colorKey, verdict }: { record: RunRecord | null; title: string; colorKey: string; verdict?: string }) {
  const answer = record?.output?.answer || record?.error || "(no answer)";
  const parts = answer.split(/(https?:\/\/[^\s)\]]+)/g);
  return (
    <div className="card answer">
      <div className="head">
        <span className="row" style={{ gap: 8 }}>
          <span className="swatch" style={{ background: `var(--s-${colorKey})` }} />
          <b>{title}</b>
        </span>
        {verdict && <span className="pill ink">{verdict}</span>}
      </div>
      <div className="body">
        {parts.map((p, i) =>
          /^https?:\/\//.test(p) ? (
            <a key={i} href={p} target="_blank" rel="noreferrer">
              {p}
            </a>
          ) : (
            <span key={i}>{p}</span>
          ),
        )}
      </div>
    </div>
  );
}
