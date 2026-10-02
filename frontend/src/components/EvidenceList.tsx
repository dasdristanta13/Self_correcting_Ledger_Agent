import type { Evidence } from "../api/types";
import { fieldLabel, formatMoney, provenanceLabel } from "../lib/format";

export function EvidenceList({ items }: { items: Evidence[] }) {
  if (items.length === 0) return <p className="muted">No evidence was retrieved for this invoice.</p>;
  return (
    <ul className="evidence">
      {items.map((e, i) => (
        <li key={i}>
          <p><strong>{fieldLabel(e.field)}</strong> <span className="money">{formatMoney(e.value)}</span></p>
          <p className="muted">{provenanceLabel(e.source.page, e.source.table_id ?? null, e.source.row ?? null)}</p>
          <pre>{e.quote}</pre>
        </li>
      ))}
    </ul>
  );
}
