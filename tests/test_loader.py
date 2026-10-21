from __future__ import annotations

import pymupdf

from src.rag.loader import (
    SUPPORTED_SUFFIXES,
    UnsupportedDocumentError,
    load_documents,
    load_file,
)


def test_load_markdown_normalizes_whitespace(tmp_path):
    path = tmp_path / "guide.md"
    path.write_text("Title\r\n\r\n\r\nBody   with   spaces  \n", encoding="utf-8")

    documents = load_file(path)

    assert len(documents) == 1
    assert documents[0].source == "guide.md"
    assert documents[0].page is None
    assert "\r" not in documents[0].text
    assert "Body with spaces" in documents[0].text
    assert "\n\n\n" not in documents[0].text


def test_load_pdf_preserves_page_numbers(tmp_path):
    path = tmp_path / "manual.pdf"
    pdf = pymupdf.open()
    pdf.new_page().insert_text((72, 72), "First page content")
    pdf.new_page().insert_text((72, 72), "Second page content")
    pdf.save(path)
    pdf.close()

    documents = load_file(path)

    assert [document.page for document in documents] == [1, 2]
    assert all(document.source == "manual.pdf" for document in documents)
    assert "First page" in documents[0].text
    assert "Second page" in documents[1].text


def test_load_documents_skips_unsupported_and_hidden_files(tmp_path):
    (tmp_path / "a.md").write_text("Alpha", encoding="utf-8")
    (tmp_path / "b.txt").write_text("Beta", encoding="utf-8")
    (tmp_path / "c.json").write_text("{}", encoding="utf-8")
    (tmp_path / ".hidden.md").write_text("Hidden", encoding="utf-8")

    documents = load_documents(tmp_path)

    assert [document.source for document in documents] == ["a.md", "b.txt"]


def test_unsupported_extension_raises(tmp_path):
    path = tmp_path / "data.csv"
    path.write_text("a,b", encoding="utf-8")

    try:
        load_file(path)
    except UnsupportedDocumentError as error:
        assert ".csv" in str(error)
    else:  # pragma: no cover
        raise AssertionError("Expected UnsupportedDocumentError")

    assert ".pdf" in SUPPORTED_SUFFIXES
