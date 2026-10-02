import { createContext, useCallback, useContext, useEffect, useMemo, useRef, useState, type ReactNode } from "react";
import { listJobs } from "../api/client";
import type { Job } from "../api/types";

interface JobsCtx { jobs: Job[]; loading: boolean; error: string | null; refresh: () => void }
const Ctx = createContext<JobsCtx | null>(null);

export function JobsProvider({ children, pollMs = 5000 }: { children: ReactNode; pollMs?: number }) {
  const [jobs, setJobs] = useState<Job[]>([]);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const alive = useRef(true);

  const refresh = useCallback(() => {
    listJobs(100)
      .then((j) => { if (alive.current) { setJobs(j); setError(null); setLoading(false); } })
      .catch(() => { if (alive.current) { setError("Could not load invoices from the server."); setLoading(false); } });
  }, []);

  useEffect(() => { alive.current = true; refresh(); return () => { alive.current = false; }; }, [refresh]);

  const active = jobs.some((j) => j.state === "QUEUED" || j.state === "RUNNING");
  useEffect(() => {
    if (!active) return;
    const t = setInterval(refresh, pollMs);
    return () => clearInterval(t);
  }, [active, pollMs, refresh]);

  const value = useMemo(() => ({ jobs, loading, error, refresh }), [jobs, loading, error, refresh]);
  return <Ctx.Provider value={value}>{children}</Ctx.Provider>;
}

export function useJobs(): JobsCtx {
  const c = useContext(Ctx);
  if (!c) throw new Error("useJobs must be used inside JobsProvider");
  return c;
}
