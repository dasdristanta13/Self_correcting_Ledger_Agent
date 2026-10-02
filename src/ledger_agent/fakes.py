import zlib
from typing import Callable

from ledger_agent.textparse import tokenize


class HashingEmbedder:
    """Deterministic offline embedder: hashed bag of tokens."""

    def __init__(self, dim: int = 256):
        self.dim = dim

    def embed(self, texts: list[str]) -> list[list[float]]:
        out = []
        for text in texts:
            vec = [0.0] * self.dim
            for tok in tokenize(text):
                vec[zlib.crc32(tok.encode()) % self.dim] += 1.0
            out.append(vec)
        return out


class FakeLLM:
    """responses: a list of dicts returned in order, or a callable(system, prompt) -> dict."""

    def __init__(self, responses: list[dict] | Callable[[str, str], dict]):
        self._responses = responses
        self.calls: list[tuple[str, str]] = []

    def complete_json(self, system: str, prompt: str, schema: dict) -> dict:
        self.calls.append((system, prompt))
        if callable(self._responses):
            return self._responses(system, prompt)
        return self._responses[len(self.calls) - 1]
