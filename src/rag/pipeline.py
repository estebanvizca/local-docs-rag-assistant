"""High-level pipeline used by the Streamlit app and the evaluation script."""

from __future__ import annotations

import time
from dataclasses import dataclass, field
from typing import Callable

import numpy as np

from .answerer import Answerer, AnswerResult, OllamaChat
from .chunker import MAX_CHARS, OVERLAP_CHARS, chunk_documents
from .config import Settings
from .embedder import OllamaEmbedder
from .index import Index
from .loader import load_documents
from .retriever import RetrievedChunk, Retriever

ProgressCallback = Callable[[int, int], None]


@dataclass
class IndexReport:
    """Result of an indexing attempt."""

    documents: int
    chunks: int
    rebuilt: bool
    stats: dict = field(default_factory=dict)


@dataclass
class AskResult:
    """Answer, evidence and timing for one question."""

    question: str
    answer: str
    abstained: bool
    citations: list[dict]
    retrieved: list[RetrievedChunk]
    latency_ms: float


class RagPipeline:
    """Wire loading, chunking, embedding, indexing, retrieval and answering."""

    def __init__(
        self,
        settings: Settings | None = None,
        embedder: OllamaEmbedder | None = None,
        chat: OllamaChat | None = None,
    ) -> None:
        self.settings = settings or Settings.from_env()
        self.embedder = embedder or OllamaEmbedder(
            host=self.settings.ollama_host,
            model=self.settings.embed_model,
            timeout=self.settings.request_timeout,
        )
        self.chat = chat or OllamaChat(
            host=self.settings.ollama_host,
            model=self.settings.chat_model,
            timeout=self.settings.request_timeout,
        )
        self.index = Index(self.settings.index_path)
        self.answerer = Answerer(self.chat)

    def build_index(
        self,
        force: bool = False,
        progress: ProgressCallback | None = None,
    ) -> IndexReport:
        """Index ``data/documents`` unless the stored fingerprint is current."""
        documents = load_documents(self.settings.docs_dir)
        source_count = len({document.source for document in documents})
        chunks = chunk_documents(documents, max_chars=MAX_CHARS, overlap_chars=OVERLAP_CHARS)
        fingerprint = Index.fingerprint(
            chunks,
            embed_model=self.settings.embed_model,
            max_chars=MAX_CHARS,
            overlap_chars=OVERLAP_CHARS,
        )

        if not force and self.index.is_current(fingerprint):
            return IndexReport(
                documents=source_count,
                chunks=len(chunks),
                rebuilt=False,
                stats=self.index.stats(),
            )

        if not chunks:
            self.index.clear()
            return IndexReport(documents=0, chunks=0, rebuilt=False, stats=self.index.stats())

        vectors = self._embed_chunks(chunks, progress)
        rebuilt = self.index.rebuild(
            chunks=chunks,
            embeddings=vectors,
            fingerprint=fingerprint,
            embed_model=self.settings.embed_model,
            force=True,
        )
        return IndexReport(
            documents=source_count,
            chunks=len(chunks),
            rebuilt=rebuilt,
            stats=self.index.stats(),
        )

    def _embed_chunks(self, chunks, progress: ProgressCallback | None) -> np.ndarray:
        batch_size = 32
        vectors: list[np.ndarray] = []
        for start in range(0, len(chunks), batch_size):
            batch = chunks[start : start + batch_size]
            vectors.append(self.embedder.embed([chunk.text for chunk in batch]))
            if progress:
                progress(min(start + len(batch), len(chunks)), len(chunks))
        return np.vstack(vectors)

    def ask(
        self,
        question: str,
        top_k: int | None = None,
        threshold: float | None = None,
    ) -> AskResult:
        """Retrieve evidence and answer one question."""
        started = time.perf_counter()
        retriever = Retriever(
            index=self.index,
            embedder=self.embedder,
            top_k=top_k or self.settings.top_k,
            threshold=(
                self.settings.similarity_threshold if threshold is None else threshold
            ),
        )
        retrieved = retriever.retrieve(question)
        result: AnswerResult = self.answerer.answer(question, retrieved)
        elapsed_ms = (time.perf_counter() - started) * 1000
        return AskResult(
            question=question,
            answer=result.answer,
            abstained=result.abstained,
            citations=result.citations,
            retrieved=retrieved,
            latency_ms=elapsed_ms,
        )

    def status(self) -> dict:
        """Return index statistics for the UI."""
        return self.index.stats()

    def close(self) -> None:
        self.index.close()
