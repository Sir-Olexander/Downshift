import { redirect } from "next/navigation";
import { Results } from "@/components/Results";
import { ApiDown, NoResultsYet } from "@/components/States";
import { Foot, TopBar } from "@/components/TopBar";
import { api } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function Home() {
  let latest = null;
  let runCount = 0;
  try {
    latest = await api.latest();
    if (!latest) {
      const all = (await api.optimizations()) || [];
      const active = all.find((o) => o.status === "running" || o.status === "queued");
      if (active) redirect(`/optimizations/${active.id}`);
      const projects = (await api.projects()) || [];
      runCount = projects.reduce((n, p) => n + p.run_count, 0);
    }
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
      <TopBar projectId={latest?.project_id ?? "research-agent"} />
      {latest ? (
        <Results opt={latest} />
      ) : (
        <div className="section">
          <NoResultsYet runCount={runCount} />
        </div>
      )}
      <Foot />
    </main>
  );
}
