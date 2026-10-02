import { getJob } from "../api/client";
import type { Job } from "../api/types";

/** Runs `worker` over `items` with at most `limit` in flight. Never rejects: a throwing worker is skipped. */
export async function runPool<T>(items: T[], limit: number, worker: (item: T, index: number) => Promise<void>): Promise<void> {
  let next = 0;
  const lane = async () => {
    while (next < items.length) {
      const i = next++;
      try { await worker(items[i], i); } catch { /* the worker owns its error reporting */ }
    }
  };
  await Promise.all(Array.from({ length: Math.min(Math.max(1, limit), items.length) }, lane));
}

export async function pollJob(id: string, intervalMs = 1000, maxFailures = 3): Promise<Job> {
  let failures = 0;
  for (;;) {
    try {
      const j = await getJob(id);
      failures = 0;
      if (j.state === "DONE" || j.state === "ERROR") return j;
    } catch (e) {
      failures++;
      if ((e as { status?: number } | null)?.status === 404 || failures >= maxFailures) throw e;
    }
    await new Promise((r) => setTimeout(r, intervalMs));
  }
}
