// Typed client for the Downshift API. Server components call the API directly; client
// components go through the /api/* rewrite (see next.config.ts).

export const API_URL = process.env.API_URL || "http://localhost:8000";

export type Metrics = {
  n: number;
  n_judged?: number;
  n_comparisons?: number;
  success_rate: number | null;
  checks_pass_rate?: number | null;
  quality: number | null;
  cost_per_run: number | null;
  latency_ms: number | null;
  tokens_in?: number;
  tokens_out?: number;
  win_rate?: number | null;
  tie_rate?: number | null;
  live_tool_call_share?: number;
  errors?: number;
};
export type Deltas = { success_rate_pp: number | null; quality_pts: number | null; cost_pct: number | null; latency_pct: number | null };
export type OptionMetrics = { test: Metrics; baseline_on_test: Metrics; deltas: Deltas; meets_bar: boolean; best_round?: number; objective?: number; n_test: number };
export type WorstExample = { task_id: string; question: string; reason: string; checks: string; answer_excerpt: string };
export type Round = { round: number; fingerprint: string; models_used: string[]; metrics: Metrics; baseline_metrics: Metrics; objective: number; changelog: string[]; rationale: string; worst_examples: WorstExample[]; n: number };
export type OptionSummary = {
  id: string; key: string; label: string; target: string; status: string; position: number;
  metrics: OptionMetrics | null; rounds: Round[]; rationale: string | null; models_used: string[]; changelog: string[]; created_at: string;
};
export type PairedDelta = { n_tasks: number; pp: number; ci95: [number, number]; ci90: [number, number]; se_pp: number; mde_pp: number };
export type HoldoutStats = {
  n_tasks: number; trials: number; pass1: number | null; passk: number | null; success_ci95: [number | null, number | null]; margin_pp: number;
  delta_vs_baseline: PairedDelta | null; verdict: "non_inferior" | "inconclusive" | "inferior" | "unknown";
  swap_pass1?: number | null; delta_vs_swap?: PairedDelta | null; vs_swap?: "better" | "undecided" | "worse" | "unknown";
};
export type SummaryRow = { key: string; label: string; models_used: string[]; metrics: Metrics; deltas: Deltas; meets_bar: boolean; verdict?: string | null; stats?: HoldoutStats | null; option_id: string };
export type StepAnalysis = { n: number; kind: string; difficulty: Record<string, number>; needs_strong_model_pct: number; sample_reasons: string[] };
export type Summary = {
  headline: { text: string; verdict: string; recommended: string | null };
  baseline: Metrics;
  options: SummaryRow[];
  notes: string[];
  split: { optimization: number; test: number; test_fraction: number; note: string };
  spent_usd: number;
  budget: { rounds: number; sample_size: number; max_cost_usd: number };
  judge: { model: string | null; method: string };
  /** How runs were scored: the task's correct answer (ground_truth), the LLM judge, or both. */
  scoring?: "ground_truth" | "judge" | "mixed";
  runtime?: "research" | "custom";
  analysis: { model: string; recommendations: string[]; per_step: Record<string, StepAnalysis> };
  provider: string;
  search_provider: string;
  pricing_note: string;
};
export type Progress = { phase: string; percent: number; detail: string; updated_at?: string };
export type Optimization = {
  id: string; project_id: string; status: "queued" | "running" | "done" | "failed"; source: string;
  created_at: string; started_at: string | null; finished_at: string | null;
  config: Record<string, unknown> | null; split: { opt: string[]; test: string[]; seed: number; test_fraction: number } | null;
  progress: Progress | null; summary: Summary | null; error: string | null; options?: OptionSummary[];
};
export type OptEvent = { id: number; ts: string; level: string; phase: string; message: string; data: unknown };
export type Checks = { answer_produced: boolean; has_sources?: boolean; sources_from_evidence?: boolean; tools_used: boolean; no_errors: boolean; n_sources?: number; n_unknown_sources?: number; n_tool_calls: number; passed: boolean; ground_truth?: boolean };
export type GroundTruth = { passed: boolean; score: number; details: string };
export type Scores = { correct: number; complete: number; supported: number };
export type Judge = { method?: "ground_truth"; preferred: "candidate" | "baseline" | "tie" | null; reason: string; candidate: (Scores & Partial<GroundTruth>) | null; baseline: (Scores & Partial<GroundTruth>) | null; candidate_quality: number | null; baseline_quality: number | null; order?: string; error?: string; model?: string };
export type RunMetrics = { judged?: boolean; success: boolean; quality: number | null; checks_passed: boolean; cost_usd: number; latency_ms: number; tokens_in: number; tokens_out: number; model_calls: number; tool_calls: number; tool_calls_recorded: number; tool_calls_live: number; preferred?: string | null; status: string };
export type ReplayRow = { id: string; task_id: string; split: string; round: number; status: string; question: string | null; metrics: { candidate: RunMetrics; baseline: RunMetrics } | null; judge: Judge | null; checks: { candidate: Checks; baseline: Checks } | null };
export type HarnessStep = { id: string; kind: string; description?: string; prompt?: string; model?: string; temperature?: number; max_tokens?: number; reasoning?: string; max_tool_calls?: number; few_shot?: { input: string; output: string }[]; retry_on_fail?: boolean; enabled?: boolean };
export type Harness = { name: string; version: string | number; description?: string; runtime?: "research" | "custom"; contract?: string; defaults: { model: string; temperature?: number | null; max_tokens?: number | null; reasoning?: string }; system_prompt: string; tools: Record<string, { description: string }>; steps: HarnessStep[]; changelog?: string[] };
export type OptionDetail = OptionSummary & {
  harness: Harness | null; harness_yaml: string | null; baseline_harness_yaml: string | null; baseline_harness: Harness | null;
  optimization: Optimization; replays: ReplayRow[]; prs: { id: string; url: string | null; dry_run: boolean; created_at: string }[];
};
export type ToolCallReq = { id: string; name: string; arguments: Record<string, unknown>; raw_arguments: string };
export type ModelCallEvent = { type: "model_call"; index: number; step: string; ts: string; model: string; provider: string; provider_model: string; params: Record<string, unknown>; messages: { role: string; content: string | null; name?: string }[]; tools: string[]; response: { content: string; tool_calls: ToolCallReq[]; reasoning: string | null; finish_reason: string | null }; tokens_in: number; tokens_out: number; cost_usd: number | null; latency_ms: number; error: string | null };
export type ToolCallEvent = { type: "tool_call"; index: number; step: string | null; ts: string; name: string; args: Record<string, unknown>; result: unknown; latency_ms: number; source: "live" | "recorded"; matched_args: { args: Record<string, unknown>; score: number; match: string } | null; error: string | null };
export type RunEvent = ModelCallEvent | ToolCallEvent;
export type Totals = { model_calls: number; tool_calls: number; tool_calls_recorded: number; tool_calls_live: number; tokens_in: number; tokens_out: number; cost_usd: number; latency_ms: number; model_latency_ms: number; tool_latency_ms: number; wall_ms: number };
export type RunRecord = { id: string; project: string; task_id: string; input: string; harness: Harness; harness_fingerprint: string; started_at: string; ended_at: string | null; status: string; error: string | null; score?: GroundTruth | null; output: { answer: string; sources: string[]; evidence?: { title: string; url: string }[]; steps_run?: string[]; verify?: { ok: boolean; problems: string[] } | null } | null; events: RunEvent[]; totals: Totals; meta: Record<string, unknown> };
export type RunComparison = { task_id: string; split: string; round: number; question: string; baseline: RunRecord | null; candidate: RunRecord; judge: Judge | null; checks: { candidate: Checks; baseline: Checks } | null; metrics: { candidate: RunMetrics; baseline: RunMetrics } | null; option: OptionSummary; baseline_option: OptionSummary };
export type RunSummary = { id: string; project_id: string; task_id: string; input: string; status: string; harness_fingerprint: string; started_at: string; ended_at: string; cost_usd: number; latency_ms: number; tokens_in: number; tokens_out: number; tag: string | null; created_at: string };
export type Project = { id: string; name: string; created_at: string; harness: Harness | null; harness_yaml: string | null; harness_fingerprint: string | null; runs: RunSummary[]; optimizations: Optimization[] };
export type ProjectListItem = { id: string; name: string; created_at: string; harness_fingerprint: string | null; run_count: number; models_used: string[] };

