"""Tests never call a real AI model: hide every key (including ones in a .env one folder up)."""
import pytest

from backend import llm


@pytest.fixture(autouse=True)
def _no_real_model_keys(monkeypatch, tmp_path):
    monkeypatch.setattr(llm, "USAGE_LOG", tmp_path / "usage_log.jsonl")  # never touch the real usage log
    monkeypatch.setattr(llm, "_loaded", True)  # don't read .env files during tests
    for k in ("PORTKEY_API_KEY", "OPENAI_API_KEY", "ANTHROPIC_API_KEY", "ANTHROPIC_AUTH_TOKEN"):
        monkeypatch.delenv(k, raising=False)
