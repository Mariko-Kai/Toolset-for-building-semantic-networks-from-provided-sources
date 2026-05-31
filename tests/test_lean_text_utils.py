"""Тесты общих Lean-парсеров (вынесены из postprocess_equivalence /
lean_equivalence_checker при дедупликации C.5)."""
from __future__ import annotations

from pipeline import lean_text_utils as ltu


def test_get_lean_name():
    assert ltu.get_lean_name("theorem foo_bar : True := by trivial") == "foo_bar"
    assert ltu.get_lean_name("def myDef : Nat := 0") == "myDef"
    assert ltu.get_lean_name("no declaration here") == "Name"


def test_determine_operator():
    assert ltu.determine_operator("thm-foo") == "↔"
    assert ltu.determine_operator("prop-bar") == "↔"
    assert ltu.determine_operator("lem-baz") == "↔"
    assert ltu.determine_operator("def-qux") == "="


def test_extract_lean_statement_theorem_strips_proof(tmp_path):
    f = tmp_path / "prop-foo.lean"
    f.write_text("import Mathlib\n\ntheorem prop_foo : 1 = 1 := by rfl\n", encoding="utf-8")
    stmt = ltu.extract_lean_statement(str(f))
    assert "theorem prop_foo : 1 = 1" in stmt
    assert "rfl" not in stmt          # доказательство отрезано
    assert "import" not in stmt       # импорты отрезаны


def test_extract_lean_statement_def_kept(tmp_path):
    f = tmp_path / "def-bar.lean"
    f.write_text("def def_bar : Nat := 42\n", encoding="utf-8")
    stmt = ltu.extract_lean_statement(str(f))
    assert "def def_bar" in stmt
