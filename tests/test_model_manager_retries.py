"""Тесты ретраев и явных ошибок ModelManager (ТЗ 1.5)."""
from __future__ import annotations

import pytest

from pipeline import model_manager
from pipeline.model_manager import ModelError, ModelManager


class _FlakyStrategy:
    """Возвращает пустую строку первые `fail_times` раз, затем 'ok'."""

    def __init__(self, fail_times: int):
        self.fail_times = fail_times
        self.calls = 0

    def generate_content(self, prompt, system_prompt=None, json_mode=False, stream_callback=None):
        self.calls += 1
        return "" if self.calls <= self.fail_times else "ok"

    def get_embedding(self, text):
        self.calls += 1
        return None if self.calls <= self.fail_times else [0.1, 0.2]


@pytest.fixture
def manager(monkeypatch):
    # Ускоряем backoff и пересоздаём singleton для изоляции.
    monkeypatch.setattr(model_manager, "MODEL_RETRY_BASE_DELAY", 0.0)
    ModelManager._instance = None
    mgr = ModelManager()
    yield mgr
    ModelManager._instance = None


def test_query_llm_recovers_after_transient_failure(manager):
    manager.strategies["main"] = _FlakyStrategy(fail_times=1)
    assert manager.query_llm("hi", max_retries=2) == "ok"


def test_query_llm_returns_empty_after_exhaustion_non_strict(manager):
    manager.strategies["main"] = _FlakyStrategy(fail_times=99)
    assert manager.query_llm("hi", max_retries=2) == ""


def test_query_llm_strict_raises_after_exhaustion(manager):
    manager.strategies["main"] = _FlakyStrategy(fail_times=99)
    with pytest.raises(ModelError):
        manager.query_llm("hi", max_retries=1, strict=True)


def test_query_llm_does_not_retry_when_streaming(manager):
    strat = _FlakyStrategy(fail_times=99)
    manager.strategies["main"] = strat
    manager.query_llm("hi", stream_callback=lambda c: None, max_retries=5)
    assert strat.calls == 1, "стриминг не должен ретраиться"


def test_get_embedding_strict_raises(manager):
    manager.strategies["main"] = _FlakyStrategy(fail_times=99)
    with pytest.raises(ModelError):
        manager.get_embedding("text", max_retries=1, strict=True)
