"""Тесты контракта узлов и реестра (ТЗ Этап 4.1)."""
from __future__ import annotations

import pytest

from pipeline.nodes import (
    NodeContext,
    NodeResult,
    NodeStatus,
    available_nodes,
    clear_registry,
    create_node,
    register_node,
)


@pytest.fixture(autouse=True)
def _clean_registry():
    clear_registry()
    yield
    clear_registry()


def test_node_result_flags():
    assert NodeResult(NodeStatus.OK).ok is True
    assert NodeResult(NodeStatus.OK).is_anomaly is False
    assert NodeResult(NodeStatus.DEVIATION).is_anomaly is True
    assert NodeResult(NodeStatus.FAILED).is_anomaly is True
    assert NodeResult(NodeStatus.SKIPPED).is_anomaly is False


def test_register_and_create():
    @register_node("demo")
    class Demo:
        def run(self, ctx: NodeContext) -> NodeResult:
            return NodeResult(NodeStatus.OK, output={"x": 1})

    assert "demo" in available_nodes()
    node = create_node("demo")
    assert node.name == "demo"
    assert node.run(NodeContext()).output == {"x": 1}


def test_duplicate_registration_rejected():
    @register_node("dup")
    class A:
        def run(self, ctx): return NodeResult(NodeStatus.OK)

    with pytest.raises(ValueError):
        @register_node("dup")
        class B:
            def run(self, ctx): return NodeResult(NodeStatus.OK)


def test_unknown_node_raises():
    with pytest.raises(KeyError):
        create_node("missing")
