import { screen, waitFor, within } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { jobWith } from "./fixtures";
import { renderAt } from "./helpers";

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return { ...actual, uploadInvoice: vi.fn(), getJob: vi.fn(), listJobs: vi.fn(), getTrace: vi.fn() };
});
import { listJobs } from "../api/client";

beforeEach(() => { vi.mocked(listJobs).mockResolvedValue([]); });
afterEach(() => { document.documentElement.removeAttribute("data-theme"); localStorage.clear(); vi.restoreAllMocks(); });

describe("shell", () => {
  it("lists the six primary destinations and marks the current one", async () => {
    renderAt("#/invoices");
    const nav = await screen.findByRole("navigation", { name: "Primary" });
    for (const name of ["Dashboard", "Invoices", "Upload", "Needs review", "Audit trail", "Settings"])
      expect(within(nav).getByRole("link", { name: new RegExp(`^${name}`) })).toBeInTheDocument();
    expect(within(nav).getByRole("link", { name: /^Invoices/ })).toHaveAttribute("aria-current", "page");
    expect(within(nav).getByRole("link", { name: /^Dashboard/ })).not.toHaveAttribute("aria-current");
  });
  it("shows the number of jobs needing review on the nav item", async () => {
    vi.mocked(listJobs).mockResolvedValue([jobWith("a", "UNRESOLVED"), jobWith("b", "RECONCILED"), jobWith("c", "FAILED")]);
    renderAt("#/upload");
    expect(await screen.findByRole("link", { name: /Needs review\s*2/ })).toBeInTheDocument();
  });
  it("reports how many jobs the agent is working on", async () => {
    vi.mocked(listJobs).mockResolvedValue([jobWith("a", null), jobWith("b", null)]);
    renderAt("#/upload");
    expect(await screen.findByText("2 in progress")).toBeInTheDocument();
  });
  it("renders an in-shell not-found page for an unknown route (Review Focus 3)", async () => {
    renderAt("#/nope");
    expect(await screen.findByRole("heading", { level: 1, name: "Page not found" })).toBeInTheDocument();
    expect(screen.getByRole("navigation", { name: "Primary" })).toBeInTheDocument();
  });
  it("moves focus to the page heading when the route changes", async () => {
    renderAt("#/upload");
    await screen.findByRole("heading", { level: 1, name: "Upload invoice" });
    window.location.hash = "#/nope";
    const h1 = await screen.findByRole("heading", { level: 1, name: "Page not found" });
    await waitFor(() => expect(h1).toHaveFocus());
  });
  it("has a skip link that focuses the main region", async () => {
    renderAt("#/upload");
    await userEvent.click(await screen.findByRole("link", { name: "Skip to content" }));
    expect(screen.getByRole("main")).toHaveFocus();
    expect(window.location.hash).toBe("#/upload");            // the skip link must not change the route
  });
});

describe("theme toggle", () => {
  it("applies and persists the chosen theme", async () => {
    renderAt("#/upload");
    await userEvent.click(await screen.findByRole("button", { name: "Dark" }));
    expect(document.documentElement.dataset.theme).toBe("dark");
    expect(JSON.parse(localStorage.getItem("ledger.theme")!)).toBe("dark");
    await userEvent.click(screen.getByRole("button", { name: "System" }));
    expect(document.documentElement.hasAttribute("data-theme")).toBe(false);
  });
  it("still works when localStorage throws (Review Focus 5)", async () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("blocked"); });
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("blocked"); });
    renderAt("#/upload");
    await userEvent.click(await screen.findByRole("button", { name: "Light" }));
    expect(document.documentElement.dataset.theme).toBe("light");
  });
});
