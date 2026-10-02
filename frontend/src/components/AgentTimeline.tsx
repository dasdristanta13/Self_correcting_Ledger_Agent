import { useEffect, useState } from "react";
import { useTrace } from "../hooks/useTrace";
import { eventDetail, formatTime, nodeLabel } from "../lib/format";

export function AgentTimeline({ jobId, replayKey, stepMs = 450 }: { jobId: string; replayKey: number; stepMs?: number }) {
  const { events, error } = useTrace(jobId);
  const [shown, setShown] = useState<number | null>(null);      // null = every event

  useEffect(() => {
    if (!events || replayKey === 0) { setShown(null); return; }
    if (typeof window.matchMedia === "function" && window.matchMedia("(prefers-reduced-motion: reduce)").matches) { setShown(null); return; }
    let n = 0;
    setShown(0);
    const t = setInterval(() => {
      n++;
      if (n >= events.length) { setShown(null); clearInterval(t); } else setShown(n);
    }, stepMs);
    return () => clearInterval(t);
  }, [replayKey, events, stepMs]);

  if (error) return <p role="alert" className="field-error">{error}</p>;
  if (!events) return <p className="muted">Loading trace…</p>;
  if (events.length === 0) return <p className="muted">No trace was recorded for this job.</p>;
  const visible = shown === null ? events : events.slice(0, shown);
  return (
    <ol className="timeline" aria-label="Agent activity">
      {visible.map((e, i) => (
        <li key={i} className={e.status === "FAILED" ? "is-bad" : undefined}>
          <time>{formatTime(e.started_at)}</time>
          <strong>{nodeLabel(e.node)}</strong>
          <span className="muted">{eventDetail(e) || `${e.latency_ms.toFixed(1)} ms`}</span>
        </li>
      ))}
    </ol>
  );
}
