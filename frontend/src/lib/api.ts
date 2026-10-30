import type { Loc } from "./loc";

export type Provenance = "LIVE_MEASURED" | "IMPORTED" | "DEMO_SAMPLE" | "NOT_RUN" | "FAILED";

export interface Run {
  id: string;
  action: string;
  params: Record<string, unknown>;
  status: "pending" | "running" | "succeeded" | "failed" | "blocked" | "not_run";
  command: string;
  provenance: Provenance;
  created_at: number;
  started_at: number | null;
  finished_at: number | null;
  heartbeat_at: number | null;
  progress: number | null;
  timeout_s: number;
  logs: { t: number; level: string; msg: string }[];
  result: any;
  error: { code: string; detail?: string; trace?: string } | null;
  experiment_id: string | null;
  mission_id: string | null;
  step_id: string | null;
  approval: { reason: string } | null;
}

export interface Check { id: string; description: Loc; path: string; op: string; value: unknown }
// The answer and explanation stay on the server; the explanation comes back from the quiz endpoint.
export interface Quiz { question: Loc; options: Loc[] }
export interface Step {
  id: string; title: Loc; what: Loc; why: Loc; concept: string | null;
  action: { id: string; params: Record<string, unknown>; editable: string[] } | null;
  expected: Loc; checks: Check[]; failure: Loc; hints: Loc[];
  sources: { file: string; symbol: string | null }[];
  alternatives: Loc | null; reproduce: Loc | null; optional: boolean;
  requires_capabilities: string[]; quiz: Quiz | null;
}
export interface Mission {
  id: string; number: number; version: string; title: Loc; tagline: Loc; objectives: Loc[];
  prerequisites: string[]; concepts: string[]; references: string[]; steps: Step[];
  challenge: { prompt: Loc; action: { id: string; params: Record<string, unknown>; editable: string[] }; checks: Check[] } | null;
  optional_experiments: Loc[]; completion_evidence: Loc;
}
export interface MissionStatus {
  id: string; state: "locked" | "available" | "in_progress" | "complete" | "not_available";
  steps: Record<string, "verified" | "pending" | "not_available">; blocked_by: string[];
  unavailable_steps: string[]; required: number; verified: number; hints_used: number;
  challenge_verified: boolean; mastery: "none" | "started" | "practiced" | "independent";
}
export interface CheckResult { id: string; passed: boolean; path: string; op: string; expected: unknown; actual: unknown; missing: boolean }
export interface StepProgress {
  hints_used: number;
  evaluation: { status: string; checks: CheckResult[]; run_id: string; provenance?: string; experiment_id?: string } | null;
  quiz: { correct: boolean; attempts: number } | null;
  attempts?: { run_id: string; status: string }[];
}
export interface MissionsResponse {
  missions: Mission[];
  status: Record<string, MissionStatus>;
  progress: { missions: Record<string, { steps: Record<string, StepProgress>; challenge: any }> };
  capabilities: Record<string, boolean>;
  scanned: boolean;
}

async function j<T>(res: Response): Promise<T> {
  if (!res.ok) {
    let detail: unknown = res.statusText;
    try { detail = (await res.json()).detail; } catch { /* keep statusText */ }
    throw new ApiError(res.status, detail);
  }
  return res.json() as Promise<T>;
}

export class ApiError extends Error {
  constructor(public status: number, public detail: unknown) {
    super(typeof detail === "string" ? detail : JSON.stringify(detail));
  }
}

const post = (url: string, body: unknown) =>
  fetch(url, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body) });

export const api = {
  missions: () => fetch("/api/missions").then(j<MissionsResponse>),
  runStep: (mid: string, sid: string, params: Record<string, unknown>, approve: boolean) =>
    post(`/api/missions/${mid}/steps/${sid}/run`, { params, approve }).then(j<Run>),
  runChallenge: (mid: string, params: Record<string, unknown>, approve: boolean) =>
    post(`/api/missions/${mid}/challenge/run`, { params, approve }).then(j<Run>),
  quiz: (mid: string, sid: string, answer: number) =>
    post(`/api/missions/${mid}/steps/${sid}/quiz`, { answer }).then(j<{ correct: boolean; explanation: Loc | null }>),
  hint: (mid: string, sid: string) =>
    post(`/api/missions/${mid}/steps/${sid}/hint`, {}).then(j<{ hints_used: number; available: number; hints: Loc[] }>),
  submit: (action: string, params: Record<string, unknown>, approve = false) =>
    post("/api/runs", { action, params, approve }).then(j<Run>),
  preview: (action: string, params: Record<string, unknown>) =>
    post(`/api/actions/${action}/preview`, { params }).then(j<{ command: string; approval_required: string | null; missing_capabilities: string[]; action: any }>),
  run: (id: string) => fetch(`/api/runs/${id}`).then(j<Run>),
  runs: () => fetch("/api/runs").then(j<Run[]>),
  diagnosis: (id: string, lang: string) => fetch(`/api/runs/${id}/diagnosis?lang=${lang}`).then(j<Diagnosis>),
  errorHelp: (code: string, lang: string) => fetch(`/api/errors/${encodeURIComponent(code)}?lang=${lang}`).then(j<{ what: string; why: string; next: string }>),
  hardware: () => fetch("/api/hardware").then(j<{ scan: any }>),
  catalog: () => fetch("/api/models/catalog").then(j<{ id: string; kind: string; size_class: string; download: boolean; note: Loc }[]>),
  localModels: () => fetch("/api/models/local").then(j<string[]>),
  experiments: () => fetch("/api/experiments").then(j<any[]>),
  experiment: (id: string) => fetch(`/api/experiments/${id}`).then(j<any>),
  notes: (id: string, notes: Record<string, string>) => post(`/api/experiments/${id}/notes`, notes).then(j<any>),
  compare: (a: string, b: string, lang: string) => fetch(`/api/experiments/${a}/compare/${b}?lang=${lang}`).then(j<any>),
  importExperiment: (data: unknown) => post("/api/experiments/import", data).then(j<any>),
  demo: () => fetch("/api/demo/benchmark").then(j<any>),
  source: (path: string, symbol?: string | null) =>
    fetch(`/api/source?path=${encodeURIComponent(path)}${symbol ? `&symbol=${encodeURIComponent(symbol)}` : ""}`).then(j<SourceFile>),
  sourceTree: () => fetch("/api/source/tree").then(j<string[]>),
  explain: (body: Record<string, unknown>) => post("/api/tutor/explain", body).then(j<any>),
  ask: (question: string, context: Record<string, unknown>, lang: string) => post("/api/tutor/ask", { question, context, lang }).then(j<any>),
  concepts: () => fetch("/api/tutor/concepts").then(j<Record<string, any>>),
  research: () => fetch("/api/research").then(j<any[]>),
  resetProgress: () => post("/api/progress/reset", {}).then(j<any>),
};

export interface SourceFile { path: string; language: string; content: string; lines: number; symbol: string | null; range: [number, number] | null; kind: string }
export interface Diagnosis { state: string; summary: string; evidence: string[]; causes: string[]; next: string[] }

/** Poll a run until it leaves running/pending. */
export async function waitForRun(id: string, onTick: (r: Run) => void, intervalMs = 400): Promise<Run> {
  for (;;) {
    const r = await api.run(id);
    onTick(r);
    if (r.status !== "running" && r.status !== "pending") return r;
    await new Promise((res) => setTimeout(res, intervalMs));
  }
}
