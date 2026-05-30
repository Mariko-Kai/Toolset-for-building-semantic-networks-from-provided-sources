"""Оркестратор верхнего уровня (ТЗ Этап 4.1b).

Гоняет последовательность узлов, после каждого обновляет RunState (мониторинг),
вливает выход узла в контекст следующего. При аномалии (DEVIATION/FAILED) — ставит
прогон на паузу, формирует Incident и передаёт его обработчику; патч применяется
ТОЛЬКО через явный gate подтверждения человека. См.
docs/architecture/agentic_orchestrator.md.
"""
from __future__ import annotations

from typing import Callable, Optional

from pipeline.nodes.base import Node, NodeContext, NodeResult, NodeStatus
from pipeline.orchestration.incidents import Incident, IncidentHandler, ManualReviewHandler, PatchPlan
from pipeline.orchestration.state import RunState, RunStatus


class Orchestrator:
    def __init__(
        self,
        nodes: list[Node],
        *,
        incident_handler: Optional[IncidentHandler] = None,
        confirm: Optional[Callable[[PatchPlan, Incident], bool]] = None,
        apply_patch: Optional[Callable[[PatchPlan, Incident], None]] = None,
        continue_on_deviation: bool = False,
    ):
        """
        nodes               — последовательность узлов потока.
        incident_handler    — расследование + план патча (по умолчанию ручной).
        confirm             — gate человека: (plan, incident) -> bool. Без него
                              патч НИКОГДА не применяется автоматически.
        apply_patch         — применение патча после подтверждения (через git+тесты).
        continue_on_deviation — продолжать ли поток при DEVIATION (по умолчанию пауза).
        """
        self.nodes = list(nodes)
        self.incident_handler = incident_handler or ManualReviewHandler()
        self.confirm = confirm
        self.apply_patch = apply_patch
        self.continue_on_deviation = continue_on_deviation
        self.incidents: list[Incident] = []
        self.patch_plans: list[PatchPlan] = []

    def run(self, ctx: Optional[NodeContext] = None, run_id: str = "run") -> RunState:
        ctx = ctx or NodeContext(run_id=run_id)
        if not ctx.run_id:
            ctx.run_id = run_id
        state = RunState(run_id=ctx.run_id)

        for node in self.nodes:
            state.record_start(node.name)
            try:
                result = node.run(ctx)
            except Exception as e:  # noqa: BLE001 — сбой узла не должен ронять оркестратор
                result = NodeResult(status=NodeStatus.FAILED, message=f"{type(e).__name__}: {e}")

            state.record_result(node.name, result)
            # Выход узла доступен следующим узлам.
            if result.output:
                ctx.data.update(result.output)

            if result.status == NodeStatus.FAILED or (
                result.status == NodeStatus.DEVIATION and not self.continue_on_deviation
            ):
                self._raise_incident(state, node, result)
                state.status = RunStatus.PAUSED.value
                return state

            if result.status == NodeStatus.NEEDS_INPUT:
                state.add_event(node.name, "paused", result.status.value, "ожидает ввода человека")
                state.status = RunStatus.PAUSED.value
                return state

        state.status = RunStatus.COMPLETED.value
        state.add_event(state.current_node, "completed", RunStatus.COMPLETED.value)
        return state

    def _raise_incident(self, state: RunState, node: Node, result: NodeResult) -> None:
        severity = "error" if result.status == NodeStatus.FAILED else "warning"
        incident = Incident(
            run_id=state.run_id, node=node.name, status=result.status.value,
            severity=severity, signals=list(result.signals),
            context={"metrics": dict(result.metrics), "events": list(result.events)},
            message=result.message,
        )
        self.incidents.append(incident)
        state.add_event(node.name, "incident", result.status.value, result.message)

        # Расследование -> план патча (без авто-применения).
        investigation = self.incident_handler.investigate(incident)
        plan = self.incident_handler.propose_patch(investigation)
        self.patch_plans.append(plan)

        # Gate человека: применяем ТОЛЬКО при явном подтверждении.
        if self.confirm is not None and self.apply_patch is not None:
            if self.confirm(plan, incident):
                self.apply_patch(plan, incident)
                state.add_event(node.name, "patch_applied", "", plan.summary)
            else:
                state.add_event(node.name, "patch_rejected", "", plan.summary)
