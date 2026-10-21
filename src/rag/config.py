"""Configuration for the local RAG assistant.

All values come from environment variables (optionally loaded from ``.env``),
so models and paths are configuration rather than hardcoded assumptions.
"""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parents[2]
LOCAL_HOSTS = {"localhost", "127.0.0.1", "::1"}

load_dotenv(PROJECT_ROOT / ".env", override=False)


def _env_float(name: str, default: float) -> float:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be a number, got {raw!r}") from exc


def _env_int(name: str, default: int) -> int:
    raw = os.getenv(name, "").strip()
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise ValueError(f"{name} must be an integer, got {raw!r}") from exc


@dataclass(frozen=True)
class Settings:
    """Runtime settings for indexing, retrieval and generation."""

    ollama_host: str = "http://localhost:11434"
    chat_model: str = "llama3.2:latest"
    embed_model: str = "nomic-embed-text"
    top_k: int = 3
    similarity_threshold: float = 0.0
    request_timeout: float = 300.0
    docs_dir: Path = PROJECT_ROOT / "data" / "documents"
    index_path: Path = PROJECT_ROOT / "data" / "index.sqlite3"
    reports_dir: Path = PROJECT_ROOT / "reports"

    def __post_init__(self) -> None:
        if not 1 <= self.top_k <= 20:
            raise ValueError("TOP_K must be between 1 and 20")
        if not 0.0 <= self.similarity_threshold <= 1.0:
            raise ValueError("SIMILARITY_THRESHOLD must be between 0 and 1")
        if self.request_timeout <= 0:
            raise ValueError("REQUEST_TIMEOUT must be positive")

        hostname = urlparse(self.ollama_host).hostname
        if hostname not in LOCAL_HOSTS:
            raise ValueError(
                "OLLAMA_HOST must point to a local address "
                f"({', '.join(sorted(LOCAL_HOSTS))}); got {self.ollama_host!r}. "
                "This project never sends documents or questions to a remote service."
            )

    @classmethod
    def from_env(cls) -> "Settings":
        """Build settings from ``.env`` / environment variables."""
        return cls(
            ollama_host=os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/"),
            chat_model=os.getenv("OLLAMA_CHAT_MODEL", "llama3.2:latest"),
            embed_model=os.getenv("OLLAMA_EMBED_MODEL", "nomic-embed-text"),
            top_k=_env_int("TOP_K", 3),
            similarity_threshold=_env_float("SIMILARITY_THRESHOLD", 0.0),
            request_timeout=_env_float("REQUEST_TIMEOUT", 180.0),
        )
