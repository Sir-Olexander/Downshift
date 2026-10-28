import Link from "next/link";
import { ApiDown } from "@/components/States";
import { Foot, TopBar } from "@/components/TopBar";
import { api } from "@/lib/api";
import { when } from "@/lib/format";

export const dynamic = "force-dynamic";

export default async function History() {
  let list;
  try {
    list = (await api.optimizations()) || [];
  } catch (e) {
    return (
      <main className="shell">
        <TopBar />
        <div className="section">
          <ApiDown message={(e as Error).message} />
        </div>
      </main>
    );
  }
  return (
    <main className="shell">
      <TopBar crumbs={[{ label: "History" }]} active="history" />
      <section className="section">
        <div className="section-head">
          <h2>Optimizations</h2>
          <p>{list.length} total</p>
        </div>
        <div className="card list">
          {list.map((o) => (
            <Link key={o.id} href={`/optimizations/${o.id}`} className="item">
              <div>
                <div>
                  <b>{o.summary?.headline.text || (o.status === "running" ? o.progress?.detail || "Running" : o.status === "failed" ? "Failed" : "Queued")}</b>
                </div>
                <div className="small muted mono">
                  {o.id} · {o.project_id} · {when(o.created_at)} · {o.source}
                </div>
              </div>
              <span className={`pill ${o.status === "done" ? "" : o.status === "failed" ? "bad" : "ink"}`}>{o.status}</span>
            </Link>
          ))}
          {!list.length && <div className="empty">Nothing yet.</div>}
        </div>
      </section>
      <Foot />
    </main>
  );
}
