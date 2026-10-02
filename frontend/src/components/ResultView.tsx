import type { Job } from "../api/types";
import { detailHref } from "../router";
import { Corrections } from "./Corrections";
import { Disclosure } from "./Disclosure";
import { EvidenceList } from "./EvidenceList";
import { LedgerTable } from "./LedgerTable";
import { StatusBadge } from "./StatusBadge";
import { Trace } from "./Trace";

export function ResultView({ job }: { job: Job }) {
  if (job.state === "ERROR") {
    return (
      <>
        <p role="alert" className="field-error service-error">
          Processing stopped because of a problem on our side, not with the invoice: {job.error ?? "unknown error"}. Upload it again to retry.
        </p>
        <div className="disclosures">
          <Disclosure title="Trace"><Trace jobId={job.job_id} /></Disclosure>
        </div>
      </>
    );
  }
  const r = job.result;
  if (!r) return null;
  return (
    <article className="result" aria-label={`Result for ${job.filename}`}>
      <header className="result-head">
        <h2 className="result-title" title={job.filename}>{job.filename}</h2>
        {r.ledger && (
          <p className="muted result-meta">
            {r.iterations} {r.iterations === 1 ? "correction round" : "correction rounds"}
          </p>
        )}
      </header>
      <StatusBadge status={r.status} />
      <p><a href={detailHref(job.job_id)}>Open full detail →</a></p>
      {r.error && <p className="muted">{r.error}</p>}
      {r.ledger && <LedgerTable ledger={r.ledger} corrections={r.corrections} />}
      {/* Without a ledger (FAILED) "No corrections were needed" would mislead, so omit the section. */}
      {(r.ledger || r.corrections.length > 0) && (
        <section className="result-section" aria-labelledby={`corr-${job.job_id}`}>
          <h3 id={`corr-${job.job_id}`}>Corrections</h3>
          <Corrections items={r.corrections} />
        </section>
      )}
      <div className="disclosures">
        <Disclosure title={`Evidence (${r.evidence.length})`}>
          <EvidenceList items={r.evidence} />
        </Disclosure>
        <Disclosure title="Trace"><Trace jobId={job.job_id} /></Disclosure>
      </div>
    </article>
  );
}
