import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import type { TraceEvent } from "../api/types";
import { jobWith } from "./fixtures";
import { render } from "@testing-library/react";
import { JobsProvider } from "../hooks/useJobs";
import { AuditView } from "../views/AuditView";
import { renderAt } from "./helpers";

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return { ...actual, uploadInvoice: vi.fn(), getJob: vi.fn(), listJobs: vi.fn(), getTrace: vi.fn() };
});
import { getTrace, listJobs } from "../api/client";

const ev = (node: string, at: string, detail: Record<string, unknown> = {}): TraceEvent =>
  ({ run_id: "r", invoice_id: "i", node, revision: 0, started_at: at, latency_ms: 2.5, status: "OK", detail });

beforeEach(() => {
  vi.mocked(listJobs).mockResolvedValue([jobWith("a", "RECONCILED"), jobWith("b", "UNRESOLVED")]);
  vi.mocked(getTrace).mockImplementation(async (id) =>
    id === "a" ? [ev("ingest", "2026-10-02T09:00:00Z"), ev("validate", "2026-10-02T09:00:02Z", { discrepancies: ["x"] })]
      : [ev("audit", "2026-10-02T09:05:00Z")]);
});

describe("AuditView", () => {
  it("merges trace events from recent jobs, newest first, with readable labels", async () => {
    renderAt("#/audit");
    const table = await screen.findByRole("table");
    await within(table).findByText("Search for evidence");
    const labels = within(table).getAllByRole("row").slice(1).map((r) => within(r).getAllByRole("cell")[2].textContent);
    expect(labels).toEqual(["Search for evidence", "Validate arithmetic", "Read document"]);
    expect(within(table).getByText("1 discrepancy")).toBeInTheDocument();
  });
  it("filters by invoice", async () => {
    renderAt("#/audit");
    await screen.findByText("Search for evidence");
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Invoice" }), "a");
    expect(within(screen.getByRole("table")).getAllByRole("row")).toHaveLength(3);
  });
  it("reports traces that could not be loaded without hiding the rest", async () => {
    vi.mocked(getTrace).mockImplementation(async (id) => { if (id === "b") throw new Error("nope"); return [ev("ingest", "2026-10-02T09:00:00Z")]; });
    renderAt("#/audit");
    expect(await screen.findByText(/1 invoice trace could not be loaded/)).toBeInTheDocument();
    expect(screen.getByText("Read document")).toBeInTheDocument();
  });
  it("shows an empty state with no jobs (Review Focus 1)", async () => {
    vi.mocked(listJobs).mockResolvedValue([]);
    renderAt("#/audit");
    expect(await screen.findByRole("heading", { name: "No activity yet" })).toBeInTheDocument();
  });
  it("shows an error with retry when jobs fail to load, not the empty state", async () => {
    vi.mocked(listJobs).mockRejectedValue(new Error("down"));
    renderAt("#/audit");
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not load invoices from the server.");
    expect(screen.getByRole("button", { name: "Try again" })).toBeInTheDocument();
    expect(screen.queryByRole("heading", { name: "No activity yet" })).toBeNull();
  });
  it("falls back to all invoices when the selected invoice disappears after a refresh", async () => {
    vi.mocked(listJobs).mockResolvedValue([jobWith("a", "RECONCILED"), jobWith("b", "UNRESOLVED"), jobWith("run", null)]);
    render(<JobsProvider pollMs={30}><AuditView /></JobsProvider>);
    await userEvent.selectOptions(await screen.findByRole("combobox", { name: "Invoice" }), "b");
    vi.mocked(listJobs).mockResolvedValue([jobWith("a", "RECONCILED"), jobWith("run", null)]);
    await waitFor(() => expect(screen.queryByRole("option", { name: "b.pdf" })).toBeNull());
    expect(screen.getByRole("combobox", { name: "Invoice" })).toHaveValue("all");
    expect(within(screen.getByRole("table")).getAllByRole("row").length).toBeGreaterThan(1);
  });
  it("offers a retry when every trace failed to load", async () => {
    vi.mocked(getTrace).mockRejectedValue(new Error("nope"));
    renderAt("#/audit");
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not load agent activity.");
    vi.mocked(getTrace).mockResolvedValue([ev("ingest", "2026-10-02T09:00:00Z")]);
    await userEvent.click(screen.getByRole("button", { name: "Try again" }));
    expect(await screen.findByRole("table")).toBeInTheDocument();
    expect(screen.getAllByText("Read document").length).toBeGreaterThan(0);
  });
});
