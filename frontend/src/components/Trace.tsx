import { useEffect, useState } from "react";
import { getTrace } from "../api/client";
import type { TraceEvent } from "../api/types";

export function Trace({ jobId }: { jobId: string }) {
  const [events, setEvents] = useState<TraceEvent[] | null>(null);
  const [error, setError] = useState<string | null>(null);
  useEffect(() => {
    let live = true;
    getTrace(jobId).then((e) => live && setEvents(e)).catch((e) => live && setError(e.message));
    return () => { live = false; };
  }, [jobId]);
  if (error) return <p role="alert" className="field-error">{error}</p>;
  if (!events) return <p className="muted">Loading trace…</p>;
  if (events.length === 0) return <p className="muted">No trace was recorded for this job.</p>;
  return (
    <ol className="trace">
      {events.map((e, i) => (<li key={i}><strong>{e.node}</strong> <span className="muted">{e.latency_ms.toFixed(1)} ms{e.status ? ` · ${e.status}` : ""}</span></li>))}
    </ol>
  );
}
