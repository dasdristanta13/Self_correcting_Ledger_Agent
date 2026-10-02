import type { Job, TraceEvent } from "./types";

export class ApiError extends Error {
  constructor(public code: string, message: string, public status: number) {
    super(message);
  }
}

const BASE = (import.meta.env.VITE_API_BASE as string | undefined) ?? "";

async function parse<T>(res: Response): Promise<T> {
  if (res.ok) return (await res.json()) as T;
  let code = "http_error", message = `Request failed (${res.status}).`;
  try {
    const body = await res.json();
    if (body && typeof body.message === "string") { code = body.code ?? code; message = body.message; }
  } catch { /* non-JSON error body */ }
  throw new ApiError(code, message, res.status);
}

export const getJob = (id: string) => fetch(`${BASE}/api/invoices/${id}`).then((r) => parse<Job>(r));
export const listJobs = (limit = 20) => fetch(`${BASE}/api/invoices?limit=${limit}`).then((r) => parse<Job[]>(r));
export const getTrace = (id: string) =>
  fetch(`${BASE}/api/invoices/${id}/trace`).then((r) => parse<TraceEvent[]>(r));

export const UPLOAD_TIMEOUT_MS = 120_000;

const FALLBACK_MESSAGES: Record<number, [string, string]> = {
  413: ["too_large", "That file is too large for the server. Try a smaller PDF."],
  415: ["not_a_pdf", "The server did not accept that file as a PDF."],
};

export function uploadInvoice(file: File, onProgress?: (pct: number) => void,
  timeoutMs: number = UPLOAD_TIMEOUT_MS): Promise<{ job_id: string; status: string }> {
  return new Promise((resolve, reject) => {
    const xhr = new XMLHttpRequest();
    xhr.open("POST", `${BASE}/api/invoices`);
    xhr.timeout = timeoutMs;
    xhr.upload.onprogress = (e) => { if (e.lengthComputable && onProgress) onProgress(Math.round((e.loaded / e.total) * 100)); };
    xhr.onerror = () => reject(new ApiError("network", "Could not reach the server. Check your connection and try again.", 0));
    xhr.ontimeout = () => reject(new ApiError("timeout", "The upload took too long and was stopped. Check your connection and try again.", 0));
    xhr.onabort = () => reject(new ApiError("aborted", "The upload was cancelled.", 0));
    xhr.onload = () => {
      let body: any = null;
      try { body = JSON.parse(xhr.responseText); } catch { /* ignore */ }
      if (xhr.status >= 200 && xhr.status < 300 && body?.job_id) resolve(body);
      else {
        const [fbCode, fbMsg] = FALLBACK_MESSAGES[xhr.status] ?? ["http_error", `Upload failed (${xhr.status}).`];
        reject(new ApiError(body?.code ?? fbCode, body?.message ?? fbMsg, xhr.status));
      }
    };
    const form = new FormData();
    form.append("file", file);
    xhr.send(form);
  });
}
