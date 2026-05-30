"""Тесты агентного LLM-обработчика инцидентов (ТЗ Этап 5.6)."""
from __future__ import annotations

from pipeline.nodes import NodeResult, NodeStatus
from pipeline.orchestration import Orchestrator, RunStatus
from pipeline.orchestration.incidents import Incident
from pipeline.orchestration.llm_handler import LLMIncidentHandler, _extract_json


def _fake_llm(prompt: str) -> str:
    """Фейковый LLM: разные ответы на запрос расследования и плана патча."""
    if "patch plan" in prompt or "PatchPlan" in prompt or "patch" in prompt.lower() and "Root cause:" in prompt:
        return '{"summary": "guard empty synth", "steps": ["add check"], "files": ["pipeline/x.py"], "tests": ["test_x"], "risk": "low"}'
    return '{"root_cause": "synth produced 0 entities", "findings": ["empty cluster"], "reviewed_files": ["pipeline/canonical_synthesizer.py"]}'


def _incident():
    return Incident(run_id="r", node="synth", status="deviation", severity="warning",
                    signals=["no_entities"], message="0 entities")


def test_investigate_parses_llm_json():
    inv = LLMIncidentHandler(query_fn=_fake_llm).investigate(_incident())
    assert "0 entities" in inv.root_cause
    assert inv.reviewed_files == ["pipeline/canonical_synthesizer.py"]


def test_propose_patch_parses_and_is_not_auto_applicable():
    handler = LLMIncidentHandler(query_fn=_fake_llm)
    inv = handler.investigate(_incident())
    plan = handler.propose_patch(inv)
    assert plan.summary == "guard empty synth"
    assert plan.risk == "low"
    assert plan.auto_applicable is False   # всегда требует подтверждения


def test_malformed_llm_output_is_safe():
    handler = LLMIncidentHandler(query_fn=lambda p: "not json at all")
    inv = handler.investigate(_incident())
    assert inv.root_cause  # дефолт, без падения
    plan = handler.propose_patch(inv)
    assert plan.auto_applicable is False


def test_extract_json_helper():
    assert _extract_json('prefix {"a": 1} suffix') == {"a": 1}
    assert _extract_json("no json") == {}
    assert _extract_json("") == {}


def test_end_to_end_agentic_loop_with_confirmation():
    applied = []
    bad = type("N", (), {"name": "synth",
                         "run": lambda self, ctx: NodeResult(NodeStatus.FAILED, message="boom")})()

    orch = Orchestrator(
        [bad],
        incident_handler=LLMIncidentHandler(query_fn=_fake_llm),
        confirm=lambda plan, inc: True,                       # человек подтвердил
        apply_patch=lambda plan, inc: applied.append(plan.summary),
    )
    state = orch.run(run_id="loop-1")

    assert state.status == RunStatus.PAUSED.value
    assert orch.incidents and orch.incidents[0].node == "synth"
    assert orch.patch_plans and orch.patch_plans[0].summary  # LLM предложил план
    assert applied == [orch.patch_plans[0].summary]            # применён после подтверждения


def test_end_to_end_without_confirmation_does_not_apply():
    applied = []
    bad = type("N", (), {"name": "synth",
                         "run": lambda self, ctx: NodeResult(NodeStatus.FAILED)})()
    orch = Orchestrator(
        [bad],
        incident_handler=LLMIncidentHandler(query_fn=_fake_llm),
        confirm=lambda plan, inc: False,                      # человек отклонил
        apply_patch=lambda plan, inc: applied.append(plan.summary),
    )
    orch.run()
    assert applied == []
