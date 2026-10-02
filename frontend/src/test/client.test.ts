import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, UPLOAD_TIMEOUT_MS, uploadInvoice } from "../api/client";

class FakeXHR {
  static last: FakeXHR;
  timeout = 0;
  status = 0;
  responseText = "";
  upload: { onprogress: ((e: unknown) => void) | null } = { onprogress: null };
  onload: (() => void) | null = null;
  onerror: (() => void) | null = null;
  ontimeout: (() => void) | null = null;
  onabort: (() => void) | null = null;
  method = "";
  url = "";
  constructor() { FakeXHR.last = this; }
  open(method: string, url: string) { this.method = method; this.url = url; }
  send() { /* the test drives the outcome */ }
  respond(status: number, text: string) { this.status = status; this.responseText = text; this.onload?.(); }
}

const file = () => new File(["%PDF-1.4"], "a.pdf", { type: "application/pdf" });
const failure = async (p: Promise<unknown>) => (await p.then(() => null, (e) => e)) as ApiError;

beforeEach(() => vi.stubGlobal("XMLHttpRequest", FakeXHR));
afterEach(() => vi.unstubAllGlobals());

describe("uploadInvoice", () => {
  it("resolves with the job id and sets the default timeout", async () => {
    const p = uploadInvoice(file());
    expect(FakeXHR.last.timeout).toBe(UPLOAD_TIMEOUT_MS);
    FakeXHR.last.respond(202, JSON.stringify({ job_id: "j1", status: "QUEUED" }));
    expect(await p).toEqual({ job_id: "j1", status: "QUEUED" });
  });
  it("lets the caller override the timeout", () => {
    void uploadInvoice(file(), undefined, 5000);
    expect(FakeXHR.last.timeout).toBe(5000);
  });
  it("rejects with a network error", async () => {
    const p = failure(uploadInvoice(file()));
    FakeXHR.last.onerror?.();
    const e = await p;
    expect(e).toBeInstanceOf(ApiError);
    expect(e.code).toBe("network");
  });
  it("rejects with a timeout error", async () => {
    const p = failure(uploadInvoice(file()));
    FakeXHR.last.ontimeout?.();
    const e = await p;
    expect(e.code).toBe("timeout");
    expect(e.message).toMatch(/too long/i);
  });
  it("rejects with an aborted error", async () => {
    const p = failure(uploadInvoice(file()));
    FakeXHR.last.onabort?.();
    const e = await p;
    expect(e.code).toBe("aborted");
    expect(e.message).toMatch(/cancelled/i);
  });
  it("uses the JSON body of a 413", async () => {
    const p = failure(uploadInvoice(file()));
    FakeXHR.last.respond(413, JSON.stringify({ code: "too_large", message: "File exceeds the 20 MB limit." }));
    const e = await p;
    expect([e.code, e.message, e.status]).toEqual(["too_large", "File exceeds the 20 MB limit.", 413]);
  });
  it("falls back to a specific message for a non-JSON 413", async () => {
    const p = failure(uploadInvoice(file()));
    FakeXHR.last.respond(413, "<html>Request Entity Too Large</html>");
    const e = await p;
    expect(e.code).toBe("too_large");
    expect(e.message).toMatch(/too large/i);
  });
  it("falls back to a specific message for a non-JSON 415", async () => {
    const p = failure(uploadInvoice(file()));
    FakeXHR.last.respond(415, "nope");
    const e = await p;
    expect(e.code).toBe("not_a_pdf");
    expect(e.message).toMatch(/PDF/);
  });
});
