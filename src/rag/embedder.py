"""Embedding client for the local Ollama endpoint.

Only the local daemon is used. The endpoint and model are configurable so the
app never assumes a specific model name.
"""

from __future__ import annotations

from collections.abc import Sequence

import httpx
import numpy as np


class EmbeddingError(RuntimeError):
    """Raised when Ollama cannot produce embeddings."""


class OllamaEmbedder:
    """Batch embeddings through Ollama's ``/api/embed`` endpoint."""

    def __init__(
        self,
        host: str = "http://localhost:11434",
        model: str = "nomic-embed-text",
        timeout: float = 180.0,
        batch_size: int = 32,
    ) -> None:
        self.host = host.rstrip("/")
        self.model = model
        self.timeout = timeout
        self.batch_size = max(1, batch_size)

    def _request_batch(self, texts: Sequence[str]) -> list[list[float]]:
        url = f"{self.host}/api/embed"
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(url, json={"model": self.model, "input": list(texts)})
                response.raise_for_status()
        except httpx.ConnectError as exc:
            raise EmbeddingError(
                f"Could not connect to Ollama at {self.host}. Start it with `ollama serve`."
            ) from exc
        except httpx.HTTPStatusError as exc:
            detail = exc.response.text[:500]
            raise EmbeddingError(
                f"Ollama embedding request failed ({exc.response.status_code}). "
                f"Check that `{self.model}` is installed with `ollama pull {self.model}`. "
                f"Details: {detail}"
            ) from exc

        try:
            payload = response.json()
            embeddings = payload["embeddings"]
        except (ValueError, KeyError) as exc:
            raise EmbeddingError(f"Unexpected response from Ollama: {response.text[:300]}") from exc

        if len(embeddings) != len(texts):
            raise EmbeddingError(
                f"Ollama returned {len(embeddings)} embeddings for {len(texts)} inputs."
            )
        if any(not vector for vector in embeddings):
            raise EmbeddingError("Ollama returned an empty embedding vector.")
        return embeddings

    def embed(self, texts: Sequence[str]) -> np.ndarray:
        """Return a ``(len(texts), dimensions)`` float32 matrix."""
        texts = list(texts)
        if not texts:
            return np.zeros((0, 0), dtype=np.float32)

        vectors: list[list[float]] = []
        for start in range(0, len(texts), self.batch_size):
            vectors.extend(self._request_batch(texts[start : start + self.batch_size]))

        matrix = np.asarray(vectors, dtype=np.float32)
        if matrix.ndim != 2 or matrix.shape[1] == 0:
            raise EmbeddingError("Ollama returned malformed embedding vectors.")
        return matrix

    def embed_one(self, text: str) -> np.ndarray:
        """Return a single embedding vector."""
        return self.embed([text])[0]