export type Agent = {
  id: string; name: string; path: string | null; registered: boolean; created_at: string | null; folder_exists: boolean; harness_on_disk: boolean;
  harness_fingerprint: string | null; models_used: string[]; run_count: number; ok_task_count: number;
  active: Optimization | null; latest: Optimization | null; optimization_count: number; optimizations?: Optimization[];
};
export type HarnessCheck = { ok: true; name: string; runtime?: string; fingerprint: string; models_used: string[]; steps: string[]; tools: string[] } | { ok: false; error: string };
export type FolderInfo = {
  path: string; name: string; suggested_id: string; description: string; harness_yaml: string | null; harness: HarnessCheck | null;
  questions_file: string | null; record_script: string | null; python_files: number; uses_sdk: boolean; tools: Record<string, string>;
  /** Set when the folder has a Downshift adapter (downshift_agent.py): Downshift runs the agent's own code. */
  adapter?: { entry: string; python: string | null; tasks: string; harness: string; python_cmd: string; error?: string } | null;
  record_command?: string | null;
};
export type Browse = { path: string; parent: string | null; root: string; has_harness: boolean; dirs: { name: string; path: string; has_harness: boolean }[] };
export type Health = { ok: boolean; provider: string | null; demo_mode: boolean; running: string[]; allow_fs: boolean; agents_root: string | null };

