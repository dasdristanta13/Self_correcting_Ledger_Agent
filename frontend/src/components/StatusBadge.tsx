type Tone = "good" | "warn" | "bad";

const COPY: Record<string, { label: string; tone: Tone; hint: string }> = {
  RECONCILED: { label: "Reconciled", tone: "good", hint: "Every figure now adds up." },
  UNRESOLVED: { label: "Needs review", tone: "warn", hint: "The invoice's own figures disagree and nothing in it says which is right." },
  MAX_REVISIONS_EXCEEDED: { label: "Stopped at limit", tone: "warn", hint: "The correction limit was reached before the totals matched." },
  INSUFFICIENT_EVIDENCE: { label: "Not enough evidence", tone: "warn", hint: "No correction was confident enough to apply." },
  NO_PROGRESS: { label: "No progress", tone: "warn", hint: "A correction did not change the discrepancy, so the run stopped." },
  FAILED: { label: "Could not read", tone: "bad", hint: "The invoice could not be processed. It may be a scan or have no line-item table." },
};

/** Status is carried by the label text and the mark's shape (check, bang, cross); colour only reinforces it. */
export function StatusBadge({ status }: { status: string }) {
  const c = COPY[status] ?? { label: status, tone: "warn" as const, hint: "This status is not recognised by this version of the app." };
  return (
    <div className={`status status-${c.tone}`} data-status={status}>
      <span className="status-mark" aria-hidden="true" />
      <div className="status-text"><strong>{c.label}</strong><p>{c.hint}</p></div>
    </div>
  );
}
