import type { ReactNode } from "react";
import type { Job } from "../../api/types";
import { statusKey, type StatusKey } from "../../lib/derive";

const LABEL: Record<StatusKey, string> = { ok: "Reconciled", wn: "Needs review", in: "Processing", er: "Failed" };

/** A status chip: a dot plus text, so meaning never depends on colour alone. */
export function Pill({ tone, children }: { tone: StatusKey | "neutral"; children?: ReactNode }) {
  return (
    <span className={`pill pill-${tone}`}>
      <span className="pill-dot" aria-hidden="true" />
      {children ?? (tone === "neutral" ? null : LABEL[tone])}
    </span>
  );
}

export function StatusPill({ job }: { job: Job }) {
  return <Pill tone={statusKey(job)} />;
}
