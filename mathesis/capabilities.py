"""Реестр возможностей и детектор недостающих представлений (ТЗ Этап 5.4).

«Возможность» (Capability) — зарегистрированный способ ПРОИЗВЕСТИ некоторое
представление объекта (текст со скана, LaTeX, Lean-код, эмбеддинг, …).

Главная ценность для цели «дописывать недостающий функционал»:
`missing_representations(required)` показывает, какие требуемые представления
объекта НЕ покрыты ни одной возможностью — это пробел архитектуры, который
агентный слой (Этап 5.6) может достроить (синтез новой возможности).

Абстракция выведена из ≥2 конкретных примеров (извлечение текста, OCR) — не
спекулятивно.
"""
from __future__ import annotations

from dataclasses import dataclass
from typing import Callable, Optional


@dataclass
class Capability:
    name: str
    provides: str                       # тип представления, напр. "lean_code", "page_text"
    description: str = ""
    producer: Optional[Callable] = None  # produce(target) -> представление (опционально)


_CAPS: dict[str, Capability] = {}


def register_capability(cap: Capability) -> Capability:
    _CAPS[cap.name] = cap
    return cap


def get_capability(name: str) -> Capability:
    if name not in _CAPS:
        raise KeyError(f"Возможность '{name}' не зарегистрирована. Есть: {sorted(_CAPS)}")
    return _CAPS[name]


def all_capabilities() -> list[Capability]:
    return list(_CAPS.values())


def capabilities_for(provides: str) -> list[Capability]:
    return [c for c in _CAPS.values() if c.provides == provides]


def has_capability(provides: str) -> bool:
    return any(c.provides == provides for c in _CAPS.values())


def missing_representations(required) -> set[str]:
    """Какие требуемые представления не покрыты ни одной возможностью (пробел)."""
    return {r for r in required if not has_capability(r)}


def produce(name: str, *args, **kwargs):
    """Вызывает продюсер возможности (получить представление). Бросает, если у
    возможности нет продюсера."""
    cap = get_capability(name)
    if cap.producer is None:
        raise ValueError(f"У возможности '{name}' нет продюсера (representation-only).")
    return cap.producer(*args, **kwargs)


# --- Реальные продюсеры (ленивые, чтобы не тянуть тяжёлые зависимости при импорте) ---
def _produce_embedding(text: str):
    from pipeline.model_manager import ModelManager
    return ModelManager.get_instance().get_embedding(text, role="embed")


def _produce_ocr(images: list, prompt: str = "Extract text and math as LaTeX-friendly plain text."):
    from pipeline.model_manager import ModelManager
    return ModelManager.get_instance().query_vision(prompt, images, role="cv")


def clear_capabilities() -> None:
    """Только для тестов."""
    _CAPS.clear()


def register_defaults() -> None:
    """Регистрирует базовые возможности математического домена (идемпотентно)."""
    defaults = [
        Capability("extract_text", "raw_text", "Извлечение текстового слоя PDF"),
        Capability("ocr", "raw_text", "Распознавание сканов через vision-модель", producer=_produce_ocr),
        Capability("synth_latex", "latex", "Синтез канонического LaTeX"),
        Capability("to_lean", "lean_code", "Трансляция в Lean 4"),
        Capability("embed", "embedding", "Векторный эмбеддинг для поиска", producer=_produce_embedding),
    ]
    for c in defaults:
        _CAPS.setdefault(c.name, c)


register_defaults()
