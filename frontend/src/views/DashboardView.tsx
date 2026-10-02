import { ActivityChart } from "../components/ActivityChart";
import { StatusBar } from "../components/StatusBar";
import { SummaryStrip } from "../components/SummaryStrip";
import { EmptyState } from "../components/ui/EmptyState";
import { StatusPill } from "../components/ui/Pill";
import { LoadingRows } from "../components/ui/Skeleton";
import { PageHeader } from "../components/ui/PageHeader";
import { useJobs } from "../hooks/useJobs";
import { correctionCount, countByKey, dailyBuckets, reconciliationRate, stopReason } from "../lib/derive";
import { formatTime } from "../lib/format";
import { statusCopy } from "../lib/status";
import { detailHref } from "../router";

export function DashboardView() {
  const { jobs, loading, error, refresh } = useJobs();
  const header = <PageHeader title="Dashboard" sub={`Reconciliation across your ${jobs.length || "most recent"} invoices.`}
    actions={<a className="btn btn-primary" href="#/upload">Upload invoice</a>} />;
  if (loading) return <>{header}<LoadingRows /></>;
  if (error && jobs.length === 0) {
    return (<>{header}<p role="alert" className="field-error">{error} <button type="button" className="btn" onClick={refresh}>Try again</button></p></>);
  }
  if (jobs.length === 0) {
    return (<>{header}<EmptyState title="No invoices yet" action={<a className="btn btn-primary" href="#/upload">Upload an invoice</a>}>
      Upload a PDF and the agent will extract, validate and reconcile it.</EmptyState></>);
  }
  const counts = countByKey(jobs);
  return (
    <>
      {header}
      <SummaryStrip counts={counts} rate={reconciliationRate(jobs)} />
      <div className="dash-grid">
        <section className="panel" aria-labelledby="dash-activity">
          <h2 id="dash-activity">Processing activity, last 14 days</h2>
          <ActivityChart buckets={dailyBuckets(jobs, 14, new Date())} />
        </section>
        <section className="panel" aria-labelledby="dash-mix">
          <h2 id="dash-mix">Status mix</h2>
          <StatusBar counts={counts} />
        </section>
      </div>
      <section className="panel" aria-labelledby="dash-recent">
        <div className="panel-head"><h2 id="dash-recent">Recent activity</h2><a href="#/invoices">View all</a></div>
        <div className="table-scroll" tabIndex={0} role="region" aria-label="Recent activity">
          <table className="data">
            <thead><tr><th scope="col">Time</th><th scope="col">Invoice</th><th scope="col">Status</th><th scope="col">Details</th></tr></thead>
            <tbody>
              {jobs.slice(0, 6).map((j) => (
                <tr key={j.job_id}>
                  <td>{formatTime(j.finished_at ?? j.created_at)}</td>
                  <td className="cell-name"><a href={detailHref(j.job_id)} title={j.filename}>{j.filename}</a></td>
                  <td><StatusPill job={j} /></td>
                  <td className="muted">{correctionCount(j) > 0 ? `${correctionCount(j)} correction${correctionCount(j) === 1 ? "" : "s"} applied` : statusCopy(stopReason(j)).hint}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>
    </>
  );
}
