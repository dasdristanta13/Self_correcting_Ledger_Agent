import type { TraceEvent } from "../api/types";

export function formatMoney(value: string | null | undefined): string {
  if (value == null) return "—";
  const m = /^(-?)(\d+)(\.\d+)?$/.exec(value.trim());
  if (!m) return value;                       // never route money through Number()
  const [, sign, int, frac = ""] = m;
  return `${sign}${int.replace(/\B(?=(\d{3})+(?!\d))/g, ",")}${frac}`;
}

export function provenanceLabel(page: number | null, table: string | null, row: number | null): string {
  const parts: string[] = [];
  if (page != null) parts.push(`Page ${page}`);
  if (table) parts.push(table);
  if (row != null) parts.push(`Row ${row}`);
  return parts.join(" · ");
}

export function fieldLabel(path: string): string {
  const m = /^(items|tax_lines)\[([^\]]+)\]\.(\w+)$/.exec(path);
  if (!m) return path;
  const [, , id, attr] = m;
  return `${id.replace("_", " ")} · ${attr.replace("_", " ")}`;
}

/** "0.10" -> "10%", "0.075" -> "7.5%". Pure string math: a rate is never routed through Number(). */
export function formatRate(rate: string | null | undefined): string {
  if (rate == null) return "";
  const m = /^(\d+)(?:\.(\d+))?$/.exec(rate.trim());
  if (!m) return rate;
  const frac = (m[2] ?? "").padEnd(2, "0");
  const whole = (m[1] + frac.slice(0, 2)).replace(/^0+(?=\d)/, "");
  const rest = frac.slice(2).replace(/0+$/, "");
  return `${whole}${rest ? `.${rest}` : ""}%`;
}

const validDate = (iso: string | null | undefined): Date | null => {
  if (!iso) return null;
  const d = new Date(iso);
  return Number.isNaN(d.getTime()) ? null : d;
};

export function formatDate(iso: string | null | undefined): string {
  const d = validDate(iso);
  return d ? d.toLocaleDateString("en-US", { month: "short", day: "2-digit", year: "numeric" }) : "—";
}
export function formatTime(iso: string | null | undefined): string {
  const d = validDate(iso);
  return d ? d.toLocaleTimeString("en-US", { hour: "2-digit", minute: "2-digit", hourCycle: "h23" }) : "—";
}
export function formatDateTime(iso: string | null | undefined): string {
  return validDate(iso) ? `${formatDate(iso)} · ${formatTime(iso)}` : "—";
}

const NODE_LABELS: Record<string, string> = {
  ingest: "Read document", extract: "Extract tables", build_index: "Build evidence index",
  build_ledger: "Build ledger", validate: "Validate arithmetic", audit: "Search for evidence",
  verify_evidence: "Verify evidence", reconcile: "Apply correction", finalize: "Reconciled", failed: "Stopped",
};
export function nodeLabel(node: string): string {
  if (NODE_LABELS[node]) return NODE_LABELS[node];
  const s = node.replace(/_/g, " ");
  return s.charAt(0).toUpperCase() + s.slice(1);
}

const plural = (n: number, one: string, many: string) => `${n} ${n === 1 ? one : many}`;
export function eventDetail(e: TraceEvent): string {
  const d = e.detail ?? {};
  const parts: string[] = [];
  if (Array.isArray(d.discrepancies)) {
    parts.push(d.discrepancies.length === 0 ? "No discrepancies" : plural(d.discrepancies.length, "discrepancy", "discrepancies"));
  }
  if (typeof d.evidence_count === "number") parts.push(plural(d.evidence_count, "evidence chunk", "evidence chunks"));
  if (Array.isArray(d.corrections)) parts.push(`${plural(d.corrections.length, "correction", "corrections")} proposed`);
  if (typeof d.error === "string") parts.push(d.error);
  return parts.join(" · ");
}
