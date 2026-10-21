from __future__ import annotations

import pytest

from src.rag.chunker import MAX_CHARS, OVERLAP_CHARS, chunk_document, chunk_text
from src.rag.loader import Document


def test_short_text_is_one_chunk():
    text = "First paragraph.\n\nSecond paragraph."

    assert chunk_text(text) == ["First paragraph.\n\nSecond paragraph."]


def test_chunks_respect_max_size():
    paragraphs = [f"Paragraph {index} " + ("word " * 120) for index in range(12)]
    text = "\n\n".join(paragraphs)

    chunks = chunk_text(text, max_chars=MAX_CHARS, overlap_chars=OVERLAP_CHARS)

    assert len(chunks) > 1
    assert all(len(chunk) <= MAX_CHARS for chunk in chunks)
    assert all(chunk.strip() for chunk in chunks)


def test_consecutive_chunks_overlap():
    first = "alpha " * 180
    second = "beta " * 180
    chunks = chunk_text(f"{first}\n\n{second}", max_chars=500, overlap_chars=100)

    assert len(chunks) >= 2
    assert chunks[0][-40:].strip() in chunks[1]


def test_long_unbroken_paragraph_is_hard_wrapped():
    text = "x" * 2500

    chunks = chunk_text(text, max_chars=300, overlap_chars=50)

    assert len(chunks) > 1
    assert all(len(chunk) <= 300 for chunk in chunks)


def test_chunk_document_preserves_provenance():
    document = Document(
        text="One paragraph.\n\nAnother paragraph.",
        source="open-systems-handbook.pdf",
        page=4,
    )

    chunks = chunk_document(document)

    assert len(chunks) == 1
    assert chunks[0].source == "open-systems-handbook.pdf"
    assert chunks[0].page == 4
    assert chunks[0].chunk_index == 0


def test_invalid_overlap_rejected():
    with pytest.raises(ValueError):
        chunk_text("text", max_chars=100, overlap_chars=100)
