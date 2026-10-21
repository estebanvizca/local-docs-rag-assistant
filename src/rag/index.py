"""Persist chunks and embeddings in SQLite and search them by cosine similarity.

The corpus is small, so vectors live in one SQLite table and NumPy computes
cosine similarity in memory. No vector database is needed for the MVP.
"""

from __future__ import annotations

import hashlib
import json
import sqlite3
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import numpy as np

from .chunker import Chunk

SCHEMA = """
CREATE TABLE IF NOT EXISTS meta (
    key TEXT PRIMARY KEY,
    value TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS chunks (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    source TEXT NOT NULL,
    page INTEGER,
    chunk_index INTEGER NOT NULL,
    text TEXT NOT NULL,
    embedding BLOB NOT NULL,
    embed_model TEXT NOT NULL
);
"""


@dataclass(frozen=True)
class SearchResult:
    """A chunk returned by similarity search."""

    text: str
    source: str
    page: int | None
    chunk_index: int
    score: float


class Index:
    """SQLite-backed chunk index with NumPy cosine search."""

    def __init__(self, path: Path) -> None:
        self.path = Path(path)
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._connection = sqlite3.connect(self.path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        with self._connection:
            self._connection.executescript(SCHEMA)

    # ------------------------------------------------------------------ meta
    def _get_meta(self, key: str) -> str | None:
        row = self._connection.execute("SELECT value FROM meta WHERE key = ?", (key,)).fetchone()
        return row["value"] if row else None

    def _set_meta(self, key: str, value: str) -> None:
        self._connection.execute(
            "INSERT INTO meta(key, value) VALUES(?, ?) "
            "ON CONFLICT(key) DO UPDATE SET value = excluded.value",
            (key, value),
        )

    @staticmethod
    def fingerprint(
        chunks: list[Chunk],
        embed_model: str,
        max_chars: int = 800,
        overlap_chars: int = 120,
    ) -> str:
        """Hash the corpus content and indexing configuration."""
        digest = hashlib.sha256()
        digest.update(f"{embed_model}|{max_chars}|{overlap_chars}".encode())
        for chunk in chunks:
            digest.update(
                f"\x00{chunk.source}\x00{chunk.page}\x00{chunk.chunk_index}\x00{chunk.text}".encode()
            )
        return digest.hexdigest()

    def is_current(self, fingerprint: str) -> bool:
        """Return True when the stored index matches the corpus fingerprint."""
        return self.count() > 0 and self._get_meta("fingerprint") == fingerprint

    # ------------------------------------------------------------------ data
    def count(self) -> int:
        row = self._connection.execute("SELECT COUNT(*) AS n FROM chunks").fetchone()
        return int(row["n"])

    def rebuild(
        self,
        chunks: list[Chunk],
        embeddings: np.ndarray,
        fingerprint: str,
        embed_model: str,
        force: bool = False,
    ) -> bool:
        """Replace the index content; skip when the fingerprint is unchanged.

        Returns ``True`` when rows were written, ``False`` when the current
        index was already valid. Re-indexing the same corpus is idempotent.
        """
        if not force and self.is_current(fingerprint):
            return False
        if len(chunks) != len(embeddings):
            raise ValueError("chunks and embeddings must have the same length")
        if len(chunks) == 0:
            self.clear()
            return False

        matrix = np.asarray(embeddings, dtype=np.float32)
        if matrix.ndim != 2:
            raise ValueError("embeddings must be a 2-D matrix")

        rows = [
            (
                chunk.source,
                chunk.page,
                chunk.chunk_index,
                chunk.text,
                matrix[index].tobytes(),
                embed_model,
            )
            for index, chunk in enumerate(chunks)
        ]

        with self._connection:
            self._connection.execute("DELETE FROM chunks")
            self._connection.executemany(
                "INSERT INTO chunks(source, page, chunk_index, text, embedding, embed_model) "
                "VALUES (?, ?, ?, ?, ?, ?)",
                rows,
            )
            self._set_meta("fingerprint", fingerprint)
            self._set_meta("embed_model", embed_model)
            self._set_meta("updated_at", datetime.now(timezone.utc).isoformat(timespec="seconds"))
        return True

    def clear(self) -> None:
        """Remove all chunks and metadata."""
        with self._connection:
            self._connection.execute("DELETE FROM chunks")
            self._connection.execute("DELETE FROM meta")

    def stats(self) -> dict:
        """Return a small summary for the UI and the evaluation report."""
        rows = self._connection.execute(
            "SELECT source, COUNT(*) AS n FROM chunks GROUP BY source ORDER BY source"
        ).fetchall()
        return {
            "chunks": self.count(),
            "sources": {row["source"]: int(row["n"]) for row in rows},
            "embed_model": self._get_meta("embed_model"),
            "updated_at": self._get_meta("updated_at"),
            "fingerprint": self._get_meta("fingerprint"),
        }

    # ------------------------------------------------------------------ search
    def search(self, query_vector: np.ndarray, top_k: int = 3) -> list[SearchResult]:
        """Return the ``top_k`` most similar chunks, highest score first."""
        if top_k <= 0:
            raise ValueError("top_k must be positive")

        rows = self._connection.execute(
            "SELECT source, page, chunk_index, text, embedding FROM chunks"
        ).fetchall()
        if not rows:
            return []

        query = np.asarray(query_vector, dtype=np.float32).ravel()
        matrix = np.vstack([np.frombuffer(row["embedding"], dtype=np.float32) for row in rows])
        if matrix.shape[1] != query.shape[0]:
            raise ValueError(
                f"Embedding dimension mismatch: index has {matrix.shape[1]}, query has {query.shape[0]}. "
                "Rebuild the index with the current embedding model."
            )

        query_norm = float(np.linalg.norm(query))
        row_norms = np.linalg.norm(matrix, axis=1)
        if query_norm == 0 or np.any(row_norms == 0):
            raise ValueError("Cannot compute cosine similarity with a zero vector.")

        scores = (matrix @ query) / (row_norms * query_norm)
        best = np.argsort(-scores)[: min(top_k, len(rows))]

        return [
            SearchResult(
                text=rows[index]["text"],
                source=rows[index]["source"],
                page=rows[index]["page"],
                chunk_index=int(rows[index]["chunk_index"]),
                score=float(scores[index]),
            )
            for index in best
        ]

    def close(self) -> None:
        self._connection.close()

    def __enter__(self) -> "Index":
        return self

    def __exit__(self, *_: object) -> None:
        self.close()
