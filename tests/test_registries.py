"""Тесты data-driven реестров (ТЗ Этап 4.2)."""
from __future__ import annotations

import pytest

from pipeline.registries import entity_types
from pipeline.registries.entity_types import detect_entity_type
from pipeline.registries.lean_hints import HintRule, hints_for_error


@pytest.fixture(autouse=True)
def _clean_detectors():
    entity_types.clear_detectors()
    yield
    entity_types.clear_detectors()


def test_detect_has_proof_is_prop():
    assert detect_entity_type(["любой текст"], has_proof=True) == "prop"


def test_detect_keyword_prop():
    assert detect_entity_type(["Теорема Кантора о ..."]) == "prop"
    assert detect_entity_type(["This lemma states..."]) == "prop"


def test_detect_default_def():
    assert detect_entity_type(["множество вещественных чисел"]) == "def"


def test_custom_detector_takes_priority():
    @entity_types.register_detector
    def _force_prop(texts, has_proof):
        return "prop" if any("ZZZ" in t for t in texts) else None

    assert detect_entity_type(["ZZZ marker"]) == "prop"
    assert detect_entity_type(["обычное определение"]) == "def"


def test_lean_hints_substring():
    hints = hints_for_error("error: unexpected token 'in' at ...")
    assert any("∈" in h for h in hints)


def test_lean_hints_regex_interpolates_identifier():
    hints = hints_for_error("Line 3: unknown identifier 'IsLimit'")
    assert any("IsLimit" in h for h in hints)


def test_lean_hints_empty_and_custom():
    assert hints_for_error("") == []
    rules = [HintRule("oops", "do X")]
    assert hints_for_error("oops happened", rules=rules) == ["do X"]
    assert hints_for_error("nothing", rules=rules) == []
