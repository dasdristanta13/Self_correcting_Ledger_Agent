import { useState } from "react";
import { EmptyState } from "../components/ui/EmptyState";
import { PageHeader } from "../components/ui/PageHeader";
import { LoadingRows } from "../components/ui/Skeleton";
import { useJobs } from "../hooks/useJobs";
import { useTraces } from "../hooks/useTraces";
import { eventDetail, formatDateTime, nodeLabel } from "../lib/format";
import { detailHref } from "../router";

export function AuditView() {
  const { jobs, loading: jobsLoading, error, refresh } = useJobs();
  const { rows, loading, failed } = useTraces(jobs);
  const [only, setOnly] = useState("all");
  const header = <PageHeader title="Audit trail" sub="What the agent did, step by step, across your most recent invoices." />;
  if (jobsLoading || loading) return <>{header}<LoadingRows /></>;
  if (error && jobs.length === 0) {
    return (<>{header}<p role="alert" className="field-error">{error} <button type="button" className="btn" onClick={refresh}>Try again</button></p></>);
  }
  if (jobs.length === 0 || (rows.length === 0 && failed === 0)) {
    return (<>{header}<EmptyState title="No activity yet" action={<a className="btn btn-primary" href="#/upload">Upload an invoice</a>}>
      Agent steps appear here once an invoice has been processed.</EmptyState></>);
  }
  const ids = [...new Map(rows.map((r) => [r.job.job_id, r.job.filename])).entries()];
  const activeOnly = ids.some(([id]) => id === only) ? only : "all";
  const shown = activeOnly === "all" ? rows : rows.filter((r) => r.job.job_id === activeOnly);
  return (
    <>
      {header}
      <div className="toolbar">
        <label className="field-inline">Invoice
          <select value={activeOnly} onChange={(e) => setOnly(e.target.value)} aria-label="Invoice">
            <option value="all">All invoices</option>
            {ids.map(([id, name]) => <option key={id} value={id}>{name}</option>)}
          </select>
        </label>
        {failed > 0 && <p role="status" className="muted">{failed} invoice trace{failed === 1 ? "" : "s"} could not be loaded.</p>}
      </div>
      <section className="panel panel-flush">
        <div className="table-scroll" tabIndex={0} role="region" aria-label="Audit trail">
          <table className="data">
            <thead><tr><th scope="col">Time</th><th scope="col">Invoice</th><th scope="col">Step</th><th scope="col">Details</th><th scope="col" className="num">Duration</th></tr></thead>
            <tbody>
              {shown.map((r, i) => (
                <tr key={`${r.job.job_id}-${i}`}>
                  <td className="nowrap">{formatDateTime(r.event.started_at)}</td>
                  <td className="cell-name"><a href={detailHref(r.job.job_id, "reconciliation")} title={r.job.filename}>{r.job.filename}</a></td>
                  <td>{nodeLabel(r.event.node)}</td>
                  <td className="muted">{eventDetail(r.event)}</td>
                  <td className="num">{r.event.latency_ms.toFixed(1)} ms</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}
