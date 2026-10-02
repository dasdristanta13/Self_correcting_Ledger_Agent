import { useEffect, useState } from "react";
import { ApiError, uploadInvoice } from "../api/client";
import { DropZone } from "../components/DropZone";
import { RecentJobs } from "../components/RecentJobs";
import { ResultView } from "../components/ResultView";
import { PageHeader } from "../components/ui/PageHeader";
import { useJob, JOB_NOT_FOUND } from "../hooks/useJob";
import { useJobs } from "../hooks/useJobs";
import { detailHref, navigate } from "../router";

export function UploadView() {
  const { jobs, refresh } = useJobs();
  const [jobId, setJobId] = useState<string | null>(null);
  const [uploadPct, setUploadPct] = useState<number | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const { job, error: pollError } = useJob(jobId);

  useEffect(() => { if (job?.state === "DONE" || job?.state === "ERROR") refresh(); }, [job?.state, refresh]);

  const working = job?.state === "QUEUED" || job?.state === "RUNNING";
  const busy = uploadPct !== null || working;

  async function handleFile(file: File) {
    setUploadError(null);
    setJobId(null);
    setUploadPct(0);
    try {
      const r = await uploadInvoice(file, setUploadPct);
      refresh();
      setJobId(r.job_id);
    } catch (e) {
      setUploadError(e instanceof ApiError ? e.message : "Upload failed. Check your connection and try again.");
    } finally {
      setUploadPct(null);
    }
  }

  return (
    <>
      <PageHeader title="Upload invoice" sub="Drop a PDF to extract, validate and reconcile it automatically." />
      <DropZone onFile={handleFile} disabled={busy} />
      <div className="activity">
        {uploadPct !== null && (
          <div role="status" className="progress">
            <label>Uploading {uploadPct}% <progress max={100} value={uploadPct} /></label>
          </div>
        )}
        {working && (
          <div role="status" className="progress">
            <p>Reconciling {job?.filename}. This usually takes a few seconds.</p>
            <span className="working-bar" aria-hidden="true" />
          </div>
        )}
        {uploadError && <p role="alert" className="field-error">{uploadError}</p>}
        {pollError && !job && <p role="alert" className="field-error">{pollError === JOB_NOT_FOUND ? pollError : "Lost contact with the server. Retrying…"}</p>}
        {pollError && job && working && <p role="status" className="muted">Reconnecting…</p>}
      </div>
      {job && <ResultView job={job} />}
      <RecentJobs jobs={jobs.slice(0, 8)} selected={jobId} onSelect={(id) => navigate(detailHref(id))} />
    </>
  );
}
