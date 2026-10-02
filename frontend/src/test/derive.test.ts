import { describe, expect, it } from "vitest";
import {
  agentLoad, correctionCount, countByKey, dailyBuckets, filterJobs, needsReview, priorityOf, reconciliationRate, statusKey, stopReason,
} from "../lib/derive";
import { eventDetail, formatDate, formatDateTime, formatTime, nodeLabel } from "../lib/format";
import { done, jobWith } from "./fixtures";

const errorJob = { ...jobWith("e", "RECONCILED"), state: "ERROR" as const, result: null, error: "interrupted" };
const doneNoResult = { ...jobWith("n", "RECONCILED"), result: null };

describe("statusKey", () => {
  it.each([
    ["RECONCILED", "ok"], ["UNRESOLVED", "wn"], ["MAX_REVISIONS_EXCEEDED", "wn"], ["INSUFFICIENT_EVIDENCE", "wn"],
    ["NO_PROGRESS", "wn"], ["FAILED", "er"], ["SOMETHING_NEW", "wn"],
  ])("%s -> %s", (status, key) => expect(statusKey(jobWith("a", status))).toBe(key));
  it("treats running jobs as in-progress", () => expect(statusKey(jobWith("a", null))).toBe("in"));
  it("treats a service ERROR and a DONE job without a result as failed (Review Focus 2)", () => {
    expect(statusKey(errorJob)).toBe("er");
    expect(statusKey(doneNoResult)).toBe("er");
  });
});

describe("counts and rate", () => {
  it("counts by key", () => {
    const jobs = [jobWith("a", "RECONCILED"), jobWith("b", "RECONCILED"), jobWith("c", "UNRESOLVED"), jobWith("d", null), errorJob];
    expect(countByKey(jobs)).toEqual({ ok: 2, wn: 1, in: 1, er: 1 });
  });
  it("rate is null for an empty list and when nothing has finished (Review Focus 1)", () => {
    expect(reconciliationRate([])).toBeNull();
    expect(reconciliationRate([jobWith("a", null)])).toBeNull();
  });
  it("rate is the integer percentage of finished jobs that reconciled", () => {
    const jobs = [jobWith("a", "RECONCILED"), jobWith("b", "RECONCILED"), jobWith("c", "RECONCILED"), jobWith("d", "UNRESOLVED"), jobWith("e", null)];
    expect(reconciliationRate(jobs)).toBe(75);
  });
  it("agentLoad counts queued and running jobs", () => {
    expect(agentLoad([jobWith("a", null), jobWith("b", "RECONCILED"), { ...jobWith("c", null), state: "QUEUED" }])).toBe(2);
  });
});

describe("dailyBuckets", () => {
  const now = new Date(2026, 9, 2, 15, 0, 0);
  const at = (d: number, h = 12) => new Date(2026, 9, d, h).toISOString();
  it("returns `days` buckets oldest first, with zeros for quiet days", () => {
    const b = dailyBuckets([], 3, now);
    expect(b.map((x) => x.day)).toEqual(["2026-09-30", "2026-10-01", "2026-10-02"]);
    expect(b.every((x) => x.ok + x.wn + x.er === 0)).toBe(true);
  });
  it("buckets by local created_at and ignores in-progress, old and invalid dates", () => {
    const jobs = [
      jobWith("a", "RECONCILED", { created_at: at(2) }), jobWith("b", "UNRESOLVED", { created_at: at(2) }),
      jobWith("c", "FAILED", { created_at: at(1) }), jobWith("d", null, { created_at: at(1) }),
      jobWith("old", "RECONCILED", { created_at: new Date(2025, 9, 1, 12).toISOString() }),
      jobWith("bad", "RECONCILED", { created_at: "not a date" }),
    ];
    const b = dailyBuckets(jobs, 3, now);
    expect(b[2]).toMatchObject({ day: "2026-10-02", ok: 1, wn: 1, er: 0 });
    expect(b[1]).toMatchObject({ day: "2026-10-01", ok: 0, wn: 0, er: 1 });
  });
});

describe("review helpers", () => {
  it.each([
    ["UNRESOLVED", "High"], ["FAILED", "High"], ["MAX_REVISIONS_EXCEEDED", "Medium"], ["NO_PROGRESS", "Medium"],
    ["INSUFFICIENT_EVIDENCE", "Low"], ["SOMETHING_NEW", "Medium"],
  ])("priority of %s is %s", (status, p) => expect(priorityOf(jobWith("a", status))).toBe(p));
  it("a service ERROR is High priority", () => expect(priorityOf(errorJob)).toBe("High"));
  it("needsReview keeps wn and er jobs in order", () => {
    const jobs = [jobWith("a", "RECONCILED"), jobWith("b", "UNRESOLVED"), jobWith("c", null), errorJob];
    expect(needsReview(jobs).map((j) => j.job_id)).toEqual(["b", "e"]);
  });
  it("stopReason and correctionCount tolerate a missing result", () => {
    expect(stopReason(jobWith("a", "NO_PROGRESS"))).toBe("NO_PROGRESS");
    expect(stopReason(errorJob)).toBe("ERROR");
    expect(correctionCount(errorJob)).toBe(0);
    expect(correctionCount(done)).toBe(1);
  });
});

describe("format additions", () => {
  it("formats dates and times, with a dash for bad input", () => {
    const iso = new Date(2024, 2, 12, 9, 41).toISOString();
    expect(formatDate(iso)).toBe("Mar 12, 2024");
    expect(formatTime(iso)).toBe("09:41");
    expect(formatDateTime(iso)).toBe("Mar 12, 2024 · 09:41");
    expect(formatDate("garbage")).toBe("—");
    expect(formatTime(null)).toBe("—");
  });
  it("labels graph nodes, with a readable fallback", () => {
    expect(nodeLabel("verify_evidence")).toBe("Verify evidence");
    expect(nodeLabel("some_new_node")).toBe("Some new node");
  });
  it("summarises trace detail", () => {
    const e = (detail: Record<string, unknown>) => ({ run_id: "r", invoice_id: "i", node: "validate", revision: 0, started_at: "t", latency_ms: 1, status: null, detail });
    expect(eventDetail(e({ discrepancies: [] }))).toBe("No discrepancies");
    expect(eventDetail(e({ discrepancies: ["a", "b"] }))).toBe("2 discrepancies");
    expect(eventDetail(e({ discrepancies: ["a"], evidence_count: 1 }))).toBe("1 discrepancy · 1 evidence chunk");
    expect(eventDetail(e({ corrections: ["x"] }))).toBe("1 correction proposed");
    expect(eventDetail(e({ error: "boom" }))).toBe("boom");
    expect(eventDetail(e({}))).toBe("");
  });
});

describe("filterJobs", () => {
  const jobs = [jobWith("alpha", "RECONCILED"), jobWith("beta", "UNRESOLVED"), jobWith("gamma", null)];
  it("filters by status key and by text", () => {
    expect(filterJobs(jobs, "all", "").length).toBe(3);
    expect(filterJobs(jobs, "wn", "").map((j) => j.job_id)).toEqual(["beta"]);
    expect(filterJobs(jobs, "all", "ALP").map((j) => j.job_id)).toEqual(["alpha"]);
    expect(filterJobs(jobs, "all", "unresolved").map((j) => j.job_id)).toEqual(["beta"]);
    expect(filterJobs(jobs, "ok", "beta")).toEqual([]);
  });
});
