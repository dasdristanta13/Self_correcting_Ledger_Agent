import type { Job } from "../api/types";

export type StatusKey = "ok" | "wn" | "in" | "er";
export type Priority = "High" | "Medium" | "Low";
export interface DayBucket { day: string; ok: number; wn: number; er: number }

export function statusKey(job: Job): StatusKey {
  if (job.state === "QUEUED" || job.state === "RUNNING") return "in";
  if (job.state === "ERROR" || !job.result) return "er";
  const s = job.result.status;
  if (s === "RECONCILED") return "ok";
  if (s === "FAILED") return "er";
  return "wn";
}

export function countByKey(jobs: Job[]): Record<StatusKey, number> {
  const out: Record<StatusKey, number> = { ok: 0, wn: 0, in: 0, er: 0 };
  for (const j of jobs) out[statusKey(j)]++;
  return out;
}

export function reconciliationRate(jobs: Job[]): number | null {
  const c = countByKey(jobs);
  const finished = c.ok + c.wn + c.er;
  return finished === 0 ? null : Math.round((c.ok / finished) * 100);
}

const dayKey = (d: Date) =>
  `${d.getFullYear()}-${String(d.getMonth() + 1).padStart(2, "0")}-${String(d.getDate()).padStart(2, "0")}`;

export function dailyBuckets(jobs: Job[], days: number, now: Date): DayBucket[] {
  const buckets: DayBucket[] = [];
  const index = new Map<string, DayBucket>();
  for (let i = days - 1; i >= 0; i--) {
    const d = new Date(now.getFullYear(), now.getMonth(), now.getDate() - i);
    const b = { day: dayKey(d), ok: 0, wn: 0, er: 0 };
    buckets.push(b);
    index.set(b.day, b);
  }
  for (const j of jobs) {
    const t = new Date(j.created_at);
    if (Number.isNaN(t.getTime())) continue;
    const b = index.get(dayKey(t));
    const k = statusKey(j);
    if (b && k !== "in") b[k]++;
  }
  return buckets;
}

/** A derived triage rule, not stored data: how urgently a human should look at this job. */
export function priorityOf(job: Job): Priority {
  if (job.state === "ERROR" || !job.result) return "High";
  switch (job.result.status) {
    case "UNRESOLVED": case "FAILED": return "High";
    case "INSUFFICIENT_EVIDENCE": return "Low";
    default: return "Medium";
  }
}

export function needsReview(jobs: Job[]): Job[] {
  return jobs.filter((j) => { const k = statusKey(j); return k === "wn" || k === "er"; });
}

export const stopReason = (job: Job): string => (job.state === "ERROR" || !job.result ? "ERROR" : job.result.status);
export const correctionCount = (job: Job): number => job.result?.corrections.length ?? 0;
export const agentLoad = (jobs: Job[]): number => countByKey(jobs).in;
