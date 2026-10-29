import { MIN_RUNS, type Agent } from "@/lib/api";

export type AgentState = { label: string; tone: "" | "good" | "bad" | "warn" | "ink"; setupDone: boolean };

export function agentState(a: Agent): AgentState {
  if (a.registered && !a.folder_exists) return { label: "Folder missing", tone: "bad", setupDone: false };
  if (a.registered && !a.harness_on_disk) return { label: "Needs harness.yaml", tone: "warn", setupDone: false };
  if (a.ok_task_count < MIN_RUNS) return { label: "Needs baseline runs", tone: "warn", setupDone: false };
  if (a.active) return { label: a.active.status === "queued" ? "Queued" : "Optimizing", tone: "ink", setupDone: true };
  if (a.latest) return { label: "Has results", tone: "good", setupDone: true };
  return { label: "Ready to run", tone: "", setupDone: true };
}

export function agentHref(a: Agent): string {
  return agentState(a).setupDone ? `/agents/${a.id}` : `/agents/new?agent=${encodeURIComponent(a.id)}`;
}
