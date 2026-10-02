import type { Job } from "../api/types";
import { fieldLabel, formatMoney, provenanceLabel } from "../lib/format";
import { Corrections } from "./Corrections";
import { Disclosure } from "./Disclosure";
import { LedgerTable } from "./LedgerTable";
import { StatusBadge } from "./StatusBadge";
import { Trace } from "./Trace";

export function ResultView({ job }: { job: Job }) {
  if (job.state === "ERROR") {
    return (
      <p role="alert" className="field-error service-error">
        Processing stopped because of a problem on our side, not with the invoice: {job.error ?? "unknown error"}. Upload it again to retry.
      </p>
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
          {r.evidence.length === 0 ? <p className="muted">No evidence was retrieved for this invoice.</p> : (
            <ul className="evidence">
              {r.evidence.map((e, i) => (
                <li key={i}>
                  <p><strong>{fieldLabel(e.field)}</strong> <span className="money">{formatMoney(e.value)}</span></p>
                  <p className="muted">{provenanceLabel(e.source.page, e.source.table_id ?? null, e.source.row ?? null)}</p>
                  <pre>{e.quote}</pre>
                </li>
              ))}
            </ul>
          )}
        </Disclosure>
        <Disclosure title="Trace"><Trace jobId={job.job_id} /></Disclosure>
      </div>
    </article>
  );
}
