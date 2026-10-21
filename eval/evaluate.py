"""Evaluate retrieval, grounding and abstention on the labeled question set.

Examples
--------
Build the index and tune the similarity threshold on validation:

    python eval/evaluate.py --tune-threshold

Run the final evaluation (validation + test):

    python eval/evaluate.py

Only retrieval, without calling the chat model:

    python eval/evaluate.py --retrieval-only

Summarize a CSV after filling the manual ``supported_human`` and
``correct_abstention_human`` columns:

    python eval/evaluate.py --summarize reports/eval_test.csv
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import replace
from datetime import datetime, timezone
from pathlib import Path

import pandas as pd

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.rag.answerer import CITATION_PATTERN  # noqa: E402
from src.rag.config import Settings  # noqa: E402
from src.rag.pipeline import RagPipeline  # noqa: E402
from src.rag.retriever import Retriever, RetrievedChunk  # noqa: E402

QUESTIONS_PATH = PROJECT_ROOT / "eval" / "questions.jsonl"
EXPECTED_COUNTS = {
    "validation": {"answerable": 9, "unanswerable": 3},
    "test": {"answerable": 9, "unanswerable": 3},
}
REQUIRED_FIELDS = {
    "id",
    "split",
    "question",
    "expected_source",
    "expected_page",
    "key_facts",
    "is_answerable",
}

STOPWORDS = {
    "a", "an", "and", "any", "are", "as", "at", "be", "been", "before", "after",
    "by", "can", "does", "do", "each", "every", "for", "from", "has", "have",
    "how", "if", "in", "into", "is", "it", "its", "less", "may", "more", "most",
    "must", "not", "of", "on", "one", "only", "or", "over", "per", "should",
    "than", "that", "the", "their", "then", "there", "these", "they", "this",
    "to", "two", "under", "up", "use", "used", "using", "was", "were", "what",
    "when", "which", "who", "will", "with", "within", "without",
}


def load_questions(path: Path = QUESTIONS_PATH) -> list[dict]:
    """Load and validate the JSONL evaluation set."""
    if not path.exists():
        raise FileNotFoundError(f"Evaluation questions not found: {path}")

    questions: list[dict] = []
    seen_ids: set[str] = set()
    with path.open(encoding="utf-8") as handle:
        for line_number, line in enumerate(handle, start=1):
            if not line.strip():
                continue
            try:
                row = json.loads(line)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON on {path.name}:{line_number}: {exc}") from exc

            missing = REQUIRED_FIELDS - row.keys()
            if missing:
                raise ValueError(f"Missing fields on line {line_number}: {sorted(missing)}")
            if row["id"] in seen_ids:
                raise ValueError(f"Duplicate question id: {row['id']}")
            if row["split"] not in EXPECTED_COUNTS:
                raise ValueError(f"Invalid split {row['split']!r} on line {line_number}")
            if not isinstance(row["is_answerable"], bool):
                raise ValueError(f"is_answerable must be boolean on line {line_number}")
            if not isinstance(row["key_facts"], list) or not row["key_facts"]:
                raise ValueError(f"key_facts must be a non-empty list on line {line_number}")
            seen_ids.add(row["id"])
            questions.append(row)

    for split, expected in EXPECTED_COUNTS.items():
        subset = [row for row in questions if row["split"] == split]
        answerable = sum(row["is_answerable"] for row in subset)
        unanswerable = len(subset) - answerable
        if (answerable, unanswerable) != (expected["answerable"], expected["unanswerable"]):
            raise ValueError(
                f"Split {split!r} has {answerable} answerable / {unanswerable} unanswerable; "
                f"expected {expected['answerable']} / {expected['unanswerable']}."
            )
    return questions


def page_label(page: int | None) -> str:
    return f"page {page}" if page is not None else "text"


def matches_expected(result: RetrievedChunk, expected_source: str, expected_page: int | None) -> bool:
    if result.source != expected_source:
        return False
    if expected_page is not None and result.page != expected_page:
        return False
    return True


def cited_chunks(citations: list[dict]) -> list[dict]:
    return citations or []


def content_tokens(text: str) -> set[str]:
    words = re.findall(r"[a-z0-9]+", text.lower())
    return {word for word in words if word not in STOPWORDS and (len(word) > 2 or word.isdigit())}


def key_fact_coverage(citations: list[dict], key_facts: list[str]) -> float:
    """Fraction of key facts whose content tokens appear in the cited passages."""
    if not citations:
        return 0.0
    cited_text = " ".join(citation["text"] for citation in citations)
    cited_tokens = content_tokens(cited_text)
    if not cited_tokens:
        return 0.0

    covered = 0
    for fact in key_facts:
        tokens = content_tokens(fact)
        if not tokens or tokens.issubset(cited_tokens):
            covered += 1
    return covered / len(key_facts)


def citation_source_match(
    citations: list[dict], expected_source: str, expected_page: int | None
) -> bool:
    for citation in citations:
        if citation["source"] != expected_source:
            continue
        if expected_page is not None and citation["page"] != expected_page:
            continue
        return True
    return False


def has_valid_citations(answer: str) -> bool:
    return bool(CITATION_PATTERN.search(answer))


def evaluate_rows(
    pipeline: RagPipeline,
    rows: list[dict],
    top_k: int,
    threshold: float,
    retrieval_only: bool = False,
) -> pd.DataFrame:
    """Run retrieval (and optionally answering) for every question."""
    retriever = Retriever(
        index=pipeline.index,
        embedder=pipeline.embedder,
        top_k=top_k,
        threshold=0.0 if retrieval_only else threshold,
    )
    records: list[dict] = []

    for row in rows:
        started = datetime.now(timezone.utc)
        error = ""
        retrieved: list[RetrievedChunk] = []
        answer = ""
        abstained = False
        citations: list[dict] = []

        try:
            if retrieval_only:
                retrieved = retriever.retrieve(row["question"])
                latency_ms = 0.0
            else:
                result = pipeline.ask(row["question"], top_k=top_k, threshold=threshold)
                retrieved = result.retrieved
                answer = result.answer
                abstained = result.abstained
                citations = result.citations
                latency_ms = result.latency_ms
        except Exception as exc:  # noqa: BLE001 - recorded per row
            error = f"{type(exc).__name__}: {exc}"

        top1 = retrieved[0] if retrieved else None
        top3_hit = any(
            matches_expected(chunk, row["expected_source"], row["expected_page"])
            for chunk in retrieved
        )
        top1_hit = bool(
            top1 and matches_expected(top1, row["expected_source"], row["expected_page"])
        )
        coverage = key_fact_coverage(citations, row["key_facts"]) if not retrieval_only else 0.0
        auto_supported = bool(
            not retrieval_only
            and not abstained
            and citations
            and citation_source_match(citations, row["expected_source"], row["expected_page"])
            and coverage >= 0.8
        )

        records.append(
            {
                "id": row["id"],
                "split": row["split"],
                "is_answerable": row["is_answerable"],
                "question": row["question"],
                "expected_source": row["expected_source"],
                "expected_page": row["expected_page"],
                "key_facts": " | ".join(row["key_facts"]),
                "retrieved_sources": "; ".join(
                    f"{chunk.source}:{chunk.page}@{chunk.score:.3f}" for chunk in retrieved
                ),
                "top1_source": top1.source if top1 else "",
                "top1_page": top1.page if top1 else "",
                "top1_score": round(top1.score, 4) if top1 else "",
                "top1_hit": top1_hit,
                "top3_hit": top3_hit,
                "citation_source_match": citation_source_match(
                    citations, row["expected_source"], row["expected_page"]
                ),
                "citation_count": len(citations),
                "cited_sources": "; ".join(
                    f"{citation['marker']} {citation['source']}:{citation['page']}@{citation['score']:.3f}"
                    for citation in citations
                ),
                "cited_text": "\n\n".join(citation["text"] for citation in citations),
                "answer_has_citation": has_valid_citations(answer),
                "key_fact_coverage": round(coverage, 3),
                "auto_supported": auto_supported,
                "abstained": abstained,
                "answer": answer,
                "latency_ms": round(latency_ms, 1),
                "supported_human": "",
                "correct_abstention_human": "",
                "notes": error or f"started {started.isoformat(timespec='seconds')}",
            }
        )

    return pd.DataFrame.from_records(records)


def _manual_labels(series: pd.Series) -> tuple[pd.Series, pd.Series]:
    values = series.astype(str).str.strip().str.lower()
    filled = values.isin({"yes", "no", "y", "n", "true", "false", "1", "0"})
    positive = values.isin({"yes", "y", "true", "1"})
    return filled, positive


def summarize(frame: pd.DataFrame) -> dict:
    """Compute automatic metrics and, when present, manual ones."""
    answerable = frame[frame["is_answerable"] == True]  # noqa: E712 - pandas boolean column
    unanswerable = frame[frame["is_answerable"] == False]  # noqa: E712

    summary: dict = {
        "questions": int(len(frame)),
        "answerable": int(len(answerable)),
        "unanswerable": int(len(unanswerable)),
        "retrieval_top1": round(float(answerable["top1_hit"].mean()), 3),
        "retrieval_top3": round(float(answerable["top3_hit"].mean()), 3),
        "citation_source_match": round(float(answerable["citation_source_match"].mean()), 3),
        "auto_supported": round(float(answerable["auto_supported"].mean()), 3),
        "abstention_unanswerable": round(float(unanswerable["abstained"].mean()), 3),
        "median_latency_ms": round(float(frame["latency_ms"].median()), 1) if len(frame) else 0.0,
        "errors": int((frame["notes"].astype(str).str.contains("Error|Exception", regex=True)).sum()),
    }

    filled, positive = _manual_labels(answerable["supported_human"])
    if filled.any():
        summary["manual_supported"] = round(float(positive[filled].mean()), 3)
        summary["manual_supported_n"] = int(filled.sum())

    filled, positive = _manual_labels(unanswerable["correct_abstention_human"])
    if filled.any():
        summary["manual_abstention"] = round(float(positive[filled].mean()), 3)
        summary["manual_abstention_n"] = int(filled.sum())

    return summary


def print_summary(summary: dict) -> None:
    print("\nEvaluation summary")
    print("------------------")
    for key, value in summary.items():
        print(f"{key:28} {value}")


def tune_threshold(pipeline: RagPipeline, rows: list[dict], top_k: int) -> float:
    """Choose a threshold on validation retrieval only; never use test."""
    validation = [row for row in rows if row["split"] == "validation"]
    retriever = Retriever(
        index=pipeline.index,
        embedder=pipeline.embedder,
        top_k=top_k,
        threshold=0.0,
    )
    retrieved_by_id = {row["id"]: retriever.retrieve(row["question"]) for row in validation}

    candidates = [round(value / 100, 2) for value in range(0, 96, 5)]
    table: list[dict] = []
    for threshold in candidates:
        hits = 0
        false_evidence = 0
        for row in validation:
            visible = [chunk for chunk in retrieved_by_id[row["id"]] if chunk.score >= threshold]
            if row["is_answerable"]:
                if any(
                    matches_expected(chunk, row["expected_source"], row["expected_page"])
                    for chunk in visible
                ):
                    hits += 1
            elif visible:
                false_evidence += 1
        table.append(
            {
                "threshold": threshold,
                "answerable_top3_hits": hits,
                "unanswerable_with_evidence": false_evidence,
            }
        )

    # Maximize validation hits, then minimize evidence for unanswerable
    # questions, then prefer the more conservative (higher) threshold.
    best = max(
        table,
        key=lambda row: (
            row["answerable_top3_hits"],
            -row["unanswerable_with_evidence"],
            row["threshold"],
        ),
    )

    print("\nThreshold tuning (validation split only)")
    print("---------------------------------------")
    for row in table:
        print(
            f"{row['threshold']:.2f}  hits {row['answerable_top3_hits']}/9  "
            f"unanswerable evidence {row['unanswerable_with_evidence']}/3"
        )
    print(f"\nRecommended SIMILARITY_THRESHOLD={best['threshold']:.2f}")

    reports_dir = pipeline.settings.reports_dir
    reports_dir.mkdir(parents=True, exist_ok=True)
    (reports_dir / "threshold_tuning.json").write_text(
        json.dumps({"best": best["threshold"], "table": table}, indent=2),
        encoding="utf-8",
    )
    return float(best["threshold"])


def ensure_index(pipeline: RagPipeline, rebuild: bool) -> None:
    report = pipeline.build_index(force=rebuild)
    state = "built" if report.rebuilt else "already current"
    print(
        f"Index {state}: {report.chunks} chunks from {report.documents} documents "
        f"({pipeline.settings.index_path})"
    )


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--questions", type=Path, default=QUESTIONS_PATH)
    parser.add_argument("--split", choices=["all", "validation", "test"], default="all")
    parser.add_argument("--top-k", type=int, default=None)
    parser.add_argument("--threshold", type=float, default=None)
    parser.add_argument("--tune-threshold", action="store_true")
    parser.add_argument("--retrieval-only", action="store_true")
    parser.add_argument("--rebuild", action="store_true")
    parser.add_argument("--reports-dir", type=Path, default=None)
    parser.add_argument("--summarize", type=Path, default=None)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)

    if args.summarize:
        frame = pd.read_csv(args.summarize)
        print_summary(summarize(frame))
        return 0

    settings = Settings.from_env()
    if args.reports_dir:
        settings = replace(settings, reports_dir=args.reports_dir)
    if args.threshold is not None:
        settings = replace(settings, similarity_threshold=args.threshold)

    questions = load_questions(args.questions)
    pipeline = RagPipeline(settings=settings)
    ensure_index(pipeline, rebuild=args.rebuild)

    try:
        if args.tune_threshold:
            tune_threshold(pipeline, questions, top_k=args.top_k or settings.top_k)
            return 0

        if args.split == "all":
            splits = ["validation", "test"]
        else:
            splits = [args.split]

        threshold = settings.similarity_threshold
        reports_dir = settings.reports_dir
        reports_dir.mkdir(parents=True, exist_ok=True)

        for split in splits:
            rows = [row for row in questions if row["split"] == split]
            frame = evaluate_rows(
                pipeline=pipeline,
                rows=rows,
                top_k=args.top_k or settings.top_k,
                threshold=threshold,
                retrieval_only=args.retrieval_only,
            )
            output = reports_dir / f"eval_{split}.csv"
            frame.to_csv(output, index=False)
            summary = summarize(frame)
            summary.update(
                {
                    "split": split,
                    "threshold": threshold,
                    "top_k": args.top_k or settings.top_k,
                    "embed_model": settings.embed_model,
                    "chat_model": settings.chat_model,
                    "retrieval_only": args.retrieval_only,
                    "generated_at": datetime.now(timezone.utc).isoformat(timespec="seconds"),
                    "csv": str(output),
                }
            )
            (reports_dir / f"summary_{split}.json").write_text(
                json.dumps(summary, indent=2), encoding="utf-8"
            )
            print_summary(summary)
            print(f"CSV written to {output}")
    finally:
        pipeline.close()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
