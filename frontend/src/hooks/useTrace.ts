import { useEffect, useState } from "react";
import { getTrace } from "../api/client";
import type { TraceEvent } from "../api/types";

export function useTrace(jobId: string): { events: TraceEvent[] | null; error: string | null } {
  const [events, setEvents] = useState<TraceEvent[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    setEvents(null);
    setError(null);
    getTrace(jobId).then((e) => live && setEvents(e)).catch((e) => live && setError(e instanceof Error ? e.message : "Could not load the trace."));
    return () => { live = false; };
  }, [jobId]);
  return { events, error };
}
