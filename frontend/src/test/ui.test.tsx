import { fireEvent, render, screen, waitFor } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import example from "@contracts/example-job.json";
import type { Job } from "../api/types";
import App from "../App";
import { DropZone } from "../components/DropZone";
import { ResultView } from "../components/ResultView";

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return { ...actual, uploadInvoice: vi.fn(), getJob: vi.fn(), listJobs: vi.fn(), getTrace: vi.fn() };
});
import { ApiError, getJob, getTrace, listJobs, uploadInvoice } from "../api/client";

const done = example as unknown as Job;
const pdf = () => new File(["%PDF-1.4"], "INV-001.pdf", { type: "application/pdf" });

describe("DropZone", () => {
  it("accepts a PDF chosen through the input", async () => {
    const onFile = vi.fn();
    render(<DropZone onFile={onFile} />);
    await userEvent.upload(screen.getByLabelText(/drop an invoice pdf/i), pdf());
    expect(onFile).toHaveBeenCalledOnce();
  });
  it("accepts a PDF dropped on the zone", () => {
    const onFile = vi.fn();
    render(<DropZone onFile={onFile} />);
    fireEvent.drop(screen.getByText(/drop an invoice pdf/i).closest("label")!, { dataTransfer: { files: [pdf()] } });
    expect(onFile).toHaveBeenCalledOnce();
  });
  it("rejects a non-PDF with a specific message and does not call onFile", async () => {
    const onFile = vi.fn();
    const user = userEvent.setup({ applyAccept: false });
    render(<DropZone onFile={onFile} />);
    await user.upload(screen.getByLabelText(/drop an invoice pdf/i), new File(["hi"], "notes.txt", { type: "text/plain" }));
    expect(await screen.findByRole("alert")).toHaveTextContent(/not a PDF/i);
    expect(onFile).not.toHaveBeenCalled();
  });
  it("ignores drops while disabled", () => {
    const onFile = vi.fn();
    render(<DropZone onFile={onFile} disabled />);
    fireEvent.drop(screen.getByText(/drop an invoice pdf/i).closest("label")!, { dataTransfer: { files: [pdf()] } });
    expect(onFile).not.toHaveBeenCalled();
  });
});

describe("ResultView", () => {
  it("shows status, the correction with provenance, and the struck-through old amount", () => {
    render(<ResultView job={done} />);
    expect(screen.getByText("Reconciled")).toBeInTheDocument();
    expect(screen.getAllByText("Page 1 · table_01 · Row 1 · confidence 97%").length).toBeGreaterThan(0);
    expect(screen.getAllByText("1,040.00")[0].tagName).toBe("DEL");
    expect(screen.getAllByText("1,014.00").some((n) => n.tagName === "INS")).toBe(true);
  });
  it.each(["UNRESOLVED", "MAX_REVISIONS_EXCEEDED", "INSUFFICIENT_EVIDENCE", "NO_PROGRESS", "FAILED"])(
    "renders terminal status %s", (status) => {
      const job = { ...done, result: { ...done.result!, status, corrections: [] } } as Job;
      render(<ResultView job={job} />);
      expect(document.querySelector(`[data-status="${status}"]`)).not.toBeNull();
    });
  it("handles an unknown status without crashing", () => {                       // Review Focus 5
    const job = { ...done, result: { ...done.result!, status: "SOMETHING_NEW" } } as Job;
    render(<ResultView job={job} />);
    expect(screen.getByText("SOMETHING_NEW")).toBeInTheDocument();
  });
  it("renders a 200-row ledger and a very long filename", () => {                // Review Focus 5
    const items = Array.from({ length: 200 }, (_, i) => ({ ...done.result!.ledger!.items[0], id: `line_${i + 1}`, description: `Part ${i}` }));
    const job = { ...done, filename: "x".repeat(300) + ".pdf",
      result: { ...done.result!, corrections: [], ledger: { ...done.result!.ledger!, items } } } as Job;
    render(<ResultView job={job} />);
    expect(screen.getAllByRole("row").length).toBeGreaterThan(200);
  });
  it("shows money larger than JS safe integers exactly", () => {                  // Review Focus 5
    const ledger = { ...done.result!.ledger!, total: "123456789012345678901.50" };
    render(<ResultView job={{ ...done, result: { ...done.result!, corrections: [], ledger } } as Job} />);
    expect(screen.getByText(/123,456,789,012,345,678,901\.50/)).toBeInTheDocument();
  });
  it("explains a service ERROR distinctly from a FAILED invoice", () => {
    render(<ResultView job={{ ...done, state: "ERROR", result: null, error: "interrupted by restart" }} />);
    expect(screen.getByRole("alert")).toHaveTextContent(/interrupted by restart/);
    expect(screen.getByText("Trace")).toBeInTheDocument();           // the trace is most useful after an ERROR
  });
  it("labels the tax line with an exact percentage and hides 'was' text from sighted users only via CSS", () => {
    render(<ResultView job={done} />);
    expect(screen.getByText("Tax 10%")).toBeInTheDocument();
    const del = document.querySelector("del")!;
    expect(del.getAttribute("aria-label")).toBeNull();
    expect(del.querySelector(".visually-hidden")).toHaveTextContent("was");
  });
  it("loads the trace only when the disclosure is opened", async () => {
    vi.mocked(getTrace).mockResolvedValue([{ run_id: "r", invoice_id: "INV-001", node: "ingest", revision: 0,
      started_at: "t", latency_ms: 1.5, status: "INGESTED", detail: {} }]);
    render(<ResultView job={done} />);
    expect(getTrace).not.toHaveBeenCalled();
    const summary = screen.getByText("Trace");
    fireEvent.click(summary);
    fireEvent(summary.closest("details")!, new Event("toggle"));
    await waitFor(() => expect(getTrace).toHaveBeenCalledWith(done.job_id));
  });
});

