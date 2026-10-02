import type { Correction, Ledger } from "../api/types";
import { formatMoney, formatRate } from "../lib/format";

interface Props { ledger: Ledger; corrections: Correction[] }

export function LedgerTable({ ledger, corrections }: Props) {
  const changed = new Map(corrections.map((c) => [c.field, c]));
  const cell = (id: string, attr: "quantity" | "unit_price" | "amount", value: string, money: boolean) => {
    const c = changed.get(`items[${id}].${attr}`);
    const shown = money ? formatMoney(value) : value;
    if (!c) return shown;
    const old = money ? formatMoney(c.old_value) : c.old_value;
    return (<><del><span className="visually-hidden">was </span>{old}</del> <ins>{shown}</ins></>);
  };
  const totals: [string, string | null][] = [
    ["Subtotal", ledger.subtotal], ["Discount", ledger.discount],
    ...ledger.tax_lines.map((t): [string, string | null] => [`Tax${t.rate ? ` ${formatRate(t.rate)}` : ""}`, t.amount]),
    ["Shipping", ledger.shipping], ["Fees", ledger.fees], ["Total", ledger.total],
  ];
  return (
    <div className="table-scroll" tabIndex={0} role="region" aria-label={`Ledger for invoice ${ledger.invoice_id}`}>
      <table className="ledger">
        <caption className="visually-hidden">Ledger for invoice {ledger.invoice_id}</caption>
        <thead><tr><th scope="col">Description</th><th scope="col" className="num">Qty</th><th scope="col" className="num">Unit price</th><th scope="col" className="num">Amount</th></tr></thead>
        <tbody>
          {ledger.items.map((i) => (
            <tr key={i.id}>
              <td className="desc">{i.description}</td>
              <td className="num">{cell(i.id, "quantity", i.quantity, false)}</td>
              <td className="num">{cell(i.id, "unit_price", i.unit_price, true)}</td>
              <td className="num">{cell(i.id, "amount", i.amount, true)}</td>
            </tr>
          ))}
        </tbody>
        <tfoot>
          {totals.filter(([, v]) => v != null).map(([label, v]) => (
            <tr key={label} className={label === "Total" ? "grand" : undefined}>
              <th scope="row" colSpan={3}>{label}</th>
              <td className="num">{formatMoney(v)}{label === "Total" ? <span className="currency"> {ledger.currency}</span> : null}</td>
            </tr>
          ))}
        </tfoot>
      </table>
    </div>
  );
}
