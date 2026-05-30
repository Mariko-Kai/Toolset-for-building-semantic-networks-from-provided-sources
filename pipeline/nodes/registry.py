"""Реестр узлов (ТЗ Этап 4.1).

Добавление нового узла = новый класс + декоратор `@register_node`, без правки
ядра/оркестратора. Это основа расширяемости и (Этап 5) подключаемых
возможностей/доменных пакетов.
"""
from __future__ import annotations

from typing import Callable

_REGISTRY: dict[str, type] = {}


def register_node(name: str | None = None) -> Callable[[type], type]:
    """Декоратор регистрации класса-узла под именем (или cls.name/имя класса)."""
    def deco(cls: type) -> type:
        key = name or getattr(cls, "name", None) or cls.__name__
        if key in _REGISTRY:
            raise ValueError(f"Узел '{key}' уже зарегистрирован")
        cls.name = key
        _REGISTRY[key] = cls
        return cls
    return deco


def get_node_class(name: str) -> type:
    if name not in _REGISTRY:
        raise KeyError(f"Узел '{name}' не зарегистрирован. Доступно: {available_nodes()}")
    return _REGISTRY[name]


def create_node(name: str, *args, **kwargs):
    """Создаёт экземпляр зарегистрированного узла."""
    return get_node_class(name)(*args, **kwargs)


def available_nodes() -> list[str]:
    return sorted(_REGISTRY)


def clear_registry() -> None:
    """Только для тестов: очищает реестр."""
    _REGISTRY.clear()
