import { fireEvent, render, screen, waitFor, within } from "@testing-library/react";
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
  it("shows the server's message when the upload is rejected", async () => {
    vi.mocked(uploadInvoice).mockRejectedValue(new ApiError("too_large", "File exceeds the 20 MB limit.", 413));
    render(<App />);
    await userEvent.upload(screen.getByLabelText(/drop an invoice pdf/i), pdf());
    expect(await screen.findByRole("alert")).toHaveTextContent("File exceeds the 20 MB limit.");
  });
  it("lists recent jobs and opens one on click", async () => {
    vi.mocked(listJobs).mockResolvedValue([done]);
    render(<App />);
    const item = await screen.findByRole("button", { name: /INV-001\.pdf/ });
    await userEvent.click(item);
    expect(await screen.findByText("Reconciled")).toBeInTheDocument();
    expect(within(screen.getByRole("main")).getByRole("article")).toBeInTheDocument();
  });
});
