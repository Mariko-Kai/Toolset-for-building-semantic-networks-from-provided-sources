"""Утилиты ретраев для циклов конвейера (ТЗ Этап 1.3).

  * backoff_delay — экспоненциальная задержка с потолком.
  * RepeatedErrorDetector — определяет, что цикл «застрял»: одна и та же ошибка
    (тот же фидбек модели) повторяется подряд, дальнейшие попытки бессмысленны.

Чистые функции/классы без побочных эффектов — легко тестируются без LLM/сети.
"""
from __future__ import annotations

import hashlib


def backoff_delay(attempt: int, base: float = 1.0, factor: float = 2.0, max_delay: float = 30.0) -> float:
    """Задержка для попытки `attempt` (нумерация с 1): base * factor**(attempt-1),
    ограниченная сверху `max_delay`. Для attempt<=1 возвращает base."""
    if attempt < 1:
        attempt = 1
    delay = base * (factor ** (attempt - 1))
    return min(delay, max_delay)


def _signature(text: str) -> str:
    """Нормализованная подпись сообщения об ошибке (без чисел/пробелов),
    чтобы «та же ошибка с другими номерами строк» считалась повтором."""
    import re
    normalized = re.sub(r"\d+", "#", text or "")
    normalized = re.sub(r"\s+", " ", normalized).strip().lower()
    return hashlib.sha256(normalized.encode("utf-8")).hexdigest()


class RepeatedErrorDetector:
    """Считает подряд идущие повторы одной и той же ошибки.

    `record(error)` возвращает True, когда одинаковая (по нормализованной
    подписи) ошибка зафиксирована `max_repeats` раз подряд — сигнал прекратить
    цикл. Иная ошибка сбрасывает счётчик. Пустые строки игнорируются.
    """

    def __init__(self, max_repeats: int = 2):
        if max_repeats < 1:
            max_repeats = 1
        self.max_repeats = max_repeats
        self._last_sig: str | None = None
        self._count = 0

    def record(self, error: str) -> bool:
        if not error or not error.strip():
            return False
        sig = _signature(error)
        if sig == self._last_sig:
            self._count += 1
        else:
            self._last_sig = sig
            self._count = 1
        return self._count >= self.max_repeats

    def reset(self) -> None:
        self._last_sig = None
        self._count = 0
