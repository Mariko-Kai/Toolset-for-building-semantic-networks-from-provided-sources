"""Тесты продюсеров возможностей и пилотного домена (ТЗ: остальные пункты)."""
from __future__ import annotations

import pytest

from mathesis import capabilities as caps
from mathesis import domains
from mathesis.domains_extra import build_logic_coq_pack, register as register_logic


def test_produce_calls_producer():
    try:
        caps.register_capability(caps.Capability("upper", "text", producer=lambda s: s.upper()))
        assert caps.produce("upper", "hi") == "HI"
    finally:
        caps._CAPS.pop("upper", None)


def test_produce_without_producer_raises():
    # synth_latex зарегистрирован без продюсера
    with pytest.raises(ValueError):
        caps.produce("synth_latex", "x")


def test_default_capabilities_have_real_producers():
    assert callable(caps.get_capability("embed").producer)
    assert callable(caps.get_capability("ocr").producer)


def test_embed_producer_delegates_to_model_manager(monkeypatch):
    captured = {}

    class FakeMgr:
        def get_embedding(self, text, role=None):
            captured["text"] = text
            captured["role"] = role
            return [0.1, 0.2]

    import pipeline.model_manager as mm
    monkeypatch.setattr(mm.ModelManager, "get_instance", staticmethod(lambda: FakeMgr()))
    assert caps.produce("embed", "предел") == [0.1, 0.2]
    assert captured == {"text": "предел", "role": "embed"}


def test_pilot_domain_is_portable():
    pack = build_logic_coq_pack()
    assert pack.target_language == "coq"
    assert pack.normalize_term("Modus Ponens!") == "modus ponens"
    try:
        register_logic()
        assert "logic_coq" in domains.available_domains()
        assert domains.get_domain("logic_coq").target_language == "coq"
        # ядро домен-агностично: math_lean и logic_coq сосуществуют
        assert "math_lean" in domains.available_domains()
    finally:
        domains._DOMAINS.pop("logic_coq", None)
