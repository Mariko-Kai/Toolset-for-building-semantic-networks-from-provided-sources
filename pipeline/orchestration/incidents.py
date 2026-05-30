"""Инциденты и их обработка (ТЗ Этап 4.1b) — агентная реакция на отклонения.

При аномальном статусе узла оркестратор формирует Incident и передаёт его
IncidentHandler: расследование → план патча. Применение патча — ТОЛЬКО после
подтверждения человека (gate в оркестраторе). LLM-агентная реализация хендлера
(код-ревью, root-cause) подключается на Этапе 5; здесь — интерфейс и безопасный
ручной хендлер по умолчанию.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol, runtime_checkable


@dataclass
class Incident:
    run_id: str
    node: str
    status: str
    severity: str = "warning"          # warning | error | critical
    signals: list = field(default_factory=list)
    context: dict = field(default_factory=dict)  # входы/выходы/события/ссылки на код
    message: str = ""


@dataclass
class Investigation:
    incident: Incident
    root_cause: str = ""
    findings: list = field(default_factory=list)
    reviewed_files: list = field(default_factory=list)


@dataclass
class PatchPlan:
    summary: str
    steps: list = field(default_factory=list)
    files: list = field(default_factory=list)
    tests: list = field(default_factory=list)
    risk: str = "unknown"
    auto_applicable: bool = False       # применять можно ТОЛЬКО после подтверждения человека


@runtime_checkable
class IncidentHandler(Protocol):
    def investigate(self, incident: Incident) -> Investigation: ...
    def propose_patch(self, investigation: Investigation) -> PatchPlan: ...


class ManualReviewHandler:
    """Безопасный хендлер по умолчанию: не делает авто-расследования и авто-патчей —
    лишь оформляет инцидент для разбора человеком. Самопочинку (LLM-код-ревью)
    добавит отдельная реализация на Этапе 5."""

    def investigate(self, incident: Incident) -> Investigation:
        return Investigation(
            incident=incident,
            root_cause="(требуется ручной разбор)",
            findings=[f"Узел '{incident.node}' завершился со статусом '{incident.status}'."],
        )

    def propose_patch(self, investigation: Investigation) -> PatchPlan:
        return PatchPlan(
            summary=f"Ручной разбор инцидента в узле '{investigation.incident.node}'",
            steps=["Изучить контекст инцидента", "Определить первопричину", "Подготовить исправление"],
            risk="unknown",
            auto_applicable=False,
        )
