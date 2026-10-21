"""Retrieve the top-k chunks for a question."""

from __future__ import annotations

from dataclasses import dataclass

from .embedder import OllamaEmbedder
from .index import Index


@dataclass(frozen=True)
class RetrievedChunk:
    """A retrieved chunk with its source metadata and similarity score."""

    text: str
    source: str
    page: int | None
    chunk_index: int
    score: float


class Retriever:
    """Embed a question and search the local index."""

    def __init__(
        self,
        index: Index,
        embedder: OllamaEmbedder,
        top_k: int = 3,
        threshold: float = 0.0,
    ) -> None:
        if top_k <= 0:
            raise ValueError("top_k must be positive")
        if not 0.0 <= threshold <= 1.0:
            raise ValueError("threshold must be between 0 and 1")
        self.index = index
        self.embedder = embedder
        self.top_k = top_k
        self.threshold = threshold

    def retrieve(self, question: str) -> list[RetrievedChunk]:
        """Return chunks above the similarity threshold, nearest first."""
        question = question.strip()
        if not question:
            return []

        query_vector = self.embedder.embed_one(question)
        results = self.index.search(query_vector, top_k=self.top_k)
        return [
            RetrievedChunk(
                text=result.text,
                source=result.source,
                page=result.page,
                chunk_index=result.chunk_index,
                score=result.score,
            )
            for result in results
            if result.score >= self.threshold
        ]
