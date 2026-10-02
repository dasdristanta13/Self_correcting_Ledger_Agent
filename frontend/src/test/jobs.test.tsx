import { render, screen, waitFor } from "@testing-library/react";
import { beforeEach, describe, expect, it, vi } from "vitest";
import { done } from "./fixtures";

vi.mock("../api/client", async () => {
  const actual = await vi.importActual<typeof import("../api/client")>("../api/client");
  return { ...actual, listJobs: vi.fn() };
});
import { listJobs } from "../api/client";
import { JobsProvider, useJobs } from "../hooks/useJobs";

function Consumer() {
  const { jobs, error } = useJobs();
  return <p>{error ?? `${jobs.length} jobs`}</p>;
}

beforeEach(() => { vi.mocked(listJobs).mockReset(); });

describe("JobsProvider", () => {
  it("recovers from a failed initial load without a manual refresh, then stops polling", async () => {
    vi.mocked(listJobs).mockRejectedValueOnce(new Error("down")).mockResolvedValue([done]);
    render(<JobsProvider pollMs={20}><Consumer /></JobsProvider>);
    expect(await screen.findByText("Could not load invoices from the server.")).toBeInTheDocument();
    expect(await screen.findByText("1 jobs")).toBeInTheDocument();
    await waitFor(() => expect(vi.mocked(listJobs).mock.calls.length).toBeGreaterThanOrEqual(2));
    await new Promise((r) => setTimeout(r, 30));          // let any in-flight tick settle
    const calls = vi.mocked(listJobs).mock.calls.length;
    await new Promise((r) => setTimeout(r, 120));
    expect(vi.mocked(listJobs).mock.calls.length).toBe(calls);
  });
});
