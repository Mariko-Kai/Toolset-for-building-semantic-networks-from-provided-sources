"""Тесты OCR-возможности (ТЗ Этап 5.3): vision-путь и OCR-узел."""
from __future__ import annotations

import json

from pipeline.nodes.base import NodeContext, NodeStatus
from pipeline.nodes.ocr import OcrNode, is_scanned_page


def test_is_scanned_page():
    assert is_scanned_page("") is True
    assert is_scanned_page("   \n  ") is True
    assert is_scanned_page("short", min_chars=20) is True
    assert is_scanned_page("a" * 50, min_chars=20) is False


def test_ocr_node_with_injected_render_and_query():
    seen = {}

    def fake_render(pdf, page, dpi):
        seen["render"] = (pdf, page, dpi)
        return b"PNGDATA"

    def fake_query(prompt, images):
        seen["images"] = images
        return "извлечённый текст с формулой $x^2$"

    node = OcrNode(render=fake_render, query_fn=fake_query, dpi=200)
    res = node.run(NodeContext(data={"pdf_path": "book.pdf", "page_index": 5}))
    assert res.status == NodeStatus.OK
    assert "формул" in res.output["text"]
    assert res.metrics["ocr_chars"] > 0
    assert seen["render"] == ("book.pdf", 5, 200)
    assert seen["images"] == [b"PNGDATA"]


def test_ocr_node_uses_provided_images_without_render():
    node = OcrNode(render=lambda *a: (_ for _ in ()).throw(AssertionError("render не должен вызываться")),
                   query_fn=lambda p, imgs: "text")
    res = node.run(NodeContext(data={"images": [b"IMG"]}))
    assert res.status == NodeStatus.OK


def test_ocr_node_empty_result_is_deviation():
    node = OcrNode(query_fn=lambda p, imgs: "")
    res = node.run(NodeContext(data={"images": [b"IMG"]}))
    assert res.status == NodeStatus.DEVIATION


def test_ocr_node_no_input_is_failed():
    node = OcrNode(query_fn=lambda p, imgs: "x")
    res = node.run(NodeContext(data={}))
    assert res.status == NodeStatus.FAILED


def test_query_vision_passes_through_to_ollama(monkeypatch):
    from pipeline import model_manager
    from pipeline.model_manager import ModelManager, OllamaStrategy

    monkeypatch.setattr(model_manager, "MODEL_RETRY_BASE_DELAY", 0.0)
    ModelManager._instance = None
    mgr = ModelManager()
    try:
        strat = OllamaStrategy()
        captured = {}

        def fake_gen(prompt, images, system_prompt=None, json_mode=False):
            captured["prompt"] = prompt
            captured["images"] = images
            return "ocr result"

        strat.generate_with_images = fake_gen
        mgr.strategies["cv"] = strat
        out = mgr.query_vision("read this", [b"IMG"], role="cv")
        assert out == "ocr result"
        assert captured["images"] == [b"IMG"]
    finally:
        ModelManager._instance = None


def test_query_vision_non_ollama_returns_empty(monkeypatch):
    from pipeline.model_manager import ModelManager

    ModelManager._instance = None
    mgr = ModelManager()
    try:
        class NotOllama:
            def generate_content(self, *a, **k): return ""
            def get_embedding(self, t): return None
        mgr.strategies["cv"] = NotOllama()
        assert mgr.query_vision("p", [b"x"], role="cv") == ""
    finally:
        ModelManager._instance = None


def test_ollama_generate_with_images_builds_base64_payload(monkeypatch):
    import base64
    import contextlib
    from pipeline import model_manager
    from pipeline.model_manager import OllamaStrategy

    captured = {}

    class _Resp:
        def read(self):
            return json.dumps({"response": "ok-text"}).encode("utf-8")

    @contextlib.contextmanager
    def fake_urlopen(req, timeout=None):
        captured["data"] = json.loads(req.data.decode("utf-8"))
        yield _Resp()

    monkeypatch.setattr(model_manager.urllib.request, "urlopen", fake_urlopen)
    strat = OllamaStrategy(model_name="llava:latest")
    out = strat.generate_with_images("describe", [b"RAWPNG"])
    assert out == "ok-text"
    assert captured["data"]["model"] == "llava:latest"
    assert captured["data"]["images"] == [base64.b64encode(b"RAWPNG").decode("ascii")]
