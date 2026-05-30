"""OCR как узел-возможность (ТЗ Этап 5.3).

Второй конкретный пример «возможности» (после извлечения текстового слоя):
сканированная/картиночная страница → рендер в изображение → vision-модель → текст.
Рендер и vision-вызов инъектируются (для тестов без fitz/модели). См.
docs/howto/ocr_integration.md.
"""
from __future__ import annotations

from typing import Callable, Optional

from pipeline.nodes.base import NodeContext, NodeResult, NodeStatus
from pipeline.nodes.registry import register_node

DEFAULT_OCR_PROMPT = (
    "Extract ALL text and mathematics from this page as clean, LaTeX-friendly plain text. "
    "Preserve formulas. Output only the extracted content."
)


def is_scanned_page(text: str, min_chars: int = 20) -> bool:
    """Эвристика: страница «сканированная», если текстового слоя почти нет."""
    return len((text or "").strip()) < min_chars


def render_page_png(pdf_path, page_index: int, dpi: int = 150) -> bytes:
    """Рендер страницы PDF в PNG (через PyMuPDF). fitz импортируется лениво."""
    import fitz
    doc = fitz.open(str(pdf_path))
    try:
        page = doc[page_index]
        zoom = dpi / 72.0
        pix = page.get_pixmap(matrix=fitz.Matrix(zoom, zoom))
        return pix.tobytes("png")
    finally:
        doc.close()


@register_node("ocr")
class OcrNode:
    """Узел OCR. Вход (ctx.data): либо `images` (list[bytes]), либо `pdf_path`+`page_index`.
    Выход: {"text": ..., "ocr_chars": N}."""
    name = "ocr"

    def __init__(self, *, prompt: Optional[str] = None,
                 render: Optional[Callable] = None,
                 query_fn: Optional[Callable[[str, list], str]] = None,
                 dpi: int = 150):
        self.prompt = prompt or DEFAULT_OCR_PROMPT
        self._render = render or render_page_png
        self._query = query_fn
        self.dpi = dpi

    def _vision(self, prompt: str, images: list) -> str:
        if self._query is not None:
            return self._query(prompt, images)
        from pipeline.model_manager import ModelManager
        return ModelManager.get_instance().query_vision(prompt, images, role="cv")

    def run(self, ctx: NodeContext) -> NodeResult:
        data = ctx.data
        images = data.get("images")
        if not images:
            pdf_path = data.get("pdf_path")
            if not pdf_path:
                return NodeResult(NodeStatus.FAILED, message="OCR: нет ни 'images', ни 'pdf_path'")
            page_index = int(data.get("page_index", 0))
            try:
                images = [self._render(pdf_path, page_index, self.dpi)]
            except Exception as e:  # noqa: BLE001
                return NodeResult(NodeStatus.FAILED, message=f"OCR render error: {e}")

        text = self._vision(self.prompt, images)
        if not text or not text.strip():
            return NodeResult(NodeStatus.DEVIATION, message="OCR вернул пустой результат")
        return NodeResult(
            NodeStatus.OK,
            output={"text": text, "ocr_chars": len(text)},
            metrics={"ocr_chars": float(len(text))},
        )
