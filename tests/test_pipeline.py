from __future__ import annotations

import numpy as np

from src.rag.config import Settings
from src.rag.pipeline import RagPipeline


class FakeEmbedder:
    """Deterministic two-dimensional embedder for an offline end-to-end test."""

    model = "fake-embed"

    def embed(self, texts):
        return np.array([self._vector(text) for text in texts], dtype=np.float32)

    def embed_one(self, text):
        return np.array(self._vector(text), dtype=np.float32)

    @staticmethod
    def _vector(text: str) -> list[float]:
        lowered = text.lower()
        if "alpha" in lowered:
            return [1.0, 0.0]
        if "beta" in lowered:
            return [0.0, 1.0]
        return [0.7, 0.7]


class FakeChat:
    def chat(self, messages):
        return "Alpha is the documented value [1]."


def make_pipeline(tmp_path) -> RagPipeline:
    docs = tmp_path / "documents"
    docs.mkdir()
    (docs / "alpha.md").write_text("Alpha is the documented value.", encoding="utf-8")
    (docs / "beta.md").write_text("Beta is a different value.", encoding="utf-8")
    settings = Settings(
        embed_model="fake-embed",
        chat_model="fake-chat",
        docs_dir=docs,
        index_path=tmp_path / "index.sqlite3",
        reports_dir=tmp_path / "reports",
    )
    return RagPipeline(settings=settings, embedder=FakeEmbedder(), chat=FakeChat())


def test_pipeline_builds_index_and_answers_with_citation(tmp_path):
    pipeline = make_pipeline(tmp_path)

    report = pipeline.build_index()
    assert report.rebuilt is True
    assert report.documents == 2
    assert report.chunks == 2

    result = pipeline.ask("What is alpha?", top_k=2)
    assert result.abstained is False
    assert "Alpha" in result.answer
    assert result.citations[0]["source"] == "alpha.md"
    assert result.retrieved[0].source == "alpha.md"
    pipeline.close()


def test_pipeline_does_not_reindex_unchanged_corpus(tmp_path):
    pipeline = make_pipeline(tmp_path)

    assert pipeline.build_index().rebuilt is True
    assert pipeline.build_index().rebuilt is False
    assert pipeline.status()["chunks"] == 2

    assert pipeline.build_index(force=True).rebuilt is True
    assert pipeline.status()["chunks"] == 2
    pipeline.close()
