"""Load and normalize documents from a local folder.

Supported formats: PDF, Markdown and plain text. PDFs keep their page number so
answers can cite the exact page; text formats use ``page=None``.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from pathlib import Path

try:  # PyMuPDF >= 1.24 exposes the non-deprecated module name.
    import pymupdf
except ImportError:  # pragma: no cover - fallback for older installations
    import fitz as pymupdf

SUPPORTED_SUFFIXES = {".pdf", ".md", ".txt"}


class UnsupportedDocumentError(ValueError):
    """Raised when a file type is outside the MVP scope."""


@dataclass(frozen=True)
class Document:
    """A single page or text unit extracted from a source file."""

    text: str
    source: str
    page: int | None = None


def _normalize(text: str) -> str:
    """Normalize line endings and whitespace while keeping paragraphs."""
    text = text.replace("\r\n", "\n").replace("\r", "\n")
    lines = [re.sub(r"[ \t]+", " ", line).strip() for line in text.split("\n")]
    text = "\n".join(lines)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip()


def load_file(path: Path) -> list[Document]:
    """Load one supported file into one or more ``Document`` records."""
    path = Path(path)
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_SUFFIXES:
        raise UnsupportedDocumentError(
            f"Unsupported file type {suffix!r}: {path.name}. "
            f"Allowed: {', '.join(sorted(SUPPORTED_SUFFIXES))}"
        )

    if suffix == ".pdf":
        return _load_pdf(path)

    text = path.read_text(encoding="utf-8", errors="replace")
    normalized = _normalize(text)
    return [Document(text=normalized, source=path.name, page=None)] if normalized else []


def _load_pdf(path: Path) -> list[Document]:
    documents: list[Document] = []
    with pymupdf.open(path) as pdf:
        for index, page in enumerate(pdf, start=1):
            text = _normalize(page.get_text("text"))
            if text:
                documents.append(Document(text=text, source=path.name, page=index))
    return documents


def load_documents(docs_dir: Path) -> list[Document]:
    """Load every supported document in ``docs_dir``, sorted by filename."""
    docs_dir = Path(docs_dir)
    if not docs_dir.exists():
        raise FileNotFoundError(f"Documents folder not found: {docs_dir}")

    documents: list[Document] = []
    for path in sorted(docs_dir.iterdir()):
        if path.is_file() and not path.name.startswith(".") and path.suffix.lower() in SUPPORTED_SUFFIXES:
            documents.extend(load_file(path))
    return documents
