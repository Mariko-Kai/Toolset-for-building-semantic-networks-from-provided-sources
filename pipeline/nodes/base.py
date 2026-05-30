"""Контракт узла агентной системы (ТЗ Этап 4.1).

Узел — единица работы с ТИПИЗИРОВАННЫМ результатом (вместо парсинга stdout).
Структурный `NodeResult.status` + метрики — основа мониторинга и реакции
оркестратора на отклонения. См. docs/architecture/agentic_orchestrator.md.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
from typing import Any, Protocol, runtime_checkable


class NodeStatus(str, Enum):
    OK = "ok"                   # отработал в пределах нормы
    DEVIATION = "deviation"     # отработал, но вне «нормального коридора»
    FAILED = "failed"           # сбой
    NEEDS_INPUT = "needs_input"  # требуется решение/подтверждение человека
    SKIPPED = "skipped"


# Статусы, которые оркестратор трактует как аномалию (триггер инцидента).
ANOMALY_STATUSES = frozenset({NodeStatus.DEVIATION, NodeStatus.FAILED})


@dataclass
class NodeContext:
    """Вход узла: произвольные данные потока + идентификатор прогона.

    Узлы читают нужные ключи из `data` и кладут результаты в `NodeResult.output`,
    который оркестратор вливает обратно в `data` для следующих узлов.
    """
    data: dict[str, Any] = field(default_factory=dict)
    run_id: str = ""


@dataclass
class NodeResult:
    status: NodeStatus
    output: dict[str, Any] = field(default_factory=dict)
    metrics: dict[str, float] = field(default_factory=dict)
    events: list[str] = field(default_factory=list)
    signals: list[str] = field(default_factory=list)   # напр. "missing_dep:def-foo"
    message: str = ""

    @property
    def ok(self) -> bool:
        return self.status == NodeStatus.OK

    @property
    def is_anomaly(self) -> bool:
        return self.status in ANOMALY_STATUSES


@runtime_checkable
class Node(Protocol):
    """Протокол узла. Реализация может быть классом или любым объектом с
    атрибутом `name` и методом `run(ctx) -> NodeResult`."""
    name: str

    def run(self, ctx: NodeContext) -> NodeResult: ...
