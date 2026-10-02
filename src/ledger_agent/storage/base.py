from __future__ import annotations

import uuid
from datetime import datetime, timezone
from typing import Literal, Protocol

from pydantic import BaseModel

JobState = Literal["QUEUED", "RUNNING", "DONE", "ERROR"]


class Job(BaseModel):
    job_id: str
    filename: str
    state: JobState = "QUEUED"
    created_at: str
    finished_at: str | None = None
    result: dict | None = None
    error: str | None = None


class JobStore(Protocol):
    def create(self, job: Job) -> None: ...
    def update(self, job_id: str, **fields) -> Job: ...
    def get(self, job_id: str) -> Job | None: ...
    def list(self, limit: int = 50) -> list[Job]: ...
    def append_events(self, job_id: str, events: list[dict]) -> None: ...
    def get_events(self, job_id: str) -> list[dict]: ...
    def mark_interrupted(self) -> int: ...


def new_job_id() -> str:
    return uuid.uuid4().hex


def utc_now() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="milliseconds")
