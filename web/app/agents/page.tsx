import Link from "next/link";
import { agentHref, agentState } from "@/components/AgentStatus";
import { RemoveAgentButton } from "@/components/RemoveAgentButton";
import { ApiDown } from "@/components/States";
import { Foot, TopBar } from "@/components/TopBar";
import { api, MIN_RUNS } from "@/lib/api";
import { shortModel, when } from "@/lib/format";

export const dynamic = "force-dynamic";

export default async function Agents() {
  let agents;
  try {
    agents = (await api.agents()) || [];
  } catch (e) {
    return (
      <main className="shell">
        <TopBar active="agents" />
        <div className="section">
          <ApiDown message={(e as Error).message} />
        </div>
      </main>
    );
  }
  return (
    <main className="shell">
      <TopBar active="agents" projectId={agents[0]?.id} />
      <section className="page-head">
        <div>
          <div className="eyebrow">Agents</div>
          <h1>The agents you are testing</h1>
          <p className="lede">Each agent is a folder with a harness.yaml and some recorded runs. Downshift replays those runs on cheaper Nemotron models.</p>
        </div>
        <Link href="/agents/new" className="btn">
          Add agent
        </Link>
      </section>
      <section className="section">
        <div className="card list agents">
          {agents.map((a) => {
            const st = agentState(a);
            return (
              <div key={a.id} className="item">
                <div style={{ minWidth: 0 }}>
                  <Link href={agentHref(a)} className="name">
                    {a.name}
                  </Link>
                  <div className="small muted mono path" title={a.path ?? undefined}>
                    {a.path}
                  </div>
                  <div className="small sub" style={{ marginTop: 2 }}>
                    {a.ok_task_count} of {MIN_RUNS}+ baseline runs recorded
                    {a.models_used.length ? ` · ${a.models_used.map(shortModel).join(", ")}` : ""}
                    {a.latest ? ` · last result ${when(a.latest.finished_at)}` : ""}
                  </div>
                </div>
                <div className="stats">
                  <span className={`pill ${st.tone}`}>{st.label}</span>
                </div>
                <div className="row" style={{ gap: 14 }}>
                  <Link href={agentHref(a)} className="btn secondary small">
                    {st.setupDone ? "Open" : "Continue setup"}
                  </Link>
                  <RemoveAgentButton id={a.id} name={a.name} />
                </div>
              </div>
            );
          })}
          {!agents.length && (
            <div className="empty">
              <h2>No agents yet</h2>
              <p className="sub">Add the folder of an agent that uses the Downshift SDK to get started.</p>
              <p style={{ marginTop: 16 }}>
                <Link href="/agents/new" className="btn">
                  Add agent
                </Link>
              </p>
            </div>
          )}
        </div>
      </section>
      <Foot />
    </main>
  );
}
