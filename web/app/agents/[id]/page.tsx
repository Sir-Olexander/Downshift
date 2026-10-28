import Link from "next/link";
import { notFound } from "next/navigation";
import { agentState } from "@/components/AgentStatus";
import { OptimizationProgress } from "@/components/OptimizationProgress";
import { StartOptimization } from "@/components/StartOptimization";
import { ApiDown } from "@/components/States";
import { Foot, TopBar } from "@/components/TopBar";
import { api, MIN_RUNS, type Health, type OptEvent, type Optimization } from "@/lib/api";
import { shortModel, when } from "@/lib/format";

export const dynamic = "force-dynamic";

export default async function RunAgent({ params }: { params: Promise<{ id: string }> }) {
  const { id } = await params;
  let agent;
  let health: Health | null = null;
  let active: Optimization | null = null;
  let events: OptEvent[] = [];
  try {
    agent = await api.agent(id);
    if (!agent) notFound();
    health = await api.health();
    if (agent.active) {
      active = await api.optimization(agent.active.id);
      events = (active && (await api.events(active.id))) || [];
    }
  } catch (e) {
    if ((e as { digest?: string }).digest?.startsWith("NEXT_")) throw e;
    return (
      <main className="shell">
        <TopBar active="run" projectId={id} />
        <div className="section">
          <ApiDown message={(e as Error).message} />
        </div>
      </main>
    );
  }
  const st = agentState(agent);
  const others = (health?.running ?? []).filter((r) => r !== active?.id);
  const blocked = agent.ok_task_count < MIN_RUNS ? `Needs at least ${MIN_RUNS} recorded runs (has ${agent.ok_task_count}).` : others.length ? "Another optimization is running; start this one when it finishes." : null;
  const history = agent.optimizations ?? [];

  return (
    <main className="shell">
      <TopBar crumbs={[{ label: "Agents", href: "/agents" }, { label: agent.name }]} projectId={agent.id} active="run" />
      <section className="page-head">
        <div style={{ minWidth: 0 }}>
          <div className="eyebrow">Run</div>
          <h1>{agent.name}</h1>
          <p className="lede">
            {agent.ok_task_count} baseline runs recorded
            {agent.models_used.length ? ` on ${agent.models_used.map(shortModel).join(", ")}` : ""}
            {agent.harness_fingerprint ? (
              <>
                {" "}
                · harness <span className="mono">{agent.harness_fingerprint}</span>
              </>
            ) : null}
          </p>
          {agent.path && <p className="small muted mono" style={{ marginTop: 4 }}>{agent.path}</p>}
        </div>
        <div className="row" style={{ gap: 8 }}>
          <span className={`pill ${st.tone}`}>{st.label}</span>
          {agent.registered && (
            <Link href={`/agents/new?agent=${encodeURIComponent(agent.id)}`} className="btn secondary small">
              Edit setup
            </Link>
          )}
        </div>
      </section>

      {!agent.registered && (
        <div className="section callout" style={{ marginTop: 20 }}>
          This agent has recorded runs but is not in your agents list. <Link href="/agents/new" style={{ textDecoration: "underline" }}>Add its folder</Link> to edit its harness from here.
        </div>
      )}

      <section className="section" style={{ marginTop: 28 }}>
        {active ? (
          <OptimizationProgress initial={active} initialEvents={events} />
        ) : (
          <StartOptimization projectId={agent.id} canStart={!blocked} blockedReason={blocked} demoMode={!!health?.demo_mode} />
        )}
      </section>

      {agent.latest?.summary && (
        <section className="section">
          <div className="section-head">
            <h2>Latest result</h2>
            <p>finished {when(agent.latest.finished_at)}</p>
          </div>
          <Link href={`/optimizations/${agent.latest.id}`} className="card card-pad row" style={{ textDecoration: "none" }}>
            <div style={{ minWidth: 0, flex: 1 }}>
              <div style={{ fontSize: 18, fontWeight: 600, letterSpacing: "-0.01em" }}>{agent.latest.summary.headline.text}</div>
              <div className="small sub" style={{ marginTop: 4 }}>
                {agent.latest.summary.headline.verdict}
              </div>
            </div>
            <span className="btn secondary small">View results →</span>
          </Link>
        </section>
      )}

      {history.length > 0 && (
        <section className="section">
          <div className="section-head">
            <h2>Past optimizations</h2>
            <p>{history.length} for this agent</p>
          </div>
          <div className="card list">
            {history.map((o) => (
              <Link key={o.id} href={`/optimizations/${o.id}`} className="item">
                <div>
                  <b>{o.summary?.headline.text || (o.status === "running" ? o.progress?.detail || "Running" : o.status === "failed" ? "Failed" : "Queued")}</b>
                  <div className="small muted mono">
                    {o.id} · {when(o.created_at)} · {o.source}
                  </div>
                </div>
                <span className={`pill ${o.status === "done" ? "" : o.status === "failed" ? "bad" : "ink"}`}>{o.status}</span>
              </Link>
            ))}
          </div>
        </section>
      )}
      <Foot />
    </main>
  );
}
