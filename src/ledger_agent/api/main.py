"""Production wiring: FastAPI + ChromaDB job store + Chroma vector backend + trace sinks.

Run with: uvicorn ledger_agent.api.main:build_app_from_env --factory --port 8787
"""
from __future__ import annotations

import os
from pathlib import Path

from fastapi import FastAPI

from ledger_agent.agents.audit import ChunkValueProposer
from ledger_agent.api.app import create_app
from ledger_agent.api.lock import DataDirLock
from ledger_agent.extraction.ledger import build_ledger
from ledger_agent.fakes import HashingEmbedder
from ledger_agent.graph import Deps
from ledger_agent.observability.sinks import CompositeSink, JsonLogSink, StoreTraceSink, configure_json_logging
from ledger_agent.retrieval.chroma_vector import chroma_vector_factory, sweep_orphan_indexes
from ledger_agent.storage.chroma_store import ChromaJobStore, persistent_client


def build_app(data_dir, *, ledger_builder=build_ledger, executor=None, max_upload_mb: float = 20,
              frontend_dist=None, lock: bool = True) -> FastAPI:
    data_dir = Path(data_dir)
    data_dir.mkdir(parents=True, exist_ok=True)
    guard = None
    if lock:                                 # BEFORE any sweep: a second process must not destroy live work
        guard = DataDirLock(data_dir)
        guard.acquire()
    try:
        return _build(data_dir, ledger_builder, executor, max_upload_mb, frontend_dist, guard)
    except BaseException:
        if guard is not None:
            guard.release()
        raise


def _build(data_dir, ledger_builder, executor, max_upload_mb, frontend_dist, guard) -> FastAPI:
    gitignore = data_dir / ".gitignore"
    if not gitignore.exists():               # keep runtime data out of git without touching the repo .gitignore
        gitignore.write_text("*\n", encoding="ascii")
    (data_dir / "chroma").mkdir(parents=True, exist_ok=True)
    client = persistent_client(data_dir / "chroma")
    store = ChromaJobStore(client)
    store.mark_interrupted()                 # jobs a crash left QUEUED/RUNNING must not spin forever
    sweep_orphan_indexes(client)             # per-invoice collections a crash left behind
    factory = chroma_vector_factory(client)

    def deps_factory(job_id: str) -> Deps:
        # HashingEmbedder / ChunkValueProposer keep the service offline; swap in real ones here.
        return Deps(embedder=HashingEmbedder(), proposer=ChunkValueProposer(), vector_factory=factory,
                    ledger_builder=ledger_builder,
                    trace_sink=CompositeSink(StoreTraceSink(store, job_id), JsonLogSink()))

    return create_app(store, deps_factory, max_upload_mb=max_upload_mb, upload_dir=data_dir / "uploads",
                      executor=executor, frontend_dist=frontend_dist, store_name="chroma",
                      on_shutdown=guard.release if guard else None)


def build_app_from_env() -> FastAPI:
    configure_json_logging(os.environ.get("LEDGER_LOG_LEVEL", "INFO"))
    return build_app(os.environ.get("LEDGER_DATA_DIR", "./data"),
                     max_upload_mb=float(os.environ.get("MAX_UPLOAD_MB", "20")),
                     frontend_dist=os.environ.get("LEDGER_FRONTEND_DIST", "frontend/dist"))
