import { screen, within } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { jobWith } from "./fixtures";
import { renderAt } from "./helpers";

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return { ...actual, uploadInvoice: vi.fn(), getJob: vi.fn(), listJobs: vi.fn(), getTrace: vi.fn() };
});
import { listJobs } from "../api/client";

beforeEach(() => { vi.mocked(listJobs).mockResolvedValue([]); });

describe("DashboardView", () => {
  it("shows a loading state, then an empty state with a route to Upload (Review Focus 1)", async () => {
    renderAt("#/");
    expect(screen.getByRole("status", { name: "Loading" })).toBeInTheDocument();
    expect(await screen.findByRole("heading", { name: "No invoices yet" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Upload an invoice" })).toHaveAttribute("href", "#/upload");
    expect(document.body.textContent).not.toMatch(/NaN/);
  });
  it("summarises counts and the reconciliation rate from real jobs", async () => {
    vi.mocked(listJobs).mockResolvedValue([
      jobWith("a", "RECONCILED"), jobWith("b", "RECONCILED"), jobWith("c", "RECONCILED"),
      jobWith("d", "UNRESOLVED"), jobWith("e", "FAILED"), jobWith("f", null),
    ]);
    renderAt("#/");
    const strip = await screen.findByRole("group", { name: "Invoice summary" });
    expect(within(strip).getByText("6")).toBeInTheDocument();            // total
    expect(within(strip).getByText("3")).toBeInTheDocument();            // reconciled
    expect(screen.getByText("60%")).toBeInTheDocument();                 // 3 of 5 finished
    expect(screen.getByRole("img", { name: /Invoices per day/ })).toBeInTheDocument();
  });
  it("links each recent activity row to its detail page", async () => {
    vi.mocked(listJobs).mockResolvedValue([jobWith("a", "RECONCILED")]);
    renderAt("#/");
    expect(await screen.findByRole("link", { name: "a.pdf" })).toHaveAttribute("href", expect.stringMatching(/^#\/invoices\/a\/document$/));
  });
  it("tolerates a failed job without a result (Review Focus 2)", async () => {
    vi.mocked(listJobs).mockResolvedValue([{ ...jobWith("x", "RECONCILED"), state: "ERROR", result: null, error: "interrupted" }]);
    renderAt("#/");
    expect(await screen.findByRole("link", { name: "x.pdf" })).toBeInTheDocument();
    expect(screen.getAllByText("Failed").length).toBeGreaterThan(0);
  });
  it("shows an error with a retry when the list cannot load", async () => {
    vi.mocked(listJobs).mockRejectedValue(new Error("down"));
    renderAt("#/");
    expect(await screen.findByRole("alert")).toHaveTextContent("Could not load invoices from the server.");
  });
});
