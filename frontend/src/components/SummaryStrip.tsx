import type { StatusKey } from "../lib/derive";

export function SummaryStrip({ counts, rate }: { counts: Record<StatusKey, number>; rate: number | null }) {
  const total = counts.ok + counts.wn + counts.in + counts.er;
  const items: [string, string][] = [
    ["Invoices", String(total)], ["Reconciled", String(counts.ok)], ["Needs review", String(counts.wn)],
    ["Failed", String(counts.er)], ["Reconciliation rate", rate === null ? "—" : `${rate}%`],
  ];
  return (
    <dl className="summary" role="group" aria-label="Invoice summary">
      {items.map(([label, value]) => (
        <div key={label}><dt>{label}</dt><dd>{value}</dd></div>
      ))}
    </dl>
  );
}
