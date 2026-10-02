import type { DayBucket } from "../lib/derive";

export function ActivityChart({ buckets }: { buckets: DayBucket[] }) {
  const max = Math.max(1, ...buckets.map((b) => b.ok + b.wn + b.er));
  const sum = (k: "ok" | "wn" | "er") => buckets.reduce((n, b) => n + b[k], 0);
  const label = `Invoices per day, last ${buckets.length} days: ${sum("ok")} reconciled, ${sum("wn")} needing review, ${sum("er")} failed`;
  const pct = (n: number) => (n === 0 ? 0 : Math.max(3, (n / max) * 100));
  return (
    <div className="chart" role="img" aria-label={label}>
      {buckets.map((b) => (
        <div key={b.day} className="chart-col" title={`${b.day}: ${b.ok} reconciled, ${b.wn} needs review, ${b.er} failed`}>
          <span className="seg-er" style={{ height: `${pct(b.er)}%` }} />
          <span className="seg-wn" style={{ height: `${pct(b.wn)}%` }} />
          <span className="seg-ok" style={{ height: `${pct(b.ok)}%` }} />
        </div>
      ))}
    </div>
  );
}
