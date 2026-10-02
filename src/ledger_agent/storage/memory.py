from __future__ import annotations

import threading

from ledger_agent.storage.base import Job, utc_now


class InMemoryJobStore:
    def __init__(self):
        self._jobs: dict[str, Job] = {}
        self._events: dict[str, list[dict]] = {}
        self._lock = threading.RLock()

    def create(self, job: Job) -> None:
        with self._lock:
            self._jobs[job.job_id] = job

    def update(self, job_id: str, **fields) -> Job:
        with self._lock:
            job = self._jobs[job_id]          # KeyError for unknown ids
            job = Job.model_validate({**job.model_dump(), **fields})
            self._jobs[job_id] = job
            return job

    def get(self, job_id: str) -> Job | None:
        with self._lock:
            return self._jobs.get(job_id)

    def list(self, limit: int = 50) -> list[Job]:
        with self._lock:
            return sorted(self._jobs.values(), key=lambda j: j.created_at, reverse=True)[:limit]

    def append_events(self, job_id: str, events: list[dict]) -> None:
        with self._lock:
            self._events.setdefault(job_id, []).extend(events)

    def get_events(self, job_id: str) -> list[dict]:
        with self._lock:
            return list(self._events.get(job_id, []))

    def mark_interrupted(self) -> int:
        with self._lock:
            n = 0
            for jid, job in list(self._jobs.items()):
                if job.state in ("QUEUED", "RUNNING"):
                    self.update(jid, state="ERROR", error="interrupted by restart", finished_at=utc_now())
                    n += 1
            return n
