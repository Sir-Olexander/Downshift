import { Onboarding } from "@/components/Onboarding";
import { ApiDown } from "@/components/States";
import { Foot, TopBar } from "@/components/TopBar";
import { api, type Agent } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function NewAgent({ searchParams }: { searchParams: Promise<{ agent?: string }> }) {
  const { agent: agentId } = await searchParams;
  let health;
  let agent: Agent | null = null;
  try {
    health = await api.health();
    if (agentId) agent = await api.agent(agentId);
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
      <TopBar crumbs={[{ label: "Agents", href: "/agents" }, { label: agent ? agent.name : "Add agent" }]} projectId={agent?.id} active="agents" />
      <section className="page-head">
        <div>
          <div className="eyebrow">{agent ? "Finish setting up" : "Add an agent"}</div>
          <h1>{agent ? agent.name : "Connect your agent"}</h1>
          <p className="lede">Three steps: point Downshift at the folder, give the agent a harness.yaml, and record a few baseline runs on its current model.</p>
        </div>
      </section>
      <section className="section" style={{ marginTop: 28 }}>
        {health?.allow_fs && health.agents_root ? (
          <Onboarding root={health.agents_root} initialAgent={agent?.registered ? agent : null} />
        ) : (
          <div className="card empty">
            <h2>Folder access is off on this server</h2>
            <p className="sub">Agents are added from folders on the machine that runs the API. Set <span className="kbd">DOWNSHIFT_ALLOW_FS=true</span> on a local API to use this screen.</p>
          </div>
        )}
      </section>
      <Foot />
    </main>
  );
}
