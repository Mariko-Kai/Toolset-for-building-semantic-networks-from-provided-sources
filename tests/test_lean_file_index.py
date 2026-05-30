"""Тест кэша id->path в lean_equivalence_checker (ТЗ Этап 3.5)."""
from __future__ import annotations

import sys
import types

# export_to_lean (через цепочку импортов) может тянуть ollama — заглушка.
sys.modules.setdefault("ollama", types.ModuleType("ollama"))

from pipeline import lean_equivalence_checker as lec  # noqa: E402


def _verifier(content_dir):
    v = object.__new__(lec.ProverEquivalenceVerifier)  # минуем тяжёлый __init__
    v.content_dir = str(content_dir)
    v._content_lean_index = None
    return v


def test_find_by_id_uses_index_and_globs_once(tmp_path, monkeypatch):
    (tmp_path / "defs").mkdir()
    (tmp_path / "defs" / "Foo [def-foo].lean").write_text("def foo := 1", encoding="utf-8")
    (tmp_path / "defs" / "Bar [def-bar].lean").write_text("def bar := 2", encoding="utf-8")

    calls = {"n": 0}
    real_glob = lec.glob.glob

    def counting_glob(*a, **k):
        calls["n"] += 1
        return real_glob(*a, **k)

    monkeypatch.setattr(lec.glob, "glob", counting_glob)

    v = _verifier(tmp_path)
    p1 = v.find_lean_file_by_id("def-foo")
    p2 = v.find_lean_file_by_id("def-bar")
    p3 = v.find_lean_file_by_id("def-missing")

    assert p1 and p1.endswith("Foo [def-foo].lean")
    assert p2 and p2.endswith("Bar [def-bar].lean")
    assert p3 is None
    # Несмотря на 3 запроса — рекурсивный glob выполнен ровно один раз (кэш).
    assert calls["n"] == 1
