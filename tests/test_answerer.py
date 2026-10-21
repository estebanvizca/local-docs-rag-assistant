from __future__ import annotations

from src.rag.answerer import ABSTENTION_MESSAGE, Answerer
from src.rag.retriever import RetrievedChunk


class FakeChat:
    def __init__(self, reply: str | None = None) -> None:
        self.reply = reply
        self.messages: list[dict[str, str]] | None = None

    def chat(self, messages):
        self.messages = messages
        if self.reply is None:
            raise AssertionError("Chat should not be called")
        return self.reply


def chunk(page: int | None = 2) -> RetrievedChunk:
    return RetrievedChunk(
        text="Negative results may be cached for at most 30 seconds.",
        source="open-systems-handbook.pdf",
        page=page,
        chunk_index=0,
        score=0.91,
    )


def test_answer_with_citations():
    answerer = Answerer(FakeChat("Negative results are cached for at most 30 seconds [1]."))

    result = answerer.answer("How long?", [chunk()])

    assert result.abstained is False
    assert result.answer.endswith("[1].")
    assert result.citations[0]["source"] == "open-systems-handbook.pdf"
    assert result.citations[0]["page"] == 2
    assert result.citations[0]["marker"] == "[1]"


def test_prompt_contains_source_page_and_rules():
    chat = FakeChat("Answer [1].")
    answerer = Answerer(chat)

    answerer.answer("Question?", [chunk(page=None)])

    assert chat.messages is not None
    system = chat.messages[0]["content"]
    user = chat.messages[1]["content"]
    assert "citation" in system.lower()
    assert "open-systems-handbook.pdf" in user
    assert "page 2" not in user  # page is None for this chunk
    assert "Question?" in user


def test_answer_without_citation_is_discarded():
    answerer = Answerer(FakeChat("Negative results are cached for 30 seconds."))

    result = answerer.answer("How long?", [chunk()])

    assert result.abstained is True
    assert result.answer == ABSTENTION_MESSAGE


def test_invalid_citation_marker_is_rejected():
    answerer = Answerer(FakeChat("The answer is 30 seconds [9]."))

    result = answerer.answer("How long?", [chunk()])

    assert result.abstained is True


def test_explicit_abstention_is_normalized():
    answerer = Answerer(FakeChat("I don't have enough information to answer that."))

    result = answerer.answer("How long?", [chunk()])

    assert result.abstained is True
    assert result.answer == ABSTENTION_MESSAGE


def test_no_chunks_means_no_model_call():
    answerer = Answerer(FakeChat(None))

    result = answerer.answer("How long?", [])

    assert result.abstained is True
    assert result.answer == ABSTENTION_MESSAGE
    assert result.citations == []
