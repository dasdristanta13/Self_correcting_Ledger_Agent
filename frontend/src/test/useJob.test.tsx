import { renderHook, waitFor } from "@testing-library/react";
import { beforeEach, expect, it, vi } from "vitest";
import example from "@contracts/example-job.json";
import type { Job } from "../api/types";
import { useJob } from "../hooks/useJob";

vi.mock("../api/client", () => ({ getJob: vi.fn() }));
import { getJob } from "../api/client";

const done = example as unknown as Job;
const running: Job = { ...done, state: "RUNNING", result: null, finished_at: null };

beforeEach(() => { vi.mocked(getJob).mockReset(); });

it("polls until the job is DONE then stops", async () => {
  vi.mocked(getJob).mockResolvedValueOnce(running).mockResolvedValueOnce(running).mockResolvedValue(done);
  const { result } = renderHook(() => useJob("j1", 10));
  await waitFor(() => expect(result.current.job?.state).toBe("DONE"));
  const calls = vi.mocked(getJob).mock.calls.length;
  await new Promise((r) => setTimeout(r, 60));
  expect(vi.mocked(getJob).mock.calls.length).toBe(calls);
});

it("stops on ERROR", async () => {
  vi.mocked(getJob).mockResolvedValue({ ...running, state: "ERROR", error: "boom" });
  const { result } = renderHook(() => useJob("j1", 10));
  await waitFor(() => expect(result.current.job?.state).toBe("ERROR"));
});

it("keeps retrying after a network error and recovers", async () => {
  vi.mocked(getJob).mockRejectedValueOnce(new Error("offline")).mockResolvedValue(done);
  // interval 50 (brief had 5): the retry fires at 3x interval; at 5 ms the error is cleared
  // before waitFor's 50 ms poll can observe it, so the assertion raced.
  const { result } = renderHook(() => useJob("j1", 50));
  await waitFor(() => expect(result.current.error).toBe("offline"));
  await waitFor(() => expect(result.current.job?.state).toBe("DONE"));
});

it("does nothing without a job id", () => {
  const { result } = renderHook(() => useJob(null, 10));
  expect(result.current.job).toBeNull();
  expect(getJob).not.toHaveBeenCalled();
});

it("stops retrying on a 404 and surfaces an error", async () => {
  vi.mocked(getJob).mockImplementation(() => Promise.reject(Object.assign(new Error("No such job."), { status: 404 })));
  const { result } = renderHook(() => useJob("gone", 10));
  await waitFor(() => expect(result.current.error).toBe("That job no longer exists."));
  const calls = vi.mocked(getJob).mock.calls.length;
  await new Promise((r) => setTimeout(r, 80));
  expect(vi.mocked(getJob).mock.calls.length).toBe(calls);
});
