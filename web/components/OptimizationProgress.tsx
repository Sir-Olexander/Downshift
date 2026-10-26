"use client";

import { useRouter } from "next/navigation";
import { useEffect, useRef, useState } from "react";
import type { OptEvent, Optimization } from "@/lib/api";
import { clock } from "@/lib/format";

export function OptimizationProgress({ initial, initialEvents }: { initial: Optimization; initialEvents: OptEvent[] }) {
  const router = useRouter();
  const [opt, setOpt] = useState(initial);
  const [events, setEvents] = useState(initialEvents);
  const lastId = useRef(initialEvents.length ? initialEvents[initialEvents.length - 1].id : 0);

  useEffect(() => {
    let stop = false;
    async function tick() {
      try {
        const [o, ev] = await Promise.all([
          fetch(`/api/v1/optimizations/${initial.id}`).then((r) => r.json() as Promise<Optimization>),
          fetch(`/api/v1/optimizations/${initial.id}/events?after=${lastId.current}`).then((r) => r.json() as Promise<OptEvent[]>),
        ]);
        if (stop) return;
        if (ev.length) {
          lastId.current = ev[ev.length - 1].id;
          setEvents((prev) => [...prev, ...ev]);
        }
        setOpt(o);
        if (o.status === "done" || o.status === "failed") {
          router.refresh();
          return;
        }
      } catch {
        /* keep polling */
      }
      if (!stop) setTimeout(tick, 2500);
    }
    const t = setTimeout(tick, 2500);
    return () => {
      stop = true;
      clearTimeout(t);
    };
  }, [initial.id, router]);

  const p = opt.progress;
  return (
    <div className="stack" style={{ gap: 20 }}>
      <div className="card progress">
        <div className="row">
          <span className="dot-live" />
          <span className="eyebrow">{opt.status === "queued" ? "Queued" : "Optimizing"}</span>
          <span className="spacer" />
          <span className="small muted mono">{opt.id}</span>
        </div>
        <div className="phase" style={{ marginTop: 10 }}>
          {p?.detail || p?.phase || "Starting"}
        </div>
        <div className="meter" aria-label={`${p?.percent ?? 0}% complete`}>
          <i style={{ width: `${p?.percent ?? 0}%` }} />
        </div>
        <div className="small sub">
          {Math.round(p?.percent ?? 0)}% · phase {p?.phase || "queued"} · results are reported on the held-out set only
        </div>
      </div>
      <div className="card card-pad">
        <div className="eyebrow" style={{ marginBottom: 10 }}>
          Live log
        </div>
        <div className="log">
          {events.map((e) => (
            <div className="e" key={e.id}>
              <span className="ts">{clock(e.ts)}</span>
              <span className={e.level === "warn" ? "warn" : e.level === "error" ? "error" : ""}>
                {e.phase && <span className="ph">[{e.phase}]</span>}
                {e.message}
              </span>
            </div>
          ))}
          {!events.length && <div className="muted">Waiting for the first event…</div>}
        </div>
      </div>
    </div>
  );
}
