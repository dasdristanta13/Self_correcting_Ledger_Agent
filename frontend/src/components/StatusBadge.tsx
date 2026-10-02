import { statusCopy } from "../lib/status";

/** Status is carried by the label text and the mark's shape (check, bang, cross); colour only reinforces it. */
export function StatusBadge({ status }: { status: string }) {
  const c = statusCopy(status);
  return (
    <div className={`status status-${c.tone}`} data-status={status}>
      <span className="status-mark" aria-hidden="true" />
      <div className="status-text"><strong>{c.label}</strong><p>{c.hint}</p></div>
    </div>
  );
}
