import type { Correction, Ledger } from "../api/types";
import { formatMoney, provenanceLabel } from "../lib/format";

export function ExtractedTable({ ledger, corrections }: { ledger: Ledger; corrections: Correction[] }) {
  const corrected = new Set(corrections.map((c) => c.field));
  return (
    <div className="table-scroll" tabIndex={0} role="region" aria-label="Extracted line items">
      <table className="data" aria-label={`Extracted line items for ${ledger.invoice_id}`}>
        <thead><tr><th scope="col">Description</th><th scope="col" className="num">Qty</th><th scope="col" className="num">Unit price</th><th scope="col" className="num">Amount</th><th scope="col">Source</th></tr></thead>
        <tbody>
          {ledger.items.map((i) => {
            const p = i.source.amount ?? Object.values(i.source)[0];
            return (
              <tr key={i.id}>
                <td>{i.description}</td>
                <td className="num">{i.quantity}</td>
                <td className="num">{formatMoney(i.unit_price)}</td>
                <td className="num">{formatMoney(i.amount)}{corrected.has(`items[${i.id}].amount`) && <> <span className="flag">Corrected</span></>}</td>
                <td className="muted">{p ? provenanceLabel(p.page, p.table_id ?? null, p.row ?? null) : "—"}</td>
              </tr>
            );
          })}
        </tbody>
      </table>
    </div>
  );
}
