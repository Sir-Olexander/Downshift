import { notFound } from "next/navigation";
import { AnswerCard, RunTimeline } from "@/components/RunTimeline";
import { ApiDown } from "@/components/States";
import { Foot, TopBar } from "@/components/TopBar";
import { api } from "@/lib/api";

export const dynamic = "force-dynamic";

export default async function RunPage({ params, searchParams }: { params: Promise<{ id: string; key: string; taskId: string }>; searchParams: Promise<{ split?: string }> }) {
  const { id, key, taskId } = await params;
  const { split } = await searchParams;
  let r;
  try {
    r = await api.run(id, key, taskId, split || "test");
    if (!r) notFound();
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
  const j = r.judge;
  const verdict = j?.preferred === "candidate" ? "judge preferred this one" : j?.preferred === "tie" ? "judge: tie" : j?.preferred === "baseline" ? "judge preferred this one" : undefined;
  return (
    <main className="shell">
      <TopBar crumbs={[{ label: "Results", href: `/optimizations/${id}` }, { label: r.option.label, href: `/optimizations/${id}/options/${key}` }, { label: r.task_id }]} projectId={r.candidate.project} active="results" />
      <section className="section">
        <div className="eyebrow">
          {r.split === "test" ? "Held-out run" : `Optimization sample, round ${r.round}`} · {r.task_id}
        </div>
        <h2 style={{ marginTop: 8, fontSize: 24, maxWidth: "40ch" }}>{r.question}</h2>
      </section>
      <section className="section compare">
        <AnswerCard record={r.baseline} title="Baseline · Nemotron 3 Ultra" colorKey="baseline" verdict={j?.preferred === "baseline" ? verdict : undefined} />
        <AnswerCard record={r.candidate} title={r.option.label} colorKey={r.option.key} verdict={j?.preferred === "candidate" || j?.preferred === "tie" ? verdict : undefined} />
      </section>
      {j && (
        <section className="section">
          <div className="card judge">
            <div className="eyebrow">Judge · {j.model || "Nemotron 3 Ultra"} · answers shown {j.order === "candidate_first" ? "candidate first" : "baseline first"}, blind</div>
            <p style={{ marginTop: 8 }}>{j.reason || j.error}</p>
            <div className="scores">
              <div className="sc">
                baseline: correct {j.baseline?.correct ?? "–"} · complete {j.baseline?.complete ?? "–"} · supported {j.baseline?.supported ?? "–"} → {j.baseline_quality ?? "–"}
              </div>
              <div className="sc">
                {r.option.label}: correct {j.candidate?.correct ?? "–"} · complete {j.candidate?.complete ?? "–"} · supported {j.candidate?.supported ?? "–"} → {j.candidate_quality ?? "–"}
              </div>
            </div>
          </div>
        </section>
      )}
      <section className="section compare">
        {r.baseline ? <RunTimeline record={r.baseline} title="Baseline timeline" /> : <div className="card empty">Baseline run not found</div>}
        <RunTimeline record={r.candidate} title={`${r.option.label} timeline`} />
      </section>
      <Foot />
    </main>
  );
}
