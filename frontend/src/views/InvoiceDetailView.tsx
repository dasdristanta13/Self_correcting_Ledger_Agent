import { useState } from "react";
import type { Job } from "../api/types";
import { AgentTimeline } from "../components/AgentTimeline";
import { Corrections } from "../components/Corrections";
import { EvidenceList } from "../components/EvidenceList";
import { ExtractedTable } from "../components/ExtractedTable";
import { LedgerTable } from "../components/LedgerTable";
import { ReconciliationSummary } from "../components/ReconciliationSummary";
import { StatusBadge } from "../components/StatusBadge";
import { EmptyState } from "../components/ui/EmptyState";
import { PageHeader } from "../components/ui/PageHeader";
import { StatusPill } from "../components/ui/Pill";
import { LoadingRows } from "../components/ui/Skeleton";
import { Tabs, tabIds } from "../components/ui/Tabs";
import { JOB_NOT_FOUND, useJob } from "../hooks/useJob";
import { useTrace } from "../hooks/useTrace";
import { eventDetail, formatDateTime, formatMoney, formatRate } from "../lib/format";
import { statusCopy } from "../lib/status";
import { detailHref, navigate, type DetailTab } from "../router";

const back = <a className="back-link" href="#/invoices">‹ Back to invoices</a>;

export function InvoiceDetailView({ id, tab }: { id: string; tab: DetailTab }) {
  const { job, error } = useJob(id);
  const [replay, setReplay] = useState(0);

  if (error && !job) {
    return error === JOB_NOT_FOUND ? (
      <><PageHeader title="Invoice not found" back={back} />
        <EmptyState title="That invoice no longer exists" action={<a className="btn" href="#/invoices">Back to invoices</a>}>It may have been removed, or the link is wrong.</EmptyState></>
    ) : (
      <><PageHeader title="Invoice" back={back} /><p role="alert" className="field-error">Lost contact with the server. Retrying…</p></>
    );
  }
  if (!job) return <><PageHeader title="Invoice" back={back} /><LoadingRows /></>;

  const total = job.result?.ledger?.total;
  const sub = [job.result?.invoice_id, total ? `${formatMoney(total)} ${job.result?.ledger?.currency ?? ""}`.trim() : null, formatDateTime(job.created_at)]
    .filter(Boolean).join(" · ");
  const head = (
    <PageHeader back={back}
      title={<>{job.filename} <StatusPill job={job} /></>} sub={sub}
      actions={tab === "reconciliation" && job.state === "DONE" ? <button type="button" className="btn" onClick={() => setReplay((n) => n + 1)}>Replay agent</button> : undefined} />
  );
  if (job.state === "QUEUED" || job.state === "RUNNING") {
    return (<>{head}<div role="status" className="progress"><p>Reconciling {job.filename}. This usually takes a few seconds.</p><span className="working-bar" aria-hidden="true" /></div></>);
  }
  if (job.state === "ERROR") {
    return (<>{head}<p role="alert" className="field-error">Processing stopped because of a problem on our side, not with the invoice: {job.error ?? "unknown error"}. Upload it again to retry.</p>
      <section className="panel"><h2>Agent activity</h2><AgentTimeline jobId={job.job_id} replayKey={0} /></section></>);
  }
  return (
    <>
      {head}
      <Tabs label="Invoice sections" value={tab} idBase="det" onChange={(t) => navigate(detailHref(id, t as DetailTab))}
        tabs={[{ id: "document", label: "Document" }, { id: "extracted", label: "Extracted data" }, { id: "reconciliation", label: "Reconciliation" }]} />
      <div role="tabpanel" id={tabIds("det", tab).panel} aria-labelledby={tabIds("det", tab).tab}>
        {tab === "document" && <DocumentTab job={job} />}
        {tab === "extracted" && <ExtractedTab job={job} />}
        {tab === "reconciliation" && <ReconciliationTab job={job} replay={replay} />}
      </div>
    </>
  );
}

