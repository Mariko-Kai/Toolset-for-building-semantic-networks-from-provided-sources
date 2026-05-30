"""Тесты pipeline.retry_utils (ТЗ 1.3)."""
from __future__ import annotations

from pipeline.retry_utils import RepeatedErrorDetector, backoff_delay


def test_backoff_is_exponential_and_capped():
    assert backoff_delay(1, base=1.0, factor=2.0) == 1.0
    assert backoff_delay(2, base=1.0, factor=2.0) == 2.0
    assert backoff_delay(3, base=1.0, factor=2.0) == 4.0
    assert backoff_delay(10, base=1.0, factor=2.0, max_delay=5.0) == 5.0
    assert backoff_delay(0, base=1.5) == 1.5  # защита от attempt<1


def test_detector_triggers_on_consecutive_repeats():
    d = RepeatedErrorDetector(max_repeats=2)
    assert d.record("Line 5: unknown identifier 'foo'") is False
    # Та же ошибка с другим номером строки — считается повтором (нормализация чисел).
    assert d.record("Line 9: unknown identifier 'foo'") is True


def test_detector_resets_on_different_error():
    d = RepeatedErrorDetector(max_repeats=2)
    assert d.record("error A") is False
    assert d.record("error B") is False  # другая ошибка — счётчик сброшен
    assert d.record("error B") is True


def test_detector_ignores_empty():
    d = RepeatedErrorDetector(max_repeats=1)
    assert d.record("") is False
    assert d.record("   ") is False
