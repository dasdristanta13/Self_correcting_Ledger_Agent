import { useEffect, useState } from "react";
import { getTrace } from "../api/client";
import type { Job, TraceEvent } from "../api/types";

export interface AuditRow { job: Job; event: TraceEvent }

export function useTraces(jobs: Job[], max = 10) {
  const [rows, setRows] = useState<AuditRow[]>([]);
  const [loading, setLoading] = useState(true);
  const [failed, setFailed] = useState(0);
  const recent = jobs.slice(0, max);
  const key = recent.map((j) => j.job_id).join(",");

  useEffect(() => {
    let live = true;
    if (recent.length === 0) { setRows([]); setFailed(0); setLoading(false); return; }
    setLoading(true);
    Promise.allSettled(recent.map((j) => getTrace(j.job_id))).then((results) => {
      if (!live) return;
      const out: AuditRow[] = [];
      let bad = 0;
      results.forEach((r, i) => {
        if (r.status === "fulfilled") r.value.forEach((event) => out.push({ job: recent[i], event }));
        else bad++;
      });
      out.sort((a, b) => b.event.started_at.localeCompare(a.event.started_at));
      setRows(out); setFailed(bad); setLoading(false);
    });
    return () => { live = false; };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [key]);

  return { rows, loading, failed };
}