function DocumentTab({ job }: { job: Job }) {
  const r = job.result!;
  if (!r.ledger) {
    return (<><StatusBadge status={r.status} /><EmptyState title="No ledger was produced">{r.error ?? "The invoice could not be read, so there is no document to show."}</EmptyState></>);
  }
  return (
    <div className="detail-grid">
      <div className="paper">
        <header className="paper-head"><div><strong>{r.ledger.invoice_id}</strong><span className="muted">{r.ledger.currency}</span></div><span className="muted">{formatDateTime(job.created_at)}</span></header>
        <LedgerTable ledger={r.ledger} corrections={r.corrections} />
        <p className="muted paper-note">A reconstruction of the final ledger; the original PDF is not stored by the service.</p>
      </div>
      <aside className="panel" aria-labelledby="info-h">
        <h2 id="info-h">Invoice information</h2>
        <dl className="kv">
          <dt>Invoice ID</dt><dd>{r.invoice_id}</dd>
          <dt>Status</dt><dd>{statusCopy(r.status).label}</dd>
          <dt>Total</dt><dd>{formatMoney(r.ledger.total)} {r.ledger.currency}</dd>
          <dt>Correction rounds</dt><dd>{r.iterations}</dd>
          <dt>Uploaded</dt><dd>{formatDateTime(job.created_at)}</dd>
          <dt>Processed</dt><dd>{formatDateTime(job.finished_at)}</dd>
        </dl>
      </aside>
    </div>
  );
}

function ExtractedTab({ job }: { job: Job }) {
  const r = job.result!;
  const l = r.original_ledger;
  if (!l) return <EmptyState title="Nothing was extracted">{r.error ?? "No ledger could be extracted from this invoice."}</EmptyState>;
  const totals: [string, string | null][] = [
    ["Subtotal", l.subtotal], ["Discount", l.discount],
    ...l.tax_lines.map((t): [string, string | null] => [`Tax${t.rate ? ` ${formatRate(t.rate)}` : ""}`, t.amount]),
    ["Shipping", l.shipping], ["Fees", l.fees], ["Total", l.total],
  ];
  return (
    <div className="detail-grid">
      <section className="panel panel-flush"><h2 className="pad-h">Line items as extracted</h2><ExtractedTable ledger={l} corrections={r.corrections} /></section>
      <aside className="panel" aria-labelledby="hdr-h">
        <h2 id="hdr-h">Header and totals</h2>
        <dl className="kv">
          <dt>Invoice</dt><dd>{l.invoice_id}</dd><dt>Currency</dt><dd>{l.currency}</dd>
          {totals.filter(([, v]) => v != null).map(([k, v]) => (<span key={k} className="kv-row"><dt>{k}</dt><dd>{formatMoney(v)}</dd></span>))}
        </dl>
      </aside>
    </div>
  );
}

type RecTab = "details" | "evidence" | "validation" | "raw";

function ReconciliationTab({ job, replay }: { job: Job; replay: number }) {
  const r = job.result!;
  const [sub, setSub] = useState<RecTab>("details");
  return (
    <div className="detail-grid detail-grid-rec">
      <section className="panel" aria-labelledby="act-h"><h2 id="act-h">Agent activity</h2>
        <p className="muted tight">What the LangGraph run did, in order.</p>
        <AgentTimeline jobId={job.job_id} replayKey={replay} /></section>
      <div className="stack">
        <ReconciliationSummary result={r} />
        <section className="panel">
          <Tabs label="Reconciliation details" value={sub} idBase="rec" onChange={(t) => setSub(t as RecTab)}
            tabs={[{ id: "details", label: "Details" }, { id: "evidence", label: "Evidence" }, { id: "validation", label: "Validation" }, { id: "raw", label: "Raw extraction" }]} />
          <div role="tabpanel" id={tabIds("rec", sub).panel} aria-labelledby={tabIds("rec", sub).tab}>
            {sub === "details" && <Corrections items={r.corrections} />}
            {sub === "evidence" && <EvidenceList items={r.evidence} />}
            {sub === "validation" && <ValidationRounds job={job} />}
            {sub === "raw" && <pre className="raw">{JSON.stringify(r, null, 2)}</pre>}
          </div>
        </section>
      </div>
    </div>
  );
}

function ValidationRounds({ job }: { job: Job }) {
  const { events, error } = useTrace(job.job_id);
  if (error) return <p role="alert" className="field-error">{error}</p>;
  if (!events) return <p className="muted">Loading validation…</p>;
  const rounds = events.filter((e) => e.node === "validate");
  const last = rounds[rounds.length - 1];
  const clean = last && Array.isArray(last.detail?.discrepancies) && last.detail.discrepancies.length === 0;
  return (
    <div>
      <p><strong>{clean ? "All checks passed" : statusCopy(job.result!.status).label}</strong></p>
      <ol className="trace">
        {rounds.map((e, i) => (<li key={i}>Round {i + 1}: {eventDetail(e) || "checked"}</li>))}
      </ol>
      {rounds.length === 0 && <p className="muted">No validation rounds were recorded.</p>}
    </div>
  );
}
