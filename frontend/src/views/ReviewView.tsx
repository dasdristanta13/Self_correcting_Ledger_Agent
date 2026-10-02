import { useState } from "react";
import { EmptyState } from "../components/ui/EmptyState";
import { PageHeader } from "../components/ui/PageHeader";
import { Pill } from "../components/ui/Pill";
import { LoadingRows } from "../components/ui/Skeleton";
import { Tabs, tabIds } from "../components/ui/Tabs";
import { useJobs } from "../hooks/useJobs";
import { needsReview, priorityOf, stopReason, type Priority } from "../lib/derive";
import { formatDateTime, formatMoney } from "../lib/format";
import { statusCopy } from "../lib/status";
import { detailHref } from "../router";

const PRIORITY_TONE = { High: "er", Medium: "wn", Low: "in" } as const satisfies Record<Priority, "er" | "wn" | "in">;

export function ReviewView() {
  const { jobs, loading, error, refresh } = useJobs();
  const [reason, setReason] = useState("all");
  const header = <PageHeader title="Needs review" sub="Invoices a person should look at: the agent stopped before everything reconciled." />;
  if (loading) return <>{header}<LoadingRows /></>;
  if (error && jobs.length === 0) {
    return (<>{header}<p role="alert" className="field-error">{error} <button type="button" className="btn" onClick={refresh}>Try again</button></p></>);
  }
  if (jobs.length === 0) {
    return (<>{header}<EmptyState title="No invoices yet" action={<a className="btn btn-primary" href="#/upload">Upload an invoice</a>}>Upload an invoice and anything the agent could not reconcile will appear here.</EmptyState></>);
  }
  const queue = needsReview(jobs);
  if (queue.length === 0) {
    return (<>{header}<EmptyState title="Nothing needs review">Every processed invoice reconciled.</EmptyState></>);
  }
  const reasons = [...new Set(queue.map(stopReason))];
  const active = reasons.includes(reason) ? reason : "all";
  const rows = active === "all" ? queue : queue.filter((j) => stopReason(j) === active);
  return (
    <>
      {header}
      <Tabs label="Filter by stop reason" value={active} onChange={setReason} idBase="rev"
        tabs={[{ id: "all", label: "All", count: queue.length },
          ...reasons.map((r) => ({ id: r, label: statusCopy(r).label, count: queue.filter((j) => stopReason(j) === r).length }))]} />
      <div role="tabpanel" id={tabIds("rev", active).panel} aria-labelledby={tabIds("rev", active).tab}>
      <section className="panel panel-flush">
        <div className="table-scroll" tabIndex={0} role="region" aria-label="Review queue">
          <table className="data">
            <thead><tr><th scope="col">Invoice</th><th scope="col" className="num">Total</th><th scope="col">Issue</th><th scope="col">Stop reason</th><th scope="col">Priority</th><th scope="col">Updated</th></tr></thead>
            <tbody>
              {rows.map((j) => {
                const code = stopReason(j);
                const total = j.result?.ledger?.total;
                const p = priorityOf(j);
                return (
                  <tr key={j.job_id}>
                    <td className="cell-name"><a href={detailHref(j.job_id)} title={j.filename}>{j.filename}</a></td>
                    <td className="num">{total ? formatMoney(total) : "—"}</td>
                    <td className="cell-issue">{statusCopy(code).hint}</td>
                    <td><code className="code-pill">{code}</code></td>
                    <td><Pill tone={PRIORITY_TONE[p]}>{p}</Pill></td>
                    <td>{formatDateTime(j.finished_at ?? j.created_at)}</td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </div>
      </section>
      <p className="muted note">Priority is a rule of thumb derived from the stop reason, not a stored field.</p>
      </div>
    </>
  );
}
