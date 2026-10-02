import { screen, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { done, jobWith } from "./fixtures";
import { renderAt } from "./helpers";

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return { ...actual, uploadInvoice: vi.fn(), getJob: vi.fn(), listJobs: vi.fn(), getTrace: vi.fn() };
});
import { listJobs } from "../api/client";

const jobs = [jobWith("alpha", "RECONCILED"), jobWith("beta", "UNRESOLVED"), jobWith("gamma", null)];
beforeEach(() => { vi.mocked(listJobs).mockResolvedValue(jobs); });

describe("InvoicesView", () => {
  it("lists jobs with real status counts on the tabs", async () => {
    renderAt("#/invoices");
    expect(await screen.findByRole("tab", { name: /^All\s*3/ })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /^Reconciled\s*1/ })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /^Needs review\s*1/ })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /^Processing\s*1/ })).toBeInTheDocument();
    expect(screen.getByRole("tab", { name: /^Failed\s*0/ })).toBeInTheDocument();
  });
  it("filters by tab and by search text", async () => {
    renderAt("#/invoices");
    await userEvent.click(await screen.findByRole("tab", { name: /^Needs review/ }));
    const table = screen.getByRole("table");
    expect(within(table).getByRole("link", { name: "beta.pdf" })).toBeInTheDocument();
    expect(within(table).queryByRole("link", { name: "alpha.pdf" })).toBeNull();
    await userEvent.click(screen.getByRole("tab", { name: /^All/ }));
    await userEvent.type(screen.getByRole("searchbox", { name: "Search invoices" }), "alp");
    expect(within(screen.getByRole("table")).getAllByRole("row")).toHaveLength(2);   // header + alpha
  });
  it("says so when a filter matches nothing", async () => {
    renderAt("#/invoices");
    await userEvent.type(await screen.findByRole("searchbox", { name: "Search invoices" }), "zzz");
    expect(screen.getByText("No invoices match.")).toBeInTheDocument();
  });
  it("renders huge totals exactly and survives a 300-character filename (Review Focus 4)", async () => {
    const big = { ...done, job_id: "big", filename: "y".repeat(300) + ".pdf",
      result: { ...done.result!, ledger: { ...done.result!.ledger!, total: "123456789012345678901.50" } } };
    vi.mocked(listJobs).mockResolvedValue([big]);
    renderAt("#/invoices");
    expect(await screen.findByText(/123,456,789,012,345,678,901\.50/)).toBeInTheDocument();
  });
  it("shows an empty state when there are no invoices at all (Review Focus 1)", async () => {
    vi.mocked(listJobs).mockResolvedValue([]);
    renderAt("#/invoices");
    expect(await screen.findByRole("heading", { name: "No invoices yet" })).toBeInTheDocument();
  });
});
