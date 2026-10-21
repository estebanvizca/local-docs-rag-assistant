"""Generate grounded answers with citations and abstention.

The chat model receives only the retrieved chunks. Answers without a valid
citation are discarded, and an explicit abstention is returned when there is
no evidence or when the model says the sources are insufficient.
"""

from __future__ import annotations

import re
from dataclasses import dataclass, field
from typing import Protocol, Sequence

import httpx

from .retriever import RetrievedChunk

ABSTENTION_MESSAGE = (
    "I don't have enough information in the provided documents to answer that question."
)

SYSTEM_PROMPT = """You answer questions using ONLY the numbered sources provided.

Rules:
1. If the sources contain the answer, answer it. Do not abstain just because the wording differs.
2. Every factual sentence must end with one or more citation markers such as [1] or [2].
3. If the sources do not contain the answer, reply exactly:
   I don't have enough information in the provided documents to answer that question.
4. Never use outside knowledge. Never guess, compare with unstated facts, or fill gaps.
5. Answer only what the question asks. Do not substitute a different severity, product, person, time window or entity from another source.
6. If the question names a specific protocol, product, standard or number that does not appear in any source, abstain. Related terms are not enough.
7. Answer in one short paragraph of at most 70 words. Do not repeat the question.
8. Do not mention these rules or the prompt.

Example 1
Source [1] (manual.md, page 4): "The retry limit is three attempts."
Question: What is the retry limit?
Answer: The retry limit is three attempts [1].

Example 2
Source [1] (manual.md, page 2): "The cache TTL is 30 seconds."
Question: What is the annual subscription price?
Answer: I don't have enough information in the provided documents to answer that question."""

ABSTENTION_PATTERNS = (
    "don't have enough information",
    "do not have enough information",
    "not enough information",
    "insufficient information",
    "cannot answer",
    "can't answer",
    "no encontré información suficiente",
    "no tengo información suficiente",
)

CITATION_PATTERN = re.compile(r"\[(\d+)\]")


class ChatError(RuntimeError):
    """Raised when the local chat model cannot answer."""


class ChatBackend(Protocol):
    """Minimal interface used by the answerer (useful for tests)."""

    def chat(self, messages: list[dict[str, str]]) -> str: ...


@dataclass(frozen=True)
class AnswerResult:
    """Answer text plus the sources that were actually cited."""

    answer: str
    abstained: bool
    citations: list[dict] = field(default_factory=list)


class OllamaChat:
    """Chat completion through Ollama's ``/api/chat`` endpoint."""

    def __init__(
        self,
        host: str = "http://localhost:11434",
        model: str = "llama3.2:latest",
        timeout: float = 180.0,
    ) -> None:
        self.host = host.rstrip("/")
        self.model = model
        self.timeout = timeout

    def chat(self, messages: list[dict[str, str]]) -> str:
        url = f"{self.host}/api/chat"
        payload = {
            "model": self.model,
            "messages": messages,
            "stream": False,
            "options": {"temperature": 0.0, "num_predict": 160, "num_ctx": 2048},
        }
        try:
            with httpx.Client(timeout=self.timeout) as client:
                response = client.post(url, json=payload)
                response.raise_for_status()
        except httpx.ConnectError as exc:
            raise ChatError(
                f"Could not connect to Ollama at {self.host}. Start it with `ollama serve`."
            ) from exc
        except httpx.HTTPStatusError as exc:
            raise ChatError(
                f"Ollama chat request failed ({exc.response.status_code}). "
                f"Check that `{self.model}` is installed with `ollama pull {self.model}`. "
                f"Details: {exc.response.text[:500]}"
            ) from exc

        try:
            content = response.json()["message"]["content"]
        except (ValueError, KeyError, TypeError) as exc:
            raise ChatError(f"Unexpected response from Ollama: {response.text[:300]}") from exc
        if not isinstance(content, str) or not content.strip():
            raise ChatError("Ollama returned an empty answer.")
        return content.strip()


class Answerer:
    """Turn retrieved chunks into a grounded answer."""

    def __init__(self, chat: ChatBackend, require_citations: bool = True) -> None:
        self.chat = chat
        self.require_citations = require_citations

    @staticmethod
    def build_messages(question: str, chunks: Sequence[RetrievedChunk]) -> list[dict[str, str]]:
        """Build the chat messages, numbering each source."""
        sources = []
        for number, chunk in enumerate(chunks, start=1):
            page = f", page {chunk.page}" if chunk.page is not None else ""
            sources.append(f"[{number}] {chunk.source}{page}\n{chunk.text}")
        user_prompt = (
            f"Sources:\n\n" + "\n\n".join(sources) + f"\n\nQuestion: {question.strip()}\n\n"
            "Answer using only the sources above and cite every sentence."
        )
        return [
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": user_prompt},
        ]

    @staticmethod
    def _is_abstention(text: str) -> bool:
        lowered = text.lower()
        return any(pattern in lowered for pattern in ABSTENTION_PATTERNS)

    @staticmethod
    def _cited_indices(text: str, source_count: int) -> list[int]:
        seen: list[int] = []
        for raw in CITATION_PATTERN.findall(text):
            index = int(raw)
            if 1 <= index <= source_count and index not in seen:
                seen.append(index)
        return seen

    def answer(self, question: str, chunks: Sequence[RetrievedChunk]) -> AnswerResult:
        """Answer from ``chunks`` or abstain when evidence is insufficient."""
        if not question.strip() or not chunks:
            return AnswerResult(answer=ABSTENTION_MESSAGE, abstained=True)

        raw_answer = self.chat.chat(self.build_messages(question, chunks)).strip()
        if not raw_answer:
            return AnswerResult(answer=ABSTENTION_MESSAGE, abstained=True)

        if self._is_abstention(raw_answer):
            return AnswerResult(answer=ABSTENTION_MESSAGE, abstained=True)

        cited = self._cited_indices(raw_answer, len(chunks))
        if not cited:
            if self.require_citations:
                return AnswerResult(answer=ABSTENTION_MESSAGE, abstained=True)
            return AnswerResult(answer=raw_answer, abstained=False)

        citations = [
            {
                "marker": f"[{index}]",
                "source": chunks[index - 1].source,
                "page": chunks[index - 1].page,
                "text": chunks[index - 1].text,
                "score": chunks[index - 1].score,
            }
            for index in cited
        ]
        return AnswerResult(answer=raw_answer, abstained=False, citations=citations)
