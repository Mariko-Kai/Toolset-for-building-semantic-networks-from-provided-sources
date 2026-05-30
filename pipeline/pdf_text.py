"""Однопроходное извлечение и кэширование текста PDF (ТЗ Этап 3.3).

Раньше текст всех страниц извлекался по 2–3 раза за прогон (полнотекстовый поиск,
построение кандидатов, preview-скан). Здесь текст страниц извлекается ОДИН раз и
кэшируется по (mtime, size) файла, после чего переиспользуется всеми фазами.

`fitz` (PyMuPDF) импортируется лениво; `_opener` инъектируется в тестах.
"""
from __future__ import annotations

import os
import re

# path -> (signature, [page_texts_lower])
_CACHE: dict[str, tuple] = {}


def _signature(pdf_path) -> tuple | None:
    try:
        st = os.stat(pdf_path)
        return (st.st_mtime, st.st_size)
    except OSError:
        return None


def get_page_texts(pdf_path, _opener=None) -> list[str]:
    """Возвращает список текстов всех страниц (lowercase, без переводов строк).

    Кэшируется по сигнатуре файла (mtime+size): повторные вызовы для того же
    неизменного файла не открывают и не парсят PDF заново.
    """
    key = str(pdf_path)
    sig = _signature(pdf_path)
    cached = _CACHE.get(key)
    if cached is not None and sig is not None and cached[0] == sig:
        return cached[1]

    opener = _opener
    if opener is None:
        import fitz  # лениво: тяжёлая зависимость из extra [ai]
        opener = fitz.open

    doc = opener(str(pdf_path))
    try:
        texts = [doc[i].get_text("text").lower().replace("\n", " ") for i in range(len(doc))]
    finally:
        try:
            doc.close()
        except Exception:
            pass

    if sig is not None:
        _CACHE[key] = (sig, texts)
    return texts


def clear_cache() -> None:
    _CACHE.clear()


def find_matching_roots(text: str, roots) -> list[str]:
    """Корни (lowercase), встречающиеся в тексте, в исходном порядке. Точная
    семантика подстроки (как `r in text`), но с однократным lower() корней."""
    return [r for r in (x.lower() for x in roots if x) if r in text]


def compile_root_regex(roots):
    """Один скомпилированный regex-алтернатор по корням (для мультипаттерн-скана).
    Возвращает None, если корней нет."""
    cleaned = [re.escape(r.lower()) for r in roots if r]
    if not cleaned:
        return None
    return re.compile("|".join(cleaned))
