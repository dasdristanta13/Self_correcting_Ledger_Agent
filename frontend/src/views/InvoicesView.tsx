import { useState } from "react";
import { EmptyState } from "../components/ui/EmptyState";
import { PageHeader } from "../components/ui/PageHeader";
import { StatusPill } from "../components/ui/Pill";
import { LoadingRows } from "../components/ui/Skeleton";
import { Tabs, tabIds } from "../components/ui/Tabs";
import { useJobs } from "../hooks/useJobs";
import { correctionCount, countByKey, filterJobs, type StatusKey } from "../lib/derive";
import { formatDate, formatMoney } from "../lib/format";
import { detailHref } from "../router";

export function InvoicesView() {
  const { jobs, loading, error, refresh } = useJobs();
  const [tab, setTab] = useState<StatusKey | "all">("all");
  const [q, setQ] = useState("");
  const header = <PageHeader title="Invoices" sub="Every invoice the agent has processed."
    actions={<a className="btn btn-primary" href="#/upload">Upload invoice</a>} />;
  if (loading) return <>{header}<LoadingRows /></>;
  if (error && jobs.length === 0) {
    return (<>{header}<p role="alert" className="field-error">{error} <button type="button" className="btn" onClick={refresh}>Try again</button></p></>);
  }
  if (jobs.length === 0) {
    return (<>{header}<EmptyState title="No invoices yet" action={<a className="btn btn-primary" href="#/upload">Upload an invoice</a>}>
      Processed invoices will appear here.</EmptyState></>);
  }
  const c = countByKey(jobs);
  const rows = filterJobs(jobs, tab, q);
  return (
    <>
      {header}
      <div className="toolbar">
        <Tabs label="Filter by status" value={tab} onChange={(id) => setTab(id as StatusKey | "all")} idBase="inv"
          tabs={[{ id: "all", label: "All", count: jobs.length }, { id: "ok", label: "Reconciled", count: c.ok },
            { id: "wn", label: "Needs review", count: c.wn }, { id: "in", label: "Processing", count: c.in }, { id: "er", label: "Failed", count: c.er }]} />
        <input type="search" className="search" aria-label="Search invoices" placeholder="Search invoices" value={q} onChange={(e) => setQ(e.target.value)} />
      </div>
      <section className="panel panel-flush" role="tabpanel" id={tabIds("inv", tab).panel} aria-labelledby={tabIds("inv", tab).tab}>
        {rows.length === 0 ? <p className="muted pad">No invoices match.</p> : (
          <div className="table-scroll" tabIndex={0} role="region" aria-label="Invoices table">
            <table className="data">
              <thead><tr><th scope="col">Invoice</th><th scope="col" className="num">Total</th><th scope="col">Date</th><th scope="col">Status</th><th scope="col" className="num">Corrections</th></tr></thead>
              <tbody>
                {rows.map((j) => {
                  const ledger = j.result?.ledger;
                  return (
                    <tr key={j.job_id}>
                      <td className="cell-name"><a href={detailHref(j.job_id)} title={j.filename}>{j.filename}</a>
                        {j.result?.invoice_id && <span className="muted cell-sub">{j.result.invoice_id}</span>}</td>
                      <td className="num">{ledger ? <>{formatMoney(ledger.total)} <span className="currency">{ledger.currency}</span></> : "—"}</td>
                      <td>{formatDate(j.created_at)}</td>
                      <td><StatusPill job={j} /></td>
                      <td className="num">{j.result ? correctionCount(j) : "—"}</td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </section>
    </>
  );
}
