from __future__ import annotations

import json

import pandas as pd
import pytest

from eval.evaluate import (
    key_fact_coverage,
    load_questions,
    matches_expected,
    summarize,
)
from src.rag.retriever import RetrievedChunk


def test_questions_have_fixed_split_and_contract():
    questions = load_questions()

    assert len(questions) == 24
    assert len({row["id"] for row in questions}) == 24
    for split, answerable, unanswerable in (("validation", 9, 3), ("test", 9, 3)):
        subset = [row for row in questions if row["split"] == split]
        assert sum(row["is_answerable"] for row in subset) == answerable
        assert sum(not row["is_answerable"] for row in subset) == unanswerable


def test_unanswerable_questions_have_no_expected_source():
    for row in load_questions():
        if not row["is_answerable"]:
            assert row["expected_source"] is None


def test_load_questions_rejects_duplicate_ids(tmp_path):
    path = tmp_path / "questions.jsonl"
    row = {
        "id": "x",
        "split": "validation",
        "question": "?",
        "expected_source": None,
        "expected_page": None,
        "key_facts": ["x"],
        "is_answerable": False,
    }
    path.write_text("\n".join(json.dumps(row) for _ in range(2)), encoding="utf-8")

    with pytest.raises(ValueError, match="Duplicate"):
        load_questions(path)


def test_matches_expected_checks_page_for_pdfs():
    result = RetrievedChunk(text="t", source="a.pdf", page=3, chunk_index=0, score=0.9)

    assert matches_expected(result, "a.pdf", 3)
    assert not matches_expected(result, "a.pdf", 4)
    assert not matches_expected(result, "b.pdf", 3)


def test_key_fact_coverage_uses_only_cited_text():
    citations = [
        {
            "text": "The reconnect timeout is 30 seconds and the retries stop after 3 attempts.",
            "source": "a.md",
            "page": None,
        }
    ]

    assert key_fact_coverage(citations, ["30 seconds", "3 attempts"]) == 1.0
    assert key_fact_coverage(citations, ["90 seconds"]) == 0.0
    assert key_fact_coverage([], ["30 seconds"]) == 0.0


def test_summary_reads_manual_labels():
    frame = pd.DataFrame(
        [
            {
                "is_answerable": True,
                "top1_hit": True,
                "top3_hit": True,
                "citation_source_match": True,
                "auto_supported": True,
                "abstained": False,
                "latency_ms": 100.0,
                "notes": "ok",
                "supported_human": "yes",
            },
            {
                "is_answerable": True,
                "top1_hit": False,
                "top3_hit": True,
                "citation_source_match": True,
                "auto_supported": False,
                "abstained": False,
                "latency_ms": 300.0,
                "notes": "ok",
                "supported_human": "no",
            },
            {
                "is_answerable": False,
                "top1_hit": False,
                "top3_hit": False,
                "citation_source_match": False,
                "auto_supported": False,
                "abstained": True,
                "latency_ms": 200.0,
                "notes": "ok",
                "correct_abstention_human": "yes",
            },
        ]
    )

    summary = summarize(frame)

    assert summary["retrieval_top1"] == 0.5
    assert summary["retrieval_top3"] == 1.0
    assert summary["manual_supported"] == 0.5
    assert summary["manual_abstention"] == 1.0
    assert summary["median_latency_ms"] == 200.0
