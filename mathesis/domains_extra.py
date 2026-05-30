"""Пилотный второй доменный пакет (ТЗ 5.5) — проверка переносимости ядра.

Демонстрирует, что ядро (узлы/оркестратор/репозиторий/capabilities) НЕ зашито на
математику+Lean: достаточно зарегистрировать другой DomainPack. Здесь — пример
домена «формальная логика → Coq» с другой нормализацией терминов и другим целевым
языком. Полноценный корпус/продюсеры — будущая работа; цель пилота — показать, что
смена домена не требует правок ядра.
"""
from __future__ import annotations

import re

from mathesis.domains import DomainPack, register_domain


def _normalize_logic_term(term: str) -> str:
    """Нормализатор терминов логики (отличается от математического стеммера)."""
    t = term.lower().strip()
    t = re.sub(r"[^\w\s]", "", t)
    return " ".join(sorted(t.split()))


def build_logic_coq_pack() -> DomainPack:
    return DomainPack(
        name="logic_coq",
        entity_kinds=("def", "prop"),
        target_language="coq",
        normalize_term=_normalize_logic_term,
        capabilities=("extract_text", "to_lean", "embed"),  # to_lean -> здесь означает «to target language»
        required_representations=("coq_code",),
        description="Пилот: формальная логика → Coq (проверка переносимости ядра).",
    )


def register() -> DomainPack:
    """Регистрирует пилотный домен (идемпотентно для тестов)."""
    return register_domain(build_logic_coq_pack())
