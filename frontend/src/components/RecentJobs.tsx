import type { Job } from "../api/types";

export function RecentJobs({ jobs, selected, onSelect }: { jobs: Job[]; selected: string | null; onSelect: (id: string) => void }) {
  if (jobs.length === 0) return null;
  return (
    <section className="recent-section" aria-labelledby="recent-h">
      <h2 id="recent-h">Recent</h2>
      <ul className="recent">
        {jobs.map((j) => (
          <li key={j.job_id}>
            <button type="button" aria-current={selected === j.job_id ? "true" : undefined} onClick={() => onSelect(j.job_id)}>
              <span className="recent-name" title={j.filename}>{j.filename}</span>
              <span className="recent-state">{j.result?.status ?? j.state}</span>
            </button>
          </li>
        ))}
      </ul>
    </section>
  );
}
