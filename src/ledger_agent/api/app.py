from __future__ import annotations

import re
import tempfile
from concurrent.futures import ThreadPoolExecutor
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Callable

from fastapi import FastAPI, File, UploadFile
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from fastapi.staticfiles import StaticFiles

from ledger_agent.api.runner import run_job
from ledger_agent.graph import Deps
from ledger_agent.storage.base import Job, JobStore, new_job_id, utc_now


def invoice_id_from_filename(filename: str | None) -> str:
    stem = Path((filename or "invoice").replace("\\", "/")).stem
    safe = re.sub(r"[^A-Za-z0-9._-]+", "-", stem).strip("-._")
    return (safe or "invoice")[:40]


def create_app(store: JobStore, deps_factory: Callable[[str], Deps], *, max_upload_mb: float = 20,
               upload_dir=None, executor=None, frontend_dist=None,
               cors_origins=("http://localhost:5173", "http://127.0.0.1:5173"),
               store_name: str = "memory") -> FastAPI:
    upload_root = Path(upload_dir) if upload_dir else Path(tempfile.mkdtemp(prefix="ledger-uploads-"))
    upload_root.mkdir(parents=True, exist_ok=True)
    own_pool = executor is None
    pool = executor or ThreadPoolExecutor(max_workers=2)
    max_bytes = int(max_upload_mb * 1024 * 1024)

    @asynccontextmanager
    async def lifespan(_app):
        yield
        if own_pool:
            pool.shutdown(wait=False, cancel_futures=True)

    app = FastAPI(title="Self-Correcting Ledger Agent", lifespan=lifespan)
    app.add_middleware(CORSMiddleware, allow_origins=list(cors_origins),
                       allow_methods=["GET", "POST", "OPTIONS"], allow_headers=["*"])

    def err(status: int, code: str, message: str) -> JSONResponse:
        return JSONResponse(status_code=status, content={"code": code, "message": message})

    @app.get("/api/health")
    def health():
        return {"status": "ok", "store": store_name}

    @app.post("/api/invoices", status_code=202)
    async def upload(file: UploadFile | None = File(default=None)):
        if file is None:
            return err(422, "missing_file", "Attach a PDF in the 'file' field.")
        data = await file.read(max_bytes + 1)
        if len(data) > max_bytes:
            return err(413, "too_large", f"File exceeds the {max_upload_mb:g} MB limit.")
        if not data.startswith(b"%PDF"):
            return err(415, "not_a_pdf", "That file is not a PDF.")
        job_id = new_job_id()
        path = upload_root / f"{job_id}.pdf"
        path.write_bytes(data)
        store.create(Job(job_id=job_id, filename=file.filename or "invoice.pdf", created_at=utc_now()))
        pool.submit(run_job, store, deps_factory, job_id, path, invoice_id_from_filename(file.filename))
        return {"job_id": job_id, "status": "QUEUED"}

    @app.get("/api/invoices")
    def list_jobs(limit: int = 50):
        return [j.model_dump(mode="json") for j in store.list(limit=max(1, min(limit, 200)))]

    @app.get("/api/invoices/{job_id}")
    def get_job(job_id: str):
        job = store.get(job_id)
        if job is None:
            return err(404, "not_found", "No such job.")
        return job.model_dump(mode="json")

    @app.get("/api/invoices/{job_id}/trace")
    def get_trace(job_id: str):
        if store.get(job_id) is None:
            return err(404, "not_found", "No such job.")
        return store.get_events(job_id)

    if frontend_dist is not None and Path(frontend_dist).is_dir():
        app.mount("/", StaticFiles(directory=str(frontend_dist), html=True), name="ui")
    return app
