"""Тесты воскрешённых хелперов графа export_to_lean (ТЗ: разбор легаси F821)."""
from __future__ import annotations

import sys
import types

sys.modules.setdefault("ollama", types.ModuleType("ollama"))

from pipeline import export_to_lean as exl  # noqa: E402


def test_topological_sort_dependencies_first():
    nodes = {"a": {}, "b": {}, "c": {}}
    # a зависит от b; b зависит от c  => порядок c, b, a
    edges = [("a", "b"), ("b", "c")]
    order = exl.topological_sort(nodes, edges)
    assert order.index("c") < order.index("b") < order.index("a")


def test_topological_sort_handles_cycle_without_crash():
    nodes = {"a": {}, "b": {}}
    edges = [("a", "b"), ("b", "a")]
    order = exl.topological_sort(nodes, edges)
    assert set(order) == {"a", "b"}  # остаток добавлен, без падения


def test_get_graph_from_files(tmp_path, monkeypatch):
    content = tmp_path / "content"
    (content / "defs").mkdir(parents=True)
    (content / "props").mkdir(parents=True)
    (content / "defs" / "Base [def-base].tex").write_text(
        "% entity-id: def-base\n% entity-type: def\nbody\n", encoding="utf-8")
    (content / "props" / "Thm [prop-thm].tex").write_text(
        "% entity-id: prop-thm\n% entity-type: prop\nuses macro{def-base}\n", encoding="utf-8")
    monkeypatch.setattr(exl, "CONTENT_DIR", content)

    nodes, edges = exl.get_graph_from_files()
    assert set(nodes) == {"def-base", "prop-thm"}
    assert nodes["def-base"]["type"] == "def"
    assert nodes["prop-thm"]["type"] == "prop"
    assert ("prop-thm", "def-base") in edges
    # топосорт: зависимость def-base раньше prop-thm
    order = exl.topological_sort(nodes, edges)
    assert order.index("def-base") < order.index("prop-thm")
