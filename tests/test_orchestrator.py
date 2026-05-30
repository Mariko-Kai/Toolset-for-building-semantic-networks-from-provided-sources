"""Тесты оркестратора, мониторинга и обработки инцидентов (ТЗ Этап 4.1b)."""
from __future__ import annotations

from pipeline.nodes import NodeContext, NodeResult, NodeStatus
from pipeline.orchestration import Orchestrator, RunStatus
from pipeline.orchestration.incidents import Investigation, PatchPlan


class _Node:
    def __init__(self, name, result_fn):
        self.name = name
        self._fn = result_fn

    def run(self, ctx: NodeContext) -> NodeResult:
        return self._fn(ctx)


def test_happy_path_runs_all_nodes_and_records_state():
    a = _Node("a", lambda ctx: NodeResult(NodeStatus.OK, output={"a": 1}, metrics={"t": 0.1}))
    b = _Node("b", lambda ctx: NodeResult(NodeStatus.OK, output={"b": 2}))
    state = Orchestrator([a, b]).run(run_id="r1")

    assert state.status == RunStatus.COMPLETED.value
    assert [nr.node for nr in state.node_runs] == ["a", "b"]
    assert state.health()["nodes_total"] == 2
    assert state.health()["failures"] == 0
    # события: start/result для каждого + completed
    kinds = [e.kind for e in state.events]
    assert kinds.count("node_start") == 2
    assert "completed" in kinds


def test_context_flows_between_nodes():
    seen = {}

    def b_fn(ctx):
        seen.update(ctx.data)
        return NodeResult(NodeStatus.OK)

    a = _Node("a", lambda ctx: NodeResult(NodeStatus.OK, output={"key": "from_a"}))
    b = _Node("b", b_fn)
    Orchestrator([a, b]).run()
    assert seen.get("key") == "from_a"


def test_failure_pauses_and_creates_incident():
    a = _Node("a", lambda ctx: NodeResult(NodeStatus.OK))
    bad = _Node("bad", lambda ctx: NodeResult(NodeStatus.FAILED, message="boom", signals=["missing_dep:x"]))
    after = _Node("after", lambda ctx: NodeResult(NodeStatus.OK))

    orch = Orchestrator([a, bad, after])
    state = orch.run(run_id="r2")

    assert state.status == RunStatus.PAUSED.value
    # 'after' не выполнялся — поток остановлен на инциденте
    assert [nr.node for nr in state.node_runs] == ["a", "bad"]
    assert len(orch.incidents) == 1
    inc = orch.incidents[0]
    assert inc.node == "bad" and inc.severity == "error"
    assert "missing_dep:x" in inc.signals
    assert len(orch.patch_plans) == 1  # хендлер предложил план
    assert orch.patch_plans[0].auto_applicable is False  # без авто-применения


def test_node_exception_is_captured_not_crashed():
    def boom(ctx):
        raise RuntimeError("kaboom")

    bad = _Node("explode", boom)
    state = Orchestrator([bad]).run()
    assert state.status == RunStatus.PAUSED.value
    assert state.node_runs[0].status == NodeStatus.FAILED.value
    assert "kaboom" in state.node_runs[0].message


def test_deviation_pauses_by_default_but_can_continue():
    dev = _Node("dev", lambda ctx: NodeResult(NodeStatus.DEVIATION, message="0 entities"))
    nxt = _Node("nxt", lambda ctx: NodeResult(NodeStatus.OK))

    paused = Orchestrator([dev, nxt]).run()
    assert paused.status == RunStatus.PAUSED.value

    cont = Orchestrator([dev, nxt], continue_on_deviation=True).run()
    assert cont.status == RunStatus.COMPLETED.value


def test_confirm_gate_applies_patch_only_on_approval():
    applied = []

    class Handler:
        def investigate(self, incident):
            return Investigation(incident=incident, root_cause="rc")

        def propose_patch(self, investigation):
            return PatchPlan(summary="fix it", auto_applicable=False)

    bad = _Node("bad", lambda ctx: NodeResult(NodeStatus.FAILED))

    # подтверждение = да -> применяем
    orch_yes = Orchestrator(
        [bad], incident_handler=Handler(),
        confirm=lambda plan, inc: True,
        apply_patch=lambda plan, inc: applied.append(plan.summary),
    )
    orch_yes.run()
    assert applied == ["fix it"]

    # подтверждение = нет -> НЕ применяем
    applied.clear()
    orch_no = Orchestrator(
        [bad], incident_handler=Handler(),
        confirm=lambda plan, inc: False,
        apply_patch=lambda plan, inc: applied.append(plan.summary),
    )
    orch_no.run()
    assert applied == []
