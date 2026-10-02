import { useTrace } from "../hooks/useTrace";

export function Trace({ jobId }: { jobId: string }) {
  const { events, error } = useTrace(jobId);
  if (error) return <p role="alert" className="field-error">{error}</p>;
  if (!events) return <p className="muted">Loading trace…</p>;
  if (events.length === 0) return <p className="muted">No trace was recorded for this job.</p>;
  return (
    <ol className="trace">
      {events.map((e, i) => (<li key={i}><strong>{e.node}</strong> <span className="muted">{e.latency_ms.toFixed(1)} ms{e.status ? ` · ${e.status}` : ""}</span></li>))}
    </ol>
  );
}
