import { describe, expect, it, vi } from "vitest";
vi.mock("../api/client", () => ({ getJob: vi.fn() }));
import { getJob } from "../api/client";
import { pollJob, runPool } from "../lib/queue";
import { done } from "./fixtures";

describe("runPool", () => {
  it("never runs more than `limit` workers at once and runs every item", async () => {
    let live = 0, peak = 0;
    const seen: number[] = [];
    await runPool([1, 2, 3, 4, 5, 6, 7], 3, async (n) => {
      live++; peak = Math.max(peak, live);
      await new Promise((r) => setTimeout(r, 5));
      seen.push(n); live--;
    });
    expect(peak).toBe(3);
    expect(seen.sort()).toEqual([1, 2, 3, 4, 5, 6, 7]);
  });
  it("keeps going when a worker throws and handles an empty list", async () => {
    const seen: number[] = [];
    await runPool([1, 2, 3], 2, async (n) => { if (n === 1) throw new Error("x"); seen.push(n); });
    expect(seen.sort()).toEqual([2, 3]);
    await expect(runPool([], 3, async () => undefined)).resolves.toBeUndefined();
  });
});

describe("pollJob", () => {
  it("polls until the job is DONE", async () => {
    vi.mocked(getJob).mockResolvedValueOnce({ ...done, state: "RUNNING" }).mockResolvedValueOnce(done);
    await expect(pollJob("j", 0)).resolves.toEqual(done);
  });
  it("gives up after consecutive failures and on 404", async () => {
    vi.mocked(getJob).mockReset().mockRejectedValue(new Error("offline"));
    await expect(pollJob("j", 0, 3)).rejects.toThrow("offline");
    expect(getJob).toHaveBeenCalledTimes(3);
    vi.mocked(getJob).mockReset().mockRejectedValue(Object.assign(new Error("gone"), { status: 404 }));
    await expect(pollJob("j", 0, 3)).rejects.toThrow("gone");
    expect(getJob).toHaveBeenCalledTimes(1);
  });
  it("times out when the job never finishes", async () => {
    vi.mocked(getJob).mockReset().mockResolvedValue({ ...done, state: "RUNNING" });
    await expect(pollJob("j", 0, 3, 30)).rejects.toThrow(/Timed out/);
  });
});
