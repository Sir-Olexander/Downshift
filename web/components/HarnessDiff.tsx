import { diffLines } from "diff";
import type { Harness } from "@/lib/api";

type Row = { l: { n: number; t: string } | null; r: { n: number; t: string } | null; kind: "same" | "add" | "del" };

export function sideBySide(left: string, right: string): Row[] {
  const rows: Row[] = [];
  let ln = 0;
  let rn = 0;
  const changes = diffLines(left, right);
  const lines = (v: string) => v.replace(/\n$/, "").split("\n");
  let pendingDel: string[] = [];
  const flushDel = () => {
    for (const t of pendingDel) rows.push({ l: { n: ++ln, t }, r: null, kind: "del" });
    pendingDel = [];
  };
  for (const c of changes) {
    if (c.removed) {
      pendingDel.push(...lines(c.value));
      continue;
    }
    if (c.added) {
      const add = lines(c.value);
      const n = Math.max(add.length, pendingDel.length);
      for (let i = 0; i < n; i++) {
        const l = i < pendingDel.length ? { n: ++ln, t: pendingDel[i] } : null;
        const r = i < add.length ? { n: ++rn, t: add[i] } : null;
        rows.push({ l, r, kind: l && r ? "del" : l ? "del" : "add" });
      }
      pendingDel = [];
      continue;
    }
    flushDel();
    for (const t of lines(c.value)) rows.push({ l: { n: ++ln, t }, r: { n: ++rn, t }, kind: "same" });
  }
  flushDel();
  return rows;
}

export function HarnessDiff({ left, right, leftTitle, rightTitle }: { left: string; right: string; leftTitle: string; rightTitle: string }) {
  const rows = sideBySide(left, right);
  const changed = rows.filter((r) => r.kind !== "same").length;
  return (
    <div className="card" style={{ overflow: "hidden" }}>
      <div className="diff">
        <div className="col">
          <div className="col-head">
            <span>{leftTitle}</span>
            <span className="muted">before</span>
          </div>
          {rows.map((r, i) => (
            <div key={i} className={`ln ${r.l ? (r.kind === "same" ? "" : "del") : "pad"}`}>
              <span className="n">{r.l ? r.l.n : ""}</span>
              <pre>{r.l ? r.l.t : ""}</pre>
            </div>
          ))}
        </div>
        <div className="col">
          <div className="col-head">
            <span>{rightTitle}</span>
            <span className="muted">after · {changed} changed lines</span>
          </div>
          {rows.map((r, i) => (
            <div key={i} className={`ln ${r.r ? (r.kind === "same" ? "" : "add") : "pad"}`}>
              <span className="n">{r.r ? r.r.n : ""}</span>
              <pre>{r.r ? r.r.t : ""}</pre>
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}

export function StepModelsTable({ before, after }: { before: Harness | null; after: Harness }) {
  const prev = new Map((before?.steps || []).map((s) => [s.id, s]));
  const resolve = (h: Harness | null, s: { model?: string; reasoning?: string; max_tokens?: number; temperature?: number } | undefined) => ({
    model: s?.model || h?.defaults.model || "–",
    reasoning: s?.reasoning || h?.defaults.reasoning || "on",
    max_tokens: s?.max_tokens ?? h?.defaults.max_tokens ?? "–",
    temperature: s?.temperature ?? h?.defaults.temperature ?? "–",
  });
  const removed = (before?.steps || []).filter((s) => !after.steps.some((a) => a.id === s.id));
  return (
    <table className="models-table">
      <thead>
        <tr>
          <th>Step</th>
          <th>Kind</th>
          <th>Model before</th>
          <th>Model after</th>
          <th>Reasoning</th>
          <th className="num">Max tokens</th>
          <th className="num">Temp.</th>
        </tr>
      </thead>
      <tbody>
        {after.steps.map((s) => {
          const b = prev.get(s.id);
          const pb = b ? resolve(before, b) : null;
          const pa = resolve(after, s);
          return (
            <tr key={s.id} style={{ opacity: s.enabled === false ? 0.5 : 1 }}>
              <td>
                {s.id}
                {s.enabled === false && <span className="badge" style={{ marginLeft: 6 }}>disabled</span>}
              </td>
              <td>{s.kind}</td>
              <td>{pb ? pb.model : <span className="muted">new step</span>}</td>
              <td>
                <b>{pa.model}</b>
              </td>
              <td>
                {pb && pb.reasoning !== pa.reasoning ? (
                  <>
                    <span className="muted">{pb.reasoning} →</span> {pa.reasoning}
                  </>
                ) : (
                  pa.reasoning
                )}
              </td>
              <td className="num">{pa.max_tokens}</td>
              <td className="num">{pa.temperature}</td>
            </tr>
          );
        })}
        {removed.map((s) => (
          <tr key={`rm-${s.id}`} style={{ opacity: 0.6 }}>
            <td>{s.id}</td>
            <td>{s.kind}</td>
            <td>{resolve(before, s).model}</td>
            <td className="muted">removed</td>
            <td />
            <td />
            <td />
          </tr>
        ))}
      </tbody>
    </table>
  );
}
