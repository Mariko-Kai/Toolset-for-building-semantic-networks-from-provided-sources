"""Тесты выбора реранкера get_reranker (URL / llama_cpp GGUF / проба / фолбэк)."""
from __future__ import annotations

import sys
import types

import pytest

from pipeline import ollama_wrapper as ow


@pytest.fixture
def fake_hybrid(monkeypatch):
    """Подменяет pipeline.hybrid_search фейком, фиксирующим выбранный backend."""
    mod = types.ModuleType("pipeline.hybrid_search")
    calls = {}

    class FakeReranker:
        def __init__(self, backend="local", model_name=None, api_url=None):
            calls["reranker"] = {"backend": backend, "model_name": model_name, "api_url": api_url}

    class FakePipeline:
        def __init__(self, **kw):
            calls["pipeline"] = kw
            self.reranker = FakeReranker(backend="rest", api_url=kw.get("api_url"))

        def close(self):
            pass

    mod.CrossEncoderReranker = FakeReranker
    mod.HybridSearchPipeline = FakePipeline
    monkeypatch.setitem(sys.modules, "pipeline.hybrid_search", mod)
    # сбрасываем кэш реранкера
    monkeypatch.setattr(ow, "_RERANKER_CACHE", None)
    monkeypatch.setattr(ow, "_RERANKER_PIPELINE", None)
    return calls


def _patch_preview(monkeypatch, provider, model):
    import pipeline.config as cfg
    monkeypatch.setattr(cfg, "resolve_module_config",
                        lambda module, **k: (provider, model, None))


def test_explicit_rest_url(fake_hybrid, monkeypatch):
    _patch_preview(monkeypatch, "llama_cpp", "x.gguf")
    monkeypatch.setenv("MATHESIS_RERANK_URL", "http://host:9000")
    ow.get_reranker()
    assert fake_hybrid["reranker"]["backend"] == "rest"
    assert fake_hybrid["reranker"]["api_url"] == "http://host:9000"


def test_llama_cpp_gguf_in_process(fake_hybrid, monkeypatch, tmp_path):
    """GGUF на llama_cpp -> in-process CrossEncoderReranker(backend='llama_cpp').
    Встроенный llama_cpp.server не имеет /rerank, поэтому REST-сервер не поднимаем."""
    gguf = tmp_path / "bge-reranker-v2-m3-Q6_K.gguf"
    gguf.write_bytes(b"GGUF")
    _patch_preview(monkeypatch, "llama_cpp", str(gguf))
    monkeypatch.delenv("MATHESIS_RERANK_URL", raising=False)
    ow.get_reranker()
    assert "pipeline" not in fake_hybrid
    assert fake_hybrid["reranker"]["backend"] == "llama_cpp"
    assert fake_hybrid["reranker"]["model_name"] == str(gguf)


def test_fallback_to_local_hf(fake_hybrid, monkeypatch):
    _patch_preview(monkeypatch, "ollama", "qwen")
    monkeypatch.delenv("MATHESIS_RERANK_URL", raising=False)
    # проба портов всегда падает
    import urllib.request
    monkeypatch.setattr(urllib.request, "urlopen",
                        lambda *a, **k: (_ for _ in ()).throw(OSError("refused")))
    ow.get_reranker()
    assert fake_hybrid["reranker"]["backend"] == "local"
    assert "BAAI" in fake_hybrid["reranker"]["model_name"]


def test_resolve_gguf_path(tmp_path, monkeypatch):
    gguf = tmp_path / "r.gguf"
    gguf.write_bytes(b"x")
    assert ow._resolve_gguf_path(str(gguf)) == gguf
    assert ow._resolve_gguf_path("not_a_model") is None
    assert ow._resolve_gguf_path("missing.gguf") is None
    # поиск по MATHESIS_LLAMA_DIR
    monkeypatch.setenv("MATHESIS_LLAMA_DIR", str(tmp_path))
    assert ow._resolve_gguf_path("r.gguf") == tmp_path / "r.gguf"
