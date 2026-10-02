export type Tone = "good" | "warn" | "bad";
export interface StatusCopy { label: string; tone: Tone; hint: string }

export const STATUS_COPY: Record<string, StatusCopy> = {
  RECONCILED: { label: "Reconciled", tone: "good", hint: "Every figure now adds up." },
  UNRESOLVED: { label: "Needs review", tone: "warn", hint: "The invoice's own figures disagree and nothing in it says which is right." },
  MAX_REVISIONS_EXCEEDED: { label: "Stopped at limit", tone: "warn", hint: "The correction limit was reached before the totals matched." },
  INSUFFICIENT_EVIDENCE: { label: "Not enough evidence", tone: "warn", hint: "No correction was confident enough to apply." },
  NO_PROGRESS: { label: "No progress", tone: "warn", hint: "A correction did not change the discrepancy, so the run stopped." },
  FAILED: { label: "Could not read", tone: "bad", hint: "The invoice could not be processed. It may be a scan or have no line-item table." },
  ERROR: { label: "Service error", tone: "bad", hint: "Processing stopped because of a problem on our side, not with the invoice." },
};

export function statusCopy(status: string): StatusCopy {
  return STATUS_COPY[status] ?? { label: status, tone: "warn", hint: "This status is not recognised by this version of the app." };
}
