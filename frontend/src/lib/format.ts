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
