"""Тесты pipeline.latex_utils после устранения дубликата (ТЗ 0.4a)."""
from __future__ import annotations

import inspect

from pipeline import latex_utils


def test_no_duplicate_definitions():
    """Каждая публичная функция определена ровно один раз (был дубль)."""
    src = inspect.getsource(latex_utils)
    for name in ("def get_macro_metadata", "def get_macro_to_id_mapping",
                 "def extract_dependencies", "def format_long_formulas"):
        assert src.count(name) == 1, f"{name} определена не один раз"


def test_extract_dependencies_explicit_hyperlink():
    deps = latex_utils.extract_dependencies(r"text \hyperlink{def-foo}{Foo} more")
    assert "def-foo" in deps


def test_format_long_formulas_short_passthrough():
    # Короткая формула остаётся в \[ ... \] без разбиения.
    out = latex_utils.format_long_formulas(r"\[ x = 1 \]")
    assert "flalign" not in out
    assert "x = 1" in out


def test_format_long_formulas_returns_string():
    # Полная версия функции имеет return (старая обрывалась и возвращала None).
    out = latex_utils.format_long_formulas(r"\[ a + b \]")
    assert isinstance(out, str)
