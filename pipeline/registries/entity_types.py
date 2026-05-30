"""Data-driven определение типа сущности (ТЗ Этап 4.2).

Заменяет жёсткий if/elif по ключевым словам реестром: ключевые слова — данные
(расширяемый список), плюс возможность зарегистрировать кастомные детекторы без
правки ядра. Тип — бинарная ось Lean (def|prop).
"""
from __future__ import annotations

from typing import Callable, Optional

# Ключевые слова, указывающие на утверждение (prop). Данные, а не код — список
# можно дополнять (PROP_KEYWORDS.append(...)) или заменять.
PROP_KEYWORDS: list[str] = [
    "теорема", "лемма", "следствие", "утверждение", "свойство",
    "theorem", "lemma", "corollary", "proposition", "property",
]

# Кастомные детекторы: fn(texts, has_proof) -> Optional["def"|"prop"].
_DETECTORS: list[Callable[[list[str], bool], Optional[str]]] = []


def register_detector(fn: Callable[[list[str], bool], Optional[str]]):
    """Регистрирует кастомный детектор типа (для новых доменов/правил)."""
    _DETECTORS.append(fn)
    return fn


def clear_detectors() -> None:
    """Только для тестов."""
    _DETECTORS.clear()


def detect_entity_type(texts, has_proof: bool = False) -> str:
    """Определяет тип сущности. Наличие доказательства => prop; затем кастомные
    детекторы; затем ключевые слова; иначе def."""
    if has_proof:
        return "prop"
    for fn in _DETECTORS:
        kind = fn(list(texts), has_proof)
        if kind in ("def", "prop"):
            return kind
    combined = " ".join(texts).lower()
    for kw in PROP_KEYWORDS:
        if kw in combined:
            return "prop"
    return "def"