describe("App", () => {
  beforeEach(() => {
    window.location.hash = "#/upload";
    vi.mocked(listJobs).mockResolvedValue([]);
    vi.mocked(getJob).mockResolvedValue(done);
    vi.mocked(uploadInvoice).mockReset();
  });
  it("uploads a dropped PDF, polls the job and shows the result", async () => {
    vi.mocked(uploadInvoice).mockResolvedValue({ job_id: done.job_id, status: "QUEUED" });
    render(<App />);
    await userEvent.upload(screen.getByLabelText(/drop an invoice pdf/i), pdf());
    expect(await screen.findByText("Reconciled")).toBeInTheDocument();
    expect(uploadInvoice).toHaveBeenCalledOnce();
  });
  it("refreshes the shared jobs list after a successful upload", async () => {
    vi.mocked(uploadInvoice).mockResolvedValue({ job_id: done.job_id, status: "QUEUED" });
    vi.mocked(getJob).mockReturnValue(new Promise(() => {}));   // job never completes, so only the upload triggers a refresh
    render(<App />);
    const initial = vi.mocked(listJobs).mock.calls.length;
    await userEvent.upload(screen.getByLabelText(/drop an invoice pdf/i), pdf());
    await waitFor(() => expect(vi.mocked(listJobs).mock.calls.length).toBeGreaterThan(initial));
    expect(uploadInvoice).toHaveBeenCalledOnce();
  });
  it("shows the server's message when the upload is rejected", async () => {
    vi.mocked(uploadInvoice).mockRejectedValue(new ApiError("too_large", "File exceeds the 20 MB limit.", 413));
    render(<App />);
    await userEvent.upload(screen.getByLabelText(/drop an invoice pdf/i), pdf());
    expect(await screen.findByRole("alert")).toHaveTextContent("File exceeds the 20 MB limit.");
  });
  it("re-enables the drop zone after an upload timeout", async () => {
    vi.mocked(uploadInvoice).mockRejectedValue(new ApiError("timeout", "The upload took too long and was stopped.", 0));
    render(<App />);
    const input = screen.getByLabelText(/drop an invoice pdf/i);
    await userEvent.upload(input, pdf());
    expect(await screen.findByRole("alert")).toHaveTextContent(/too long/i);
    expect(screen.getByLabelText(/drop an invoice pdf/i)).not.toBeDisabled();
  });
  it("shows a Reconnecting hint when polling fails mid-job", async () => {
    const running = { ...done, state: "RUNNING", result: null } as Job;
    vi.mocked(getJob).mockResolvedValueOnce(running).mockRejectedValue(new Error("offline"));
    vi.mocked(uploadInvoice).mockResolvedValue({ job_id: done.job_id, status: "QUEUED" });
    render(<App />);
    await userEvent.upload(screen.getByLabelText(/drop an invoice pdf/i), pdf());
    expect(await screen.findByText("Reconnecting…", {}, { timeout: 4000 })).toBeInTheDocument();
  });
  it("shows a friendly message, not the raw network error, before a job loads", async () => {
    vi.mocked(getJob).mockRejectedValue(new TypeError("Failed to fetch"));
    vi.mocked(uploadInvoice).mockResolvedValue({ job_id: "j9", status: "QUEUED" });
    render(<App />);
    await userEvent.upload(screen.getByLabelText(/drop an invoice pdf/i), pdf());
    const alert = await screen.findByRole("alert");
    expect(alert).toHaveTextContent("Lost contact with the server. Retrying…");
    expect(alert).not.toHaveTextContent(/Failed to fetch/);
  });
  it("keeps the specific message when the job is unknown (404)", async () => {
    vi.mocked(getJob).mockRejectedValue(new ApiError("not_found", "No such job.", 404));
    vi.mocked(uploadInvoice).mockResolvedValue({ job_id: "j9", status: "QUEUED" });
    render(<App />);
    await userEvent.upload(screen.getByLabelText(/drop an invoice pdf/i), pdf());
    expect(await screen.findByRole("alert")).toHaveTextContent("That job no longer exists.");
  });
  it("lists recent jobs and opens one in the detail route on click", async () => {
    vi.mocked(listJobs).mockResolvedValue([done]);
    render(<App />);
    await userEvent.click(await screen.findByRole("button", { name: /INV-001\.pdf/ }));
    expect(window.location.hash).toBe(`#/invoices/${done.job_id}/document`);
  });
});
