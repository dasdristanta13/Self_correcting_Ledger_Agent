import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { jobWith } from "./fixtures";
import { render } from "@testing-library/react";
import { JobsProvider } from "../hooks/useJobs";
import { ReviewView } from "../views/ReviewView";
import { renderAt } from "./helpers";

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return { ...actual, uploadInvoice: vi.fn(), getJob: vi.fn(), listJobs: vi.fn(), getTrace: vi.fn() };
});
import { listJobs } from "../api/client";

const err = { ...jobWith("svc", "RECONCILED"), state: "ERROR" as const, result: null, error: "interrupted" };
beforeEach(() => {
  vi.mocked(listJobs).mockResolvedValue([
    jobWith("ok1", "RECONCILED"), jobWith("un", "UNRESOLVED"), jobWith("na", "NO_PROGRESS"), jobWith("ie", "INSUFFICIENT_EVIDENCE"), err, jobWith("run", null),
  ]);
});

describe("ReviewView", () => {
  it("lists only jobs that need a human, with stop reason and derived priority", async () => {
    renderAt("#/review");
    const table = await screen.findByRole("table");
    const rows = within(table).getAllByRole("row").slice(1);
    expect(rows).toHaveLength(4);                                   // un, na, ie, svc; not ok1 or run
    expect(within(table).queryByRole("link", { name: "ok1.pdf" })).toBeNull();
    const un = within(table).getByRole("link", { name: "un.pdf" }).closest("tr")!;
    expect(within(un).getByText("UNRESOLVED")).toBeInTheDocument();
    expect(within(un).getByText("High")).toBeInTheDocument();
    expect(within(within(table).getByRole("link", { name: "ie.pdf" }).closest("tr")!).getByText("Low")).toBeInTheDocument();
  });
  it("filters by stop reason", async () => {
    renderAt("#/review");
    await userEvent.click(await screen.findByRole("tab", { name: /^No progress/ }));
    expect(within(screen.getByRole("table")).getAllByRole("row")).toHaveLength(2);
  });
  it("shows a positive empty state when nothing needs review (Review Focus 1)", async () => {
    vi.mocked(listJobs).mockResolvedValue([jobWith("a", "RECONCILED")]);
    renderAt("#/review");
    expect(await screen.findByRole("heading", { name: "Nothing needs review" })).toBeInTheDocument();
  });
  it("falls back to All when the selected stop reason disappears after a refresh", async () => {
    vi.mocked(listJobs).mockResolvedValue([jobWith("un", "UNRESOLVED"), jobWith("na", "NO_PROGRESS"), jobWith("run", null)]);
    render(<JobsProvider pollMs={30}><ReviewView /></JobsProvider>);
    await userEvent.click(await screen.findByRole("tab", { name: /^No progress/ }));
    vi.mocked(listJobs).mockResolvedValue([jobWith("un", "UNRESOLVED"), jobWith("run", null)]);
    await waitFor(() => expect(screen.queryByRole("tab", { name: /^No progress/ })).toBeNull());
    expect(screen.getByRole("tab", { name: /^All/ })).toHaveAttribute("aria-selected", "true");
    expect(within(screen.getByRole("table")).getAllByRole("row")).toHaveLength(2);
  });
  it("invites an upload instead of claiming success when there are no jobs at all", async () => {
    vi.mocked(listJobs).mockResolvedValue([]);
    renderAt("#/review");
    expect(await screen.findByRole("heading", { name: "No invoices yet" })).toBeInTheDocument();
    expect(screen.getByRole("link", { name: "Upload an invoice" })).toHaveAttribute("href", "#/upload");
    expect(screen.queryByText("Nothing needs review")).toBeNull();
  });
  it("wires the active tab to an existing tabpanel", async () => {
    renderAt("#/review");
    const tab = await screen.findByRole("tab", { name: /^All/ });
    const panel = document.getElementById(tab.getAttribute("aria-controls")!);
    expect(panel).not.toBeNull();
    expect(panel).toHaveAttribute("role", "tabpanel");
  });
});
