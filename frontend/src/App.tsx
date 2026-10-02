import { useCallback, useEffect, useState } from "react";
import { ApiError, listJobs, uploadInvoice } from "./api/client";
import type { Job } from "./api/types";
import { DropZone } from "./components/DropZone";
import { RecentJobs } from "./components/RecentJobs";
import { ResultView } from "./components/ResultView";
import { useJob } from "./hooks/useJob";

export default function App() {
  const [jobId, setJobId] = useState<string | null>(null);
  const [uploadPct, setUploadPct] = useState<number | null>(null);
  const [uploadError, setUploadError] = useState<string | null>(null);
  const [recent, setRecent] = useState<Job[]>([]);
  const { job, error: pollError } = useJob(jobId);

  const refresh = useCallback(() => { listJobs().then(setRecent).catch(() => undefined); }, []);
  useEffect(refresh, [refresh]);
  useEffect(() => { if (job?.state === "DONE" || job?.state === "ERROR") refresh(); }, [job?.state, refresh]);

  const working = job?.state === "QUEUED" || job?.state === "RUNNING";
  const busy = uploadPct !== null || working;

  async function handleFile(file: File) {
    setUploadError(null);
    setJobId(null);
    setUploadPct(0);
    try {
      const r = await uploadInvoice(file, setUploadPct);
      setJobId(r.job_id);
    } catch (e) {
      setUploadError(e instanceof ApiError ? e.message : "Upload failed. Check your connection and try again.");
    } finally {
      setUploadPct(null);
    }
  }

  return (
    <main className="page">
      <header className="masthead">
        <h1>Ledger Agent</h1>
        <p className="lede">Drop an invoice. Get a reconciled ledger and the evidence behind every correction.</p>
      </header>
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
        {pollError && !job && <p role="alert" className="field-error">Lost contact with the server. Retrying.</p>}
      </div>
      {job && <ResultView job={job} />}
      <RecentJobs jobs={recent} selected={jobId} onSelect={setJobId} />
    </main>
  );
}
