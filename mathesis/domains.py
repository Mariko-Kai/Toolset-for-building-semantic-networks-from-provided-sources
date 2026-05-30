"""Доменные пакеты (ТЗ Этап 5.4) — переносимость ядра на другие задачи.

`DomainPack` бандлит доменно-специфичные знания (виды сущностей, нормализация
терминов, целевой язык формализации, доступные возможности, требуемые
представления). Ядро (узлы, оркестратор, репозиторий) домен-агностично; смена
домена = другой DomainPack.

`math_lean` — первый пакет (математика → Lean), переиспользует уже вынесенные
реестры (Этап 4.2). Второй (пилотный) пакет на Этапе 5.5 проверяет переносимость.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional


@dataclass
class DomainPack:
    name: str
    entity_kinds: tuple = ("def", "prop")
    target_language: str = "lean4"
    detect_entity_type: Optional[Callable] = None     # (texts, has_proof) -> kind
    normalize_term: Optional[Callable] = None          # стеммер/нормализатор
    capabilities: tuple = ()                            # имена возможностей домена
    required_representations: tuple = ()                # что нужно, чтобы «сохранить» объект
    description: str = ""


_DOMAINS: dict[str, DomainPack] = {}


def register_domain(pack: DomainPack) -> DomainPack:
    _DOMAINS[pack.name] = pack
    return pack


def get_domain(name: str) -> DomainPack:
    if name not in _DOMAINS:
        raise KeyError(f"Домен '{name}' не зарегистрирован. Есть: {sorted(_DOMAINS)}")
    return _DOMAINS[name]


def available_domains() -> list[str]:
    return sorted(_DOMAINS)


def clear_domains() -> None:
    """Только для тестов."""
    _DOMAINS.clear()


def build_math_lean_pack() -> DomainPack:
    """Математика → Lean: переиспользует data-driven реестры Этапа 4.2."""
    from pipeline.registries.entity_types import detect_entity_type
    return DomainPack(
        name="math_lean",
        entity_kinds=("def", "prop"),
        target_language="lean4",
        detect_entity_type=detect_entity_type,
        capabilities=("extract_text", "ocr", "synth_latex", "to_lean", "embed"),
        required_representations=("latex", "lean_code"),
        description="Формализация математики из учебников в Lean 4.",
    )


# Регистрируем дефолтный домен при импорте.
register_domain(build_math_lean_pack())
