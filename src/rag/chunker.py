"""Split documents into overlapping chunks.

Paragraphs are packed first; a chunk never exceeds ``MAX_CHARS``. Consecutive
chunks share up to ``OVERLAP_CHARS`` characters to preserve context at
boundaries. Every chunk keeps its source filename and page (when available).
"""

from __future__ import annotations

import re
from dataclasses import dataclass

from .loader import Document

MAX_CHARS = 800
OVERLAP_CHARS = 120


@dataclass(frozen=True)
class Chunk:
    """A retrievable text fragment with provenance metadata."""

    text: str
    source: str
    page: int | None
    chunk_index: int


def _split_long_paragraph(paragraph: str, max_chars: int) -> list[str]:
    """Split an oversized paragraph on sentence boundaries, then hard-wrap."""
    sentences = re.split(r"(?<=[.!?])\s+", paragraph)
    pieces: list[str] = []
    current = ""

    for sentence in sentences:
        if len(sentence) > max_chars:
            if current:
                pieces.append(current)
                current = ""
            pieces.extend(
                sentence[i : i + max_chars].strip()
                for i in range(0, len(sentence), max_chars)
                if sentence[i : i + max_chars].strip()
            )
            continue
        candidate = f"{current} {sentence}".strip() if current else sentence
        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                pieces.append(current)
            current = sentence

    if current:
        pieces.append(current)
    return pieces


def _tail(text: str, overlap_chars: int) -> str:
    """Return an overlap tail that starts at a sentence boundary when possible.

    A plain character cut can split a number from its unit (for example,
    ``"at most 30" | "seconds"``). That hurts citation support because the
    retrieved chunk may contain the unit but not the value. The tail is allowed
    to grow to at most twice ``overlap_chars`` to keep the straddling sentence
    whole; otherwise it falls back to a word-aligned cut.
    """
    if overlap_chars <= 0 or not text:
        return ""

    start = max(0, len(text) - overlap_chars)
    prefix = text[:start]
    boundary = None
    for match in re.finditer(r"[.!?](?=\s|$)", prefix):
        boundary = match.end()

    if boundary is not None and start - boundary <= overlap_chars:
        start = boundary
    else:
        start = max(0, len(text) - 2 * overlap_chars)
        tail = text[start:]
        if len(text) > 2 * overlap_chars and " " in tail:
            tail = tail.split(" ", 1)[1]
        return tail.strip()

    return text[start:].strip()


def chunk_text(
    text: str,
    max_chars: int = MAX_CHARS,
    overlap_chars: int = OVERLAP_CHARS,
) -> list[str]:
    """Split normalized text into chunks of at most ``max_chars`` characters."""
    if max_chars <= 0:
        raise ValueError("max_chars must be positive")
    if overlap_chars < 0 or overlap_chars >= max_chars:
        raise ValueError("overlap_chars must be >= 0 and smaller than max_chars")

    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    pieces: list[str] = []
    for paragraph in paragraphs:
        if len(paragraph) <= max_chars:
            pieces.append(paragraph)
        else:
            pieces.extend(_split_long_paragraph(paragraph, max_chars))

    chunks: list[str] = []
    current = ""
    for piece in pieces:
        if not current:
            current = piece
            continue

        candidate = f"{current}\n\n{piece}"
        if len(candidate) <= max_chars:
            current = candidate
            continue

        chunks.append(current)
        tail = _tail(current, overlap_chars)
        with_overlap = f"{tail}\n\n{piece}" if tail else piece
        current = with_overlap if len(with_overlap) <= max_chars else piece

    if current:
        chunks.append(current)

    return [chunk for chunk in chunks if chunk.strip()]


def chunk_document(
    document: Document,
    max_chars: int = MAX_CHARS,
    overlap_chars: int = OVERLAP_CHARS,
) -> list[Chunk]:
    """Chunk one document while preserving its filename and page."""
    return [
        Chunk(text=text, source=document.source, page=document.page, chunk_index=index)
        for index, text in enumerate(chunk_text(document.text, max_chars, overlap_chars))
    ]


def chunk_documents(
    documents: list[Document],
    max_chars: int = MAX_CHARS,
    overlap_chars: int = OVERLAP_CHARS,
) -> list[Chunk]:
    """Chunk a list of documents in order."""
    chunks: list[Chunk] = []
    for document in documents:
        chunks.extend(chunk_document(document, max_chars, overlap_chars))
    return chunks
