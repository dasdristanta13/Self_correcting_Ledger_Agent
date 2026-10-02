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
