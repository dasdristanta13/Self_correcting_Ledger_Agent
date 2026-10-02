import { screen } from "@testing-library/react";
import userEvent from "@testing-library/user-event";
import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { loadSettings, SETTING_GROUPS } from "../lib/settings";
import { writeJSON } from "../lib/storage";
import { renderAt } from "./helpers";

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return { ...actual, uploadInvoice: vi.fn(), getJob: vi.fn(), listJobs: vi.fn(), getTrace: vi.fn() };
});
import { listJobs } from "../api/client";

beforeEach(() => { vi.mocked(listJobs).mockResolvedValue([]); });
afterEach(() => { localStorage.clear(); vi.restoreAllMocks(); });

describe("settings storage", () => {
  it("defaults mirror configs/default.yaml", () => {
    const s = loadSettings();
    expect(s.max_revisions).toBe("3");
    expect(s.confidence_threshold).toBe("0.90");
    expect(s.top_k).toBe("5");
    expect(s.tolerance).toBe("0.01");
  });
  it("ignores stored values of the wrong type or outside the options", () => {
    localStorage.setItem("ledger.settings", JSON.stringify({ max_revisions: 99, extract_tables: "yes", top_k: "8" }));
    const s = loadSettings();
    expect(s.max_revisions).toBe("3");
    expect(s.extract_tables).toBe(true);
    expect(s.top_k).toBe("8");
  });
  it("falls back to defaults when localStorage throws (Review Focus 5)", () => {
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("blocked"); });
    expect(loadSettings().top_k).toBe("5");
  });
  it("falls back to defaults when the stored value is an array", () => {
    localStorage.setItem("ledger.settings", JSON.stringify(["top_k"]));
    expect(loadSettings().top_k).toBe("5");
  });
  it("writeJSON reports whether the write succeeded", () => {
    expect(writeJSON("k", { a: 1 })).toBe(true);
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("blocked"); });
    expect(writeJSON("k", { a: 1 })).toBe(false);
  });
  it("every select default is one of its options", () => {
    for (const d of Object.values(SETTING_GROUPS).flat()) if (d.kind === "select") expect(d.options).toContain(d.default);
  });
});

describe("SettingsView", () => {
  it("labels itself as a browser-only preview", async () => {
    renderAt("#/settings");
    expect(await screen.findByText(/not yet applied by the agent/i)).toBeInTheDocument();
  });
  it("edits, saves and restores settings", async () => {
    renderAt("#/settings");
    await userEvent.click(await screen.findByRole("tab", { name: "Agent" }));
    const save = screen.getByRole("button", { name: "Save changes" });
    expect(save).toBeDisabled();
    await userEvent.selectOptions(screen.getByRole("combobox", { name: "Retrieval top-K" }), "8");
    expect(save).toBeEnabled();
    await userEvent.click(save);
    expect(await screen.findByText("Saved in this browser")).toBeInTheDocument();
    expect(JSON.parse(localStorage.getItem("ledger.settings")!).top_k).toBe("8");
    await userEvent.click(screen.getByRole("button", { name: "Reset to defaults" }));
    expect(screen.getByRole("combobox", { name: "Retrieval top-K" })).toHaveValue("5");
  });
  it("toggles a switch with the keyboard", async () => {
    renderAt("#/settings");
    await userEvent.click(await screen.findByRole("tab", { name: "Extraction" }));
    const sw = screen.getByRole("switch", { name: "High accuracy mode" });
    expect(sw).toHaveAttribute("aria-checked", "false");
    sw.focus();
    await userEvent.keyboard(" ");
    expect(sw).toHaveAttribute("aria-checked", "true");
  });
  it("does not crash when saving is blocked", async () => {
    vi.spyOn(Storage.prototype, "setItem").mockImplementation(() => { throw new Error("blocked"); });
    renderAt("#/settings");
    await userEvent.click(await screen.findByRole("tab", { name: "Notifications" }));
    await userEvent.click(screen.getByRole("switch", { name: "Processing failed" }));
    const save = screen.getByRole("button", { name: "Save changes" });
    await userEvent.click(save);
    expect(screen.getByRole("heading", { level: 1, name: "Settings" })).toBeInTheDocument();
    expect(screen.getByRole("alert")).toHaveTextContent("Couldn't save in this browser. Your changes apply to this session only.");
    expect(screen.queryByText("Saved in this browser")).not.toBeInTheDocument();
    expect(save).toBeEnabled();
  });
});
