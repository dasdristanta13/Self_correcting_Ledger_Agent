export type JobState = "QUEUED" | "RUNNING" | "DONE" | "ERROR";
export interface Provenance {
  document_id: string; page: number; block_id?: string | null; table_id?: string | null;
  row?: number | null; column?: string | null; bbox?: number[] | null;
}
export interface LineItem {
  id: string; description: string; quantity: string; unit_price: string; amount: string;
  source: Record<string, Provenance>;
}
export interface TaxLine { id: string; rate: string | null; amount: string; source: Record<string, Provenance> }
export interface Ledger {
  invoice_id: string; currency: string; items: LineItem[]; subtotal: string | null; discount: string | null;
  tax: string | null; tax_lines: TaxLine[]; shipping: string | null; fees: string | null; total: string;
  sources: Record<string, Provenance>;
}
export interface Correction {
  revision: number; field: string; old_value: string; new_value: string; reason: string;
  source_page: number | null; source_table: string | null; source_row: number | null; confidence: number;
}
export interface Evidence {
  field: string; value: string; source: Provenance; confidence: number; chunk_id: string; quote: string;
}
export interface Result {
  invoice_id: string; status: string; iterations: number; ledger: Ledger | null;
  original_ledger: Ledger | null; corrections: Correction[]; evidence: Evidence[]; error: string | null;
}
export interface Job {
  job_id: string; filename: string; state: JobState; created_at: string;
  finished_at: string | null; result: Result | null; error: string | null;
}
export interface TraceEvent {
  run_id: string; invoice_id: string | null; node: string; revision: number; started_at: string;
  latency_ms: number; status: string | null; detail: Record<string, unknown>;
}