/** The minimum the API asks for before it will start an optimization. */
export const MIN_RUNS = 4;

export class ApiError extends Error {
  constructor(public status: number, message: string) {
    super(message);
  }
}

async function get<T>(path: string): Promise<T | null> {
  let res: Response;
  try {
    res = await fetch(`${API_URL}${path}`, { cache: "no-store" });
  } catch (e) {
    throw new ApiError(0, `The Downshift API at ${API_URL} is not reachable (${(e as Error).message}).`);
  }
  if (res.status === 404) return null;
  if (!res.ok) throw new ApiError(res.status, `${path}: ${res.status} ${await res.text()}`);
  return (await res.json()) as T;
}

export const api = {
  latest: () => get<Optimization>("/v1/optimizations/latest"),
  optimization: (id: string) => get<Optimization>(`/v1/optimizations/${id}`),
  optimizations: () => get<Optimization[]>("/v1/optimizations"),
  events: (id: string, after = 0) => get<OptEvent[]>(`/v1/optimizations/${id}/events?after=${after}`),
  option: (id: string, key: string) => get<OptionDetail>(`/v1/optimizations/${id}/options/${key}`),
  run: (id: string, key: string, taskId: string, split = "test") => get<RunComparison>(`/v1/optimizations/${id}/options/${key}/runs/${taskId}?split=${split}`),
  projects: () => get<ProjectListItem[]>("/v1/projects"),
  project: (id: string) => get<Project>(`/v1/projects/${id}`),
  agents: () => get<Agent[]>("/v1/agents"),
  agent: (id: string) => get<Agent>(`/v1/agents/${id}`),
  health: () => get<Health>("/healthz"),
};

/** Browser-side JSON call through the /api rewrite. Throws with the API's `detail` on failure. */
export async function call<T>(path: string, init?: { method?: string; body?: unknown }): Promise<T> {
  let res: Response;
  try {
    res = await fetch(`/api${path}`, { method: init?.method ?? (init?.body !== undefined ? "POST" : "GET"), headers: init?.body !== undefined ? { "Content-Type": "application/json" } : undefined, body: init?.body !== undefined ? JSON.stringify(init.body) : undefined });
  } catch (e) {
    throw new Error(`Could not reach the API: ${(e as Error).message}`);
  }
  const data = await res.json().catch(() => ({}));
  if (!res.ok) throw new Error(typeof data.detail === "string" ? data.detail : `Request failed (${res.status}).`);
  return data as T;
}
