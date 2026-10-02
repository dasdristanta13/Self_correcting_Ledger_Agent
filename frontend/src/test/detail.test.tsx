import { render, screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { TraceEvent } from "../api/types";
import { AgentTimeline } from "../components/AgentTimeline";
import { done } from "./fixtures";
import { renderAt } from "./helpers";

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return { ...actual, uploadInvoice: vi.fn(), getJob: vi.fn(), listJobs: vi.fn(), getTrace: vi.fn() };
});
import { ApiError, getJob, getTrace, listJobs } from "../api/client";

const ev = (node: string, n: number, detail: Record<string, unknown> = {}): TraceEvent =>
  ({ run_id: "r", invoice_id: "INV-001", node, revision: 0, started_at: `2026-10-02T09:00:0${n}Z`, latency_ms: 1.5, status: "OK", detail });
const trace = [ev("ingest", 0), ev("validate", 1, { discrepancies: ["items[line_01].amount"] }), ev("reconcile", 2), ev("validate", 3, { discrepancies: [] })];
const url = `#/invoices/${done.job_id}`;

beforeEach(() => {
  vi.mocked(listJobs).mockResolvedValue([done]);
  vi.mocked(getJob).mockResolvedValue(done);
  vi.mocked(getTrace).mockResolvedValue(trace);
});

describe("InvoiceDetailView", () => {
  it("shows the header and the document tab by default, with the correction marked", async () => {
    renderAt(`${url}/document`);
    expect(await screen.findByRole("heading", { level: 1, name: /^INV-001\.pdf/ })).toBeInTheDocument();
    expect(screen.getAllByText("Reconciled").length).toBeGreaterThan(0);
    expect(screen.getByRole("tab", { name: "Document" })).toHaveAttribute("aria-selected", "true");
    expect(screen.getAllByText("1,040.00")[0].tagName).toBe("DEL");
    expect(screen.getByRole("link", { name: /Back to invoices/ })).toHaveAttribute("href", "#/invoices");
  });
  it("switches tabs through the URL", async () => {
    renderAt(`${url}/document`);
    await userEvent.click(await screen.findByRole("tab", { name: "Extracted data" }));
    expect(window.location.hash).toBe(`${url}/extracted`);
    expect(await screen.findByRole("table", { name: /Extracted line items/ })).toBeInTheDocument();
    expect(screen.getByText("Corrected")).toBeInTheDocument();           // line_01.amount differs from the final ledger
  });
  it("renders the reconciliation tab: mismatch summary, timeline and detail tabs", async () => {
    renderAt(`${url}/reconciliation`);
    expect(await screen.findByText("Resolved")).toBeInTheDocument();
    const timeline = await screen.findByRole("list", { name: "Agent activity" });
    expect(within(timeline).getAllByRole("listitem")).toHaveLength(4);
    expect(within(timeline).getAllByText("Validate arithmetic")).toHaveLength(2);
    await userEvent.click(screen.getByRole("tab", { name: "Evidence" }));
    expect(screen.getByText(/Industrial Filter/)).toBeInTheDocument();
    await userEvent.click(screen.getByRole("tab", { name: "Validation" }));
    expect(await screen.findByText("All checks passed")).toBeInTheDocument();
    await userEvent.click(screen.getByRole("tab", { name: "Raw extraction" }));
    expect(screen.getByText(/"invoice_id": "INV-001"/)).toBeInTheDocument();
  });
  it("explains an unknown job in-shell (Review Focus 3)", async () => {
    vi.mocked(getJob).mockRejectedValue(new ApiError("not_found", "No such job.", 404));
    renderAt("#/invoices/ghost/document");
    expect(await screen.findByRole("heading", { name: "Invoice not found" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Back to invoices" })).toHaveAttribute("href", "#/invoices");
  });
  it("shows progress for a job that is still running", async () => {
    vi.mocked(getJob).mockResolvedValue({ ...done, state: "RUNNING", result: null, finished_at: null });
    renderAt(`${url}/document`);
    expect(await screen.findByText(/Reconciling INV-001\.pdf/)).toBeInTheDocument();
  });
  it("explains a service ERROR distinctly and still offers the trace (Review Focus 2)", async () => {
    vi.mocked(getJob).mockResolvedValue({ ...done, state: "ERROR", result: null, error: "interrupted by restart" });
    renderAt(`${url}/reconciliation`);
    expect(await screen.findByRole("alert")).toHaveTextContent(/interrupted by restart/);
  });
  it("handles a FAILED invoice that has no ledger", async () => {
    vi.mocked(getJob).mockResolvedValue({ ...done, result: { ...done.result!, status: "FAILED", ledger: null, original_ledger: null, corrections: [], evidence: [], error: "no tables" } });
    renderAt(`${url}/document`);
    expect(await screen.findByText("Could not read")).toBeInTheDocument();
    expect(screen.getByText(/no ledger was produced/i)).toBeInTheDocument();
  });
  it("replays the agent trace one step at a time", async () => {
    renderAt(`${url}/reconciliation`);
    await screen.findByRole("list", { name: "Agent activity" });
    await userEvent.click(screen.getByRole("button", { name: "Replay agent" }));
    await waitFor(() => expect(within(screen.getByRole("list", { name: "Agent activity" })).queryAllByRole("listitem").length).toBeLessThan(4));
    await waitFor(() => expect(within(screen.getByRole("list", { name: "Agent activity" })).getAllByRole("listitem")).toHaveLength(4), { timeout: 4000 });
  });
  it("does not re-run the replay when returning to the reconciliation tab", async () => {
    renderAt(`${url}/reconciliation`);
    const first = await screen.findByRole("list", { name: "Agent activity" });
    expect(within(first).getAllByRole("listitem")).toHaveLength(4);
    await userEvent.click(screen.getByRole("button", { name: "Replay agent" }));
    await userEvent.click(screen.getByRole("tab", { name: "Document" }));
    await userEvent.click(await screen.findByRole("tab", { name: "Reconciliation" }));
    const again = await screen.findByRole("list", { name: "Agent activity" });
    expect(within(again).getAllByRole("listitem")).toHaveLength(4);
  });
});

describe("AgentTimeline", () => {
  it("reveals events step by step when replayed and settles on all of them", async () => {
    vi.mocked(getTrace).mockResolvedValue(trace.slice(0, 3));
    render(<AgentTimeline jobId="j" replayKey={1} stepMs={300} />);
    const count = () => screen.queryAllByRole("listitem").length;
    await waitFor(() => expect(count()).toBe(1), { timeout: 1500 });
    await waitFor(() => expect(count()).toBe(3), { timeout: 2500 });
  });
  it("shows an empty message when no trace was recorded", async () => {
    vi.mocked(getTrace).mockResolvedValue([]);
    render(<AgentTimeline jobId="j" replayKey={0} />);
    expect(await screen.findByText("No trace was recorded for this job.")).toBeInTheDocument();
  });
});
