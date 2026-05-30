"""Тесты реестра возможностей и доменных пакетов (ТЗ Этап 5.4)."""
from __future__ import annotations

import pytest

from mathesis import capabilities as caps
from mathesis import domains


def test_default_capabilities_registered():
    names = {c.name for c in caps.all_capabilities()}
    assert {"extract_text", "ocr", "to_lean", "embed"} <= names


def test_capabilities_for_and_has():
    # raw_text дают и extract_text, и ocr
    providers = {c.name for c in caps.capabilities_for("raw_text")}
    assert {"extract_text", "ocr"} <= providers
    assert caps.has_capability("lean_code") is True
    assert caps.has_capability("does_not_exist") is False


def test_missing_representations_detects_gap():
    # latex/lean_code покрыты; "diagram" — нет → попадает в пробел
    missing = caps.missing_representations({"latex", "lean_code", "diagram"})
    assert missing == {"diagram"}


def test_register_custom_capability_closes_gap():
    try:
        assert "diagram" in caps.missing_representations({"diagram"})
        caps.register_capability(caps.Capability("draw", "diagram", "рисует диаграмму"))
        assert caps.missing_representations({"diagram"}) == set()
    finally:
        caps._CAPS.pop("draw", None)


def test_math_lean_domain_present_and_wired():
    assert "math_lean" in domains.available_domains()
    pack = domains.get_domain("math_lean")
    assert pack.entity_kinds == ("def", "prop")
    assert pack.target_language == "lean4"
    # detect_entity_type реально работает (из реестра 4.2)
    assert pack.detect_entity_type(["теорема о ..."]) == "prop"
    assert pack.detect_entity_type(["множество"]) == "def"


def test_register_second_domain():
    try:
        domains.register_domain(domains.DomainPack(name="logic_coq", target_language="coq"))
        assert "logic_coq" in domains.available_domains()
        assert domains.get_domain("logic_coq").target_language == "coq"
    finally:
        domains._DOMAINS.pop("logic_coq", None)


def test_get_unknown_raises():
    with pytest.raises(KeyError):
        domains.get_domain("nope")
    with pytest.raises(KeyError):
        caps.get_capability("nope")
