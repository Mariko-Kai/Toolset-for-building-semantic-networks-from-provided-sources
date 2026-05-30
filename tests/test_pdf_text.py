"""Тесты кэша текста PDF (ТЗ Этап 3.3) — без fitz, через инъекцию opener."""
from __future__ import annotations

from pipeline import pdf_text


class _FakePage:
    def __init__(self, text):
        self._text = text

    def get_text(self, _mode):
        return self._text


class _FakeDoc:
    def __init__(self, pages):
        self._pages = [_FakePage(p) for p in pages]

    def __len__(self):
        return len(self._pages)

    def __getitem__(self, i):
        return self._pages[i]

    def close(self):
        pass


def test_get_page_texts_lowercases_and_strips_newlines(tmp_path):
    f = tmp_path / "a.pdf"
    f.write_bytes(b"x")
    pdf_text.clear_cache()
    opener_calls = {"n": 0}

    def opener(_path):
        opener_calls["n"] += 1
        return _FakeDoc(["Hello\nWORLD", "Predel Funkcii"])

    texts = pdf_text.get_page_texts(f, _opener=opener)
    assert texts == ["hello world", "predel funkcii"]
    # Повторный вызов — из кэша (opener не вызывается снова).
    pdf_text.get_page_texts(f, _opener=opener)
    assert opener_calls["n"] == 1


def test_cache_invalidates_on_file_change(tmp_path):
    f = tmp_path / "b.pdf"
    f.write_bytes(b"x")
    pdf_text.clear_cache()
    calls = {"n": 0}

    def opener(_path):
        calls["n"] += 1
        return _FakeDoc(["v" + str(calls["n"])])

    pdf_text.get_page_texts(f, _opener=opener)
    import os
    import time
    # Меняем содержимое и mtime — кэш должен инвалидироваться.
    f.write_bytes(b"xxxx")
    os.utime(f, (time.time() + 10, time.time() + 10))
    pdf_text.get_page_texts(f, _opener=opener)
    assert calls["n"] == 2


def test_find_matching_roots_preserves_order_and_lowercases():
    text = "the limit of a continuous function"
    assert pdf_text.find_matching_roots(text, ["Limit", "Continuous", "Derivative"]) == ["limit", "continuous"]


def test_compile_root_regex():
    assert pdf_text.compile_root_regex([]) is None
    rx = pdf_text.compile_root_regex(["Limit", "Sup"])
    assert set(rx.findall("limit and sup here")) == {"limit", "sup"}
