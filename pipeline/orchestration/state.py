"""Состояние прогона и журнал событий (ТЗ Этап 4.1b) — плотный мониторинг.

RunState — единый источник истины о прогоне: история узлов, статусы, переходы,
append-only журнал событий, агрегированное «здоровье». Сериализуется в dict для
персистенции в БД и для live-инспекции монитор-UI.
"""
from __future__ import annotations

from collections import Counter
from dataclasses import asdict, dataclass, field
from enum import Enum

from pipeline.nodes.base import NodeResult, NodeStatus


class RunStatus(str, Enum):
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    PAUSED = "paused"       # ожидает решения человека (инцидент/needs_input)


@dataclass
class Event:
    seq: int
    node: str
    kind: str               # node_start | node_result | incident | paused | completed
    status: str
    message: str = ""


@dataclass
class NodeRun:
    node: str
    status: str
    metrics: dict = field(default_factory=dict)
    signals: list = field(default_factory=list)
    message: str = ""


@dataclass
class RunState:
    run_id: str
    status: str = RunStatus.RUNNING.value
    node_runs: list = field(default_factory=list)
    events: list = field(default_factory=list)
    current_node: str = ""
    _seq: int = 0

    def add_event(self, node: str, kind: str, status: str = "", message: str = "") -> Event:
        self._seq += 1
        ev = Event(seq=self._seq, node=node, kind=kind, status=str(status), message=message)
        self.events.append(ev)
        return ev

    def record_start(self, node: str) -> None:
        self.current_node = node
        self.add_event(node, "node_start")

    def record_result(self, node: str, result: NodeResult) -> None:
        self.node_runs.append(NodeRun(
            node=node, status=result.status.value, metrics=dict(result.metrics),
            signals=list(result.signals), message=result.message,
        ))
        self.add_event(node, "node_result", result.status.value, result.message)

    def health(self) -> dict:
        """Сводка статусов по узлам прогона (для монитора/политик)."""
        counts = Counter(nr.status for nr in self.node_runs)
        return {
            "run_status": self.status,
            "nodes_total": len(self.node_runs),
            "by_status": dict(counts),
            "deviations": counts.get(NodeStatus.DEVIATION.value, 0),
            "failures": counts.get(NodeStatus.FAILED.value, 0),
        }

    def to_dict(self) -> dict:
        return {
            "run_id": self.run_id,
            "status": self.status,
            "current_node": self.current_node,
            "node_runs": [asdict(nr) for nr in self.node_runs],
            "events": [asdict(e) for e in self.events],
            "health": self.health(),
        }
