import { useEffect, useState } from "react";
import { getJob } from "../api/client";
import type { Job } from "../api/types";

export const JOB_NOT_FOUND = "That job no longer exists.";

export function useJob(jobId: string | null, intervalMs = 1000) {
  const [job, setJob] = useState<Job | null>(null);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    setJob(null);
    setError(null);
    if (!jobId) return;
    let cancelled = false;
    let timer: ReturnType<typeof setTimeout> | undefined;
    const tick = async () => {
      try {
        const j = await getJob(jobId);
        if (cancelled) return;
        setJob(j);
        setError(null);
        if (j.state === "QUEUED" || j.state === "RUNNING") timer = setTimeout(tick, intervalMs);
      } catch (e) {
        if (cancelled) return;
        const status = (e as { status?: number } | null)?.status;
        if (status === 404) {                              // unknown job: retrying cannot help
          setError(JOB_NOT_FOUND);
          return;
        }
        setError(e instanceof Error ? e.message : "Network error");
        timer = setTimeout(tick, intervalMs * 3);          // keep trying
      }
    };
    void tick();
    return () => { cancelled = true; if (timer) clearTimeout(timer); };
  }, [jobId, intervalMs]);

  return { job, error };
}
