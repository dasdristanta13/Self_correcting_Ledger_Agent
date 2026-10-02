from typing import Protocol

from ledger_agent.models import DocumentTable


class LLMClient(Protocol):
    def complete_json(self, system: str, prompt: str, schema: dict) -> dict: ...


class Embedder(Protocol):
    def embed(self, texts: list[str]) -> list[list[float]]: ...


class OcrBackend(Protocol):
    def recognize(self, page_png: bytes) -> tuple[str, list[dict]]:
        """Return (text, blocks[{block_id,bbox,text}]) for one page image."""


class TableExtractor(Protocol):
    def extract(self, pdf_path: str) -> list[DocumentTable]: ...
