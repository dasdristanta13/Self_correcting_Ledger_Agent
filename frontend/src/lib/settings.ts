import { readJSON, writeJSON } from "./storage";

export type SettingValue = boolean | string;
export interface SettingDef { key: string; label: string; hint?: string; kind: "toggle" | "select"; options?: string[]; default: SettingValue }

const sel = (key: string, label: string, options: string[], def: string, hint?: string): SettingDef => ({ key, label, hint, kind: "select", options, default: def });
const tog = (key: string, label: string, def: boolean, hint?: string): SettingDef => ({ key, label, hint, kind: "toggle", default: def });

export const SETTING_GROUPS: Record<string, SettingDef[]> = {
  General: [
    sel("currency_format", "Currency format", ["USD – US Dollar ($)", "EUR – Euro (€)", "GBP – Pound (£)", "INR – Rupee (₹)"], "USD – US Dollar ($)"),
    sel("date_format", "Date format", ["MM/DD/YYYY", "DD/MM/YYYY", "YYYY-MM-DD"], "MM/DD/YYYY"),
  ],
  Extraction: [
    tog("detect_scans", "Auto-detect scanned PDFs", true, "Scanned pages need an OCR backend, which this build does not ship."),
    tog("extract_tables", "Extract tables", true),
    tog("preserve_layout", "Preserve document layout", true),
    tog("high_accuracy", "High accuracy mode", false),
  ],
  Validation: [
    sel("tolerance", "Rounding tolerance", ["0.00", "0.01", "0.05"], "0.01", "Largest difference treated as rounding."),
    tog("validate_tax_per_line", "Validate tax per line", true),
  ],
  Agent: [
    sel("max_revisions", "Max correction iterations", ["1", "2", "3", "5"], "3"),
    sel("confidence_threshold", "Evidence confidence threshold", ["0.80", "0.90", "0.95"], "0.90", "Corrections below this confidence are not applied."),
    sel("top_k", "Retrieval top-K", ["3", "5", "8"], "5"),
    tog("auto_reconcile", "Auto-reconciliation", true),
  ],
  Notifications: [
    tog("notify_done", "Reconciliation completed", true),
    tog("notify_review", "Needs review", true),
    tog("notify_failed", "Processing failed", true),
  ],
};

const KEY = "ledger.settings";
const ALL = Object.values(SETTING_GROUPS).flat();

export const defaultSettings = (): Record<string, SettingValue> => Object.fromEntries(ALL.map((d) => [d.key, d.default]));

export function loadSettings(): Record<string, SettingValue> {
  const stored = readJSON<Record<string, unknown>>(KEY, {});
  const out = defaultSettings();
  if (!stored || typeof stored !== "object") return out;
  for (const d of ALL) {
    const v = stored[d.key];
    if (d.kind === "toggle" && typeof v === "boolean") out[d.key] = v;
    if (d.kind === "select" && typeof v === "string" && d.options!.includes(v)) out[d.key] = v;
  }
  return out;
}

export function saveSettings(s: Record<string, SettingValue>): void {
  writeJSON(KEY, s);
}
