from __future__ import annotations

import pytest

from src.rag.config import Settings


def test_remote_ollama_host_is_rejected():
    with pytest.raises(ValueError, match="local address"):
        Settings(ollama_host="https://api.example.com")


def test_loopback_hosts_are_accepted():
    for host in ("http://localhost:11434", "http://127.0.0.1:11434", "http://[::1]:11434"):
        assert Settings(ollama_host=host).ollama_host == host


def test_threshold_bounds_are_validated():
    with pytest.raises(ValueError):
        Settings(similarity_threshold=1.5)
