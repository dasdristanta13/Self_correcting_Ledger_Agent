import type { Correction } from "../api/types";
import { fieldLabel, formatMoney, provenanceLabel } from "../lib/format";

export function Corrections({ items }: { items: Correction[] }) {
  if (items.length === 0) return <p className="muted">No corrections were applied.</p>;
  return (
    <ul className="corrections">
      {items.map((c, i) => (
        <li key={`${c.field}-${i}`}>
          <strong>{fieldLabel(c.field)}</strong>
          <span className="change"><del>{formatMoney(c.old_value)}</del> → <ins>{formatMoney(c.new_value)}</ins></span>
          <span className="muted">{provenanceLabel(c.source_page, c.source_table, c.source_row)} · confidence {(c.confidence * 100).toFixed(0)}%</span>
        </li>
      ))}
    </ul>
  );
}
