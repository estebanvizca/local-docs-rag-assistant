from __future__ import annotations

import numpy as np

from src.rag.chunker import Chunk
from src.rag.index import Index
from src.rag.retriever import Retriever


class FakeEmbedder:
    def embed(self, texts):
        return np.array([[1.0, 0.0] for _ in texts], dtype=np.float32)

    def embed_one(self, text):
        return np.array([1.0, 0.0], dtype=np.float32)


def build_index(tmp_path) -> Index:
    index = Index(tmp_path / "index.sqlite3")
    chunks = [
        Chunk(text="alpha", source="a.md", page=None, chunk_index=0),
        Chunk(text="beta", source="b.pdf", page=3, chunk_index=0),
    ]
    vectors = np.array([[1.0, 0.0], [0.8, 0.6]], dtype=np.float32)
    index.rebuild(chunks, vectors, Index.fingerprint(chunks, "fake"), "fake")
    return index


def test_retriever_returns_ordered_results(tmp_path):
    index = build_index(tmp_path)
    retriever = Retriever(index, FakeEmbedder(), top_k=2, threshold=0.0)

    results = retriever.retrieve("anything")

    assert [result.text for result in results] == ["alpha", "beta"]
    assert results[1].source == "b.pdf"
    assert results[1].page == 3
    index.close()


def test_threshold_filters_weak_results(tmp_path):
    index = build_index(tmp_path)
    retriever = Retriever(index, FakeEmbedder(), top_k=2, threshold=0.9)

    results = retriever.retrieve("anything")

    assert [result.text for result in results] == ["alpha"]
    index.close()


def test_empty_question_returns_nothing(tmp_path):
    index = build_index(tmp_path)
    retriever = Retriever(index, FakeEmbedder(), top_k=2)

    assert retriever.retrieve("   ") == []
    index.close()
