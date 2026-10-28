import { notFound } from "next/navigation";
import { OptimizationProgress } from "@/components/OptimizationProgress";
import { Results } from "@/components/Results";
import { ApiDown } from "@/components/States";
import { Foot, TopBar } from "@/components/TopBar";
import { api } from "@/lib/api";
import { clock } from "@/lib/format";

export const dynamic = "force-dynamic";

export default async function OptimizationPage({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  let opt;
  let events;
  try {
    opt = await api.optimization(id);
    if (!opt) notFound();
    events = (await api.events(opt.id)) || [];
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
  return (
    <main className="shell">
      <TopBar crumbs={[{ label: "History", href: "/optimizations" }, { label: opt.id }]} projectId={opt.project_id} active={opt.status === "done" ? "results" : "run"} />
      {opt.status === "done" && opt.summary ? (
        <Results opt={opt} />
      ) : opt.status === "failed" ? (
        <section className="section stack">
          <div className="card empty">
            <h2>This optimization failed</h2>
            <p className="sub">{opt.error}</p>
          </div>
          <div className="card card-pad log">
            {events.map((e) => (
              <div className="e" key={e.id}>
                <span className="ts">{clock(e.ts)}</span>
                <span className={e.level === "error" ? "error" : ""}>{e.message}</span>
              </div>
            ))}
          </div>
        </section>
      ) : (
        <section className="section">
          <OptimizationProgress initial={opt} initialEvents={events} />
        </section>
      )}
      <Foot />
    </main>
  );
}
