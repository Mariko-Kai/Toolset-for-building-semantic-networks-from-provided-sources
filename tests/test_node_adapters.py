"""Тесты адаптеров подпроцессов в узлы (ТЗ Этап 5.2)."""
from __future__ import annotations

from pipeline.nodes import NodeContext, NodeStatus
from pipeline.nodes.adapters import SubprocessNode, build_enrichment_flow, parse_synth_line
from pipeline.orchestration import Orchestrator, RunStatus, load_run, save_run_state


def _runner_factory(rc: int, lines: list[str]):
    def runner(cmd, env, on_line, timeout):
        for ln in lines:
            on_line(ln)
        return rc
    return runner


def test_parse_synth_line():
    out = {}
    parse_synth_line("[synthesizer] Parsed: entity_id=def-foo, type=def", out)
    parse_synth_line('[synthesizer] ParsedDeps: {"entity_id": "def-foo", "deps": ["def-bar"]}', out)
    assert out["entities"] == ["def-foo"]
    assert out["deps"] == {"def-foo": ["def-bar"]}


def test_subprocess_node_ok():
    node = SubprocessNode("x", ["cmd"], runner=_runner_factory(0, ["hello"]))
    res = node.run(NodeContext())
    assert res.status == NodeStatus.OK
    assert res.metrics["returncode"] == 0.0
    assert "duration_s" in res.metrics


def test_subprocess_node_failed_on_returncode():
    node = SubprocessNode("x", ["cmd"], runner=_runner_factory(2, []))
    res = node.run(NodeContext())
    assert res.status == NodeStatus.FAILED
    assert "2" in res.message


def test_subprocess_node_exception_is_failed():
    def boom(cmd, env, on_line, timeout):
        raise RuntimeError("spawn failed")
    res = SubprocessNode("x", ["cmd"], runner=boom).run(NodeContext())
    assert res.status == NodeStatus.FAILED
    assert "spawn failed" in res.message


def test_synth_node_deviation_when_no_entities():
    # rc=0, но синтез не выдал entity → DEVIATION
    flow = build_enrichment_flow(["e"], ["a"], ["s"], runner=_runner_factory(0, ["noise"]))
    synth = flow[-1]
    res = synth.run(NodeContext())
    assert res.status == NodeStatus.DEVIATION
    assert "не произвёл" in res.message


def test_build_enrichment_flow_names():
    flow = build_enrichment_flow(["e"], ["a"], ["s"])
    assert [n.name for n in flow] == ["extract", "align", "synth"]


def test_orchestrated_flow_completes_and_persists(canon_conn):
    # Фейковый runner: синтез эмитит структурный handoff -> entities захвачены.
    def runner(cmd, env, on_line, timeout):
        if cmd and cmd[0] == "synth":
            on_line("[synthesizer] Parsed: entity_id=def-limit, type=def")
            on_line('[synthesizer] ParsedDeps: {"entity_id": "def-limit", "deps": []}')
        return 0

    flow = build_enrichment_flow(["extract"], ["align"], ["synth"], runner=runner)
    state = Orchestrator(flow).run(run_id="enr-1")

    assert state.status == RunStatus.COMPLETED.value
    # выход synth-узла доступен (структурно), без парсинга stdout в оркестраторе
    assert state.node_runs[-1].node == "synth"
    # персистенция мониторинга
    save_run_state(canon_conn, state)
    loaded = load_run(canon_conn, "enr-1")
    assert loaded["status"] == "completed"
    assert loaded["health"]["nodes_total"] == 3


def test_orchestrated_flow_pauses_on_synth_deviation():
    # Синтез отработал (rc=0), но не дал сущностей → DEVIATION → пауза.
    runner = _runner_factory(0, ["nothing useful"])
    flow = build_enrichment_flow(["extract"], ["align"], ["synth"], runner=runner)
    orch = Orchestrator(flow)
    state = orch.run(run_id="enr-2")
    assert state.status == RunStatus.PAUSED.value
    assert len(orch.incidents) == 1
    assert orch.incidents[0].node == "synth"
