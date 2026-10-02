import { useEffect, useRef, useState } from "react";
import { uploadInvoice } from "../api/client";
import type { Job } from "../api/types";
import { useJobs } from "../hooks/useJobs";
import { pollJob, runPool } from "../lib/queue";
import { validateFile } from "../lib/validate";
import { detailHref } from "../router";
import { DropZone } from "./DropZone";
import { StatusPill } from "./ui/Pill";

const MAX_FILES = 100;
const CONCURRENCY = 3;

type Stage = "ready" | "invalid" | "uploading" | "reconciling" | "done" | "failed";
interface Row { id: number; file: File; stage: Stage; pct: number; job?: Job; message?: string }

const mb = (bytes: number) => `${(bytes / 1048576).toFixed(1)} MB`;
const STAGE_TEXT: Record<Stage, string> = { ready: "Ready", invalid: "Not accepted", uploading: "Uploading", reconciling: "Reconciling", done: "Done", failed: "Failed" };

export function BulkUpload() {
  const { refresh } = useJobs();
  const [rows, setRows] = useState<Row[]>([]);
  const [running, setRunning] = useState(false);
  const [notice, setNotice] = useState<string | null>(null);
  const alive = useRef(true);
  const nextId = useRef(1);
  useEffect(() => { alive.current = true; return () => { alive.current = false; }; }, []);

  const patch = (id: number, p: Partial<Row>) => {
    if (alive.current) setRows((rs) => rs.map((r) => (r.id === id ? { ...r, ...p } : r)));
  };

  function add(files: File[]) {
    const room = Math.max(0, MAX_FILES - rows.length);
    const take = files.slice(0, room);
    setNotice(files.length > take.length ? `Only ${MAX_FILES} files can be queued at once. ${files.length - take.length} were skipped.` : null);
    setRows((rs) => [...rs, ...take.map((file): Row => {
      const problem = validateFile(file);
      return { id: nextId.current++, file, stage: problem ? "invalid" : "ready", pct: 0, message: problem ?? undefined };
    })]);
  }

  async function runAll() {
    const todo = rows.filter((r) => r.stage === "ready" || r.stage === "failed");
    if (todo.length === 0) return;
    setRunning(true);
    await runPool(todo, CONCURRENCY, async (r) => {
      patch(r.id, { stage: "uploading", pct: 0, message: undefined });
      try {
        const { job_id } = await uploadInvoice(r.file, (pct) => patch(r.id, { pct }));
        patch(r.id, { stage: "reconciling", pct: 100 });
        const job = await pollJob(job_id);
        patch(r.id, job.state === "ERROR"
          ? { stage: "failed", job, message: job.error ?? "Processing failed on the server." }
          : { stage: "done", job });
      } catch (e) {
        patch(r.id, { stage: "failed", message: e instanceof Error ? e.message : "Upload failed." });
      }
    });
    if (alive.current) { setRunning(false); refresh(); }
  }

  const complete = rows.filter((r) => r.stage === "done" || r.stage === "failed").length;
  const queued = rows.filter((r) => r.stage !== "invalid").length;

  return (
    <div>
      <DropZone multiple onFiles={add} disabled={running} />
      {notice && <p role="status" className="muted pad-top">{notice}</p>}
      {rows.length > 0 && (
        <section className="bulk" aria-label="Upload queue">
          <div className="bulk-head">
            <div><h2>{rows.length} {rows.length === 1 ? "file" : "files"}</h2><p className="muted">{complete} of {queued} finished</p></div>
            <div className="page-actions">
              <button type="button" className="btn" disabled={running} onClick={() => { setRows([]); setNotice(null); }}>Clear</button>
              <button type="button" className="btn btn-primary" disabled={running || !rows.some((r) => r.stage === "ready" || r.stage === "failed")} onClick={runAll}>Reconcile all</button>
            </div>
          </div>
          <progress className="bulk-progress" max={Math.max(queued, 1)} value={complete} aria-label="Overall progress" />
          <div className="table-scroll" tabIndex={0} role="region" aria-label="Queued files">
            <table className="data">
              <thead><tr><th scope="col">File</th><th scope="col">Size</th><th scope="col">Status</th><th scope="col">Result</th></tr></thead>
              <tbody>
                {rows.map((r) => (
                  <tr key={r.id}>
                    <td className="cell-name"><span className="file-name" title={r.file.name}>{r.file.name}</span></td>
                    <td className="num">{mb(r.file.size)}</td>
                    <td>{STAGE_TEXT[r.stage]}{r.stage === "uploading" ? ` ${r.pct}%` : ""}{r.message && <span className="muted cell-sub">{r.message}</span>}</td>
                    <td>{r.job && r.stage === "done" ? <a href={detailHref(r.job.job_id)} className="pill-link"><StatusPill job={r.job} /></a> : "—"}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      )}
    </div>
  );
}
