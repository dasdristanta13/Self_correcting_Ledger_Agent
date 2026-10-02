import type { Result } from "../api/types";
import { fieldLabel, formatMoney, provenanceLabel } from "../lib/format";
import { statusCopy } from "../lib/status";
import { Pill } from "./ui/Pill";

export function ReconciliationSummary({ result }: { result: Result }) {
  const resolved = result.status === "RECONCILED";
  const first = result.corrections[0];
  if (!first) {
    const c = statusCopy(result.status);
    return (
      <div className={`mis ${resolved ? "is-resolved" : "is-open"}`}>
        <div className="mis-head"><strong>{resolved ? "No discrepancies found" : c.label}</strong>
          <Pill tone={resolved ? "ok" : "wn"}>{resolved ? "Resolved" : "Unresolved"}</Pill></div>
        <p>{resolved ? "Every figure added up on the first pass." : c.hint}</p>
      </div>
    );
  }
  const n = result.corrections.length;
  return (
    <div className={`mis ${resolved ? "is-resolved" : "is-open"}`}>
      <div className="mis-head">
        <strong>{n === 1 ? "Line item mismatch" : `${n} corrections applied`}</strong>
        <Pill tone={resolved ? "ok" : "wn"}>{resolved ? "Resolved" : "Unresolved"}</Pill>
      </div>
      <p className="mis-change"><del>{formatMoney(first.old_value)}</del> → <ins>{formatMoney(first.new_value)}</ins></p>
      <p className="muted">{fieldLabel(first.field)} · {provenanceLabel(first.source_page, first.source_table, first.source_row)}</p>
    </div>
  );
}
