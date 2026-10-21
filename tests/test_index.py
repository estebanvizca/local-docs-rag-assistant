from __future__ import annotations

import numpy as np

from src.rag.chunker import Chunk
from src.rag.index import Index


def make_chunk(text: str, index: int = 0) -> Chunk:
    return Chunk(text=text, source="doc.md", page=None, chunk_index=index)


def test_rebuild_search_and_idempotency(tmp_path):
    index = Index(tmp_path / "index.sqlite3")
    chunks = [make_chunk("alpha", 0), make_chunk("beta", 1)]
    vectors = np.array([[1.0, 0.0], [0.0, 1.0]], dtype=np.float32)
    fingerprint = Index.fingerprint(chunks, embed_model="fake")

    assert index.rebuild(chunks, vectors, fingerprint, "fake") is True
    assert index.count() == 2

    results = index.search(np.array([1.0, 0.0], dtype=np.float32), top_k=2)
    assert results[0].text == "alpha"
    assert results[0].score == 1.0
    assert results[1].text == "beta"
    assert results[1].score == 0.0

    # Same content must not duplicate rows.
    assert index.rebuild(chunks, vectors, fingerprint, "fake") is False
    assert index.count() == 2

    # Force still replaces instead of appending.
    assert index.rebuild(chunks, vectors, fingerprint, "fake", force=True) is True
    assert index.count() == 2
    index.close()


def test_fingerprint_changes_with_content_and_model():
    chunks = [make_chunk("alpha")]
    base = Index.fingerprint(chunks, embed_model="model-a")
    other_model = Index.fingerprint(chunks, embed_model="model-b")
    other_text = Index.fingerprint([make_chunk("beta")], embed_model="model-a")

    assert base != other_model
    assert base != other_text


def test_stats_and_clear(tmp_path):
    index = Index(tmp_path / "index.sqlite3")
    chunks = [make_chunk("alpha", 0), make_chunk("alpha two", 1)]
    vectors = np.array([[1.0, 0.0], [1.0, 0.0]], dtype=np.float32)
    index.rebuild(chunks, vectors, Index.fingerprint(chunks, "fake"), "fake")

    stats = index.stats()
    assert stats["chunks"] == 2
    assert stats["sources"] == {"doc.md": 2}
    assert stats["embed_model"] == "fake"

    index.clear()
    assert index.count() == 0
    assert index.search(np.array([1.0, 0.0], dtype=np.float32)) == []
    index.close()


def test_dimension_mismatch_is_explicit(tmp_path):
    index = Index(tmp_path / "index.sqlite3")
    chunks = [make_chunk("alpha")]
    index.rebuild(
        chunks,
        np.array([[1.0, 0.0]], dtype=np.float32),
        Index.fingerprint(chunks, "fake"),
        "fake",
    )

    try:
        index.search(np.array([1.0, 0.0, 0.0], dtype=np.float32))
    except ValueError as error:
        assert "dimension mismatch" in str(error)
    else:  # pragma: no cover
        raise AssertionError("Expected ValueError")
    index.close()
