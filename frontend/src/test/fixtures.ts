import example from "@contracts/example-job.json";
import type { Job } from "../api/types";

export const done = example as unknown as Job;

/** status null => a RUNNING job with no result; otherwise a DONE job carrying that result status. */
export function jobWith(id: string, status: string | null, over: Partial<Job> = {}): Job {
  if (status === null) {
    return { ...done, job_id: id, filename: `${id}.pdf`, state: "RUNNING", result: null, finished_at: null, ...over };
  }
  return {
    ...done, job_id: id, filename: `${id}.pdf`, state: "DONE",
    result: { ...done.result!, status, corrections: status === "RECONCILED" ? done.result!.corrections : [] },
    ...over,
  };
}
