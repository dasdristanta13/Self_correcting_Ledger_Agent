from __future__ import annotations

import json
import threading
from pathlib import Path

import chromadb

from ledger_agent.storage.base import Job, utc_now

_ZERO = [0.0]


class ChromaJobStore:
    """JobStore on ChromaDB. Records are JSON documents with a dummy embedding."""

    def __init__(self, client):
        self._jobs = client.get_or_create_collection("jobs", embedding_function=None)
        self._events = client.get_or_create_collection("events", embedding_function=None)
        self._lock = threading.RLock()

    @classmethod
    def persistent(cls, path) -> "ChromaJobStore":
        Path(path).mkdir(parents=True, exist_ok=True)
        return cls(chromadb.PersistentClient(path=str(path)))

    def _put(self, job: Job) -> None:
        self._jobs.upsert(ids=[job.job_id], embeddings=[_ZERO], documents=[job.model_dump_json()],
                          metadatas=[{"state": job.state, "filename": job.filename,
                                      "created_at": job.created_at}])

    def create(self, job: Job) -> None:
        with self._lock:
            self._put(job)

    def get(self, job_id: str) -> Job | None:
        docs = self._jobs.get(ids=[job_id], include=["documents"])["documents"]
        return Job.model_validate_json(docs[0]) if docs else None

    def update(self, job_id: str, **fields) -> Job:
        with self._lock:
            job = self.get(job_id)
            if job is None:
                raise KeyError(job_id)
            job = Job.model_validate({**job.model_dump(), **fields})
            self._put(job)
            return job

    def list(self, limit: int = 50) -> list[Job]:
        docs = self._jobs.get(include=["documents"])["documents"]
        jobs = [Job.model_validate_json(d) for d in docs]
        return sorted(jobs, key=lambda j: j.created_at, reverse=True)[:limit]

    def append_events(self, job_id: str, events: list[dict]) -> None:
        if not events:
            return
        with self._lock:
            start = len(self._events.get(where={"job_id": job_id}, include=[])["ids"])
            self._events.upsert(
                ids=[f"{job_id}:{start + i:08d}" for i in range(len(events))],
                embeddings=[_ZERO] * len(events),
                documents=[json.dumps(e, default=str) for e in events],
                metadatas=[{"job_id": job_id, "seq": start + i} for i in range(len(events))])

    def get_events(self, job_id: str) -> list[dict]:
        got = self._events.get(where={"job_id": job_id}, include=["documents", "metadatas"])
        pairs = sorted(zip(got["metadatas"], got["documents"]), key=lambda p: p[0]["seq"])
        return [json.loads(doc) for _meta, doc in pairs]

    def mark_interrupted(self) -> int:
        with self._lock:
            got = self._jobs.get(where={"state": {"$in": ["QUEUED", "RUNNING"]}}, include=["documents"])
            for doc in got["documents"]:
                self.update(Job.model_validate_json(doc).job_id, state="ERROR",
                            error="interrupted by restart", finished_at=utc_now())
            return len(got["documents"])
