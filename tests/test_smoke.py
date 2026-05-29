"""Smoke-тесты: пакеты импортируются, фикстуры работают."""
from __future__ import annotations

import sqlite3


def test_import_light_modules():
    # Лёгкие модули без тяжёлых AI/ML-зависимостей должны импортироваться.
    import pipeline.config  # noqa: F401
    import pipeline.latex_utils  # noqa: F401
    import mathesis  # noqa: F401


def test_tmp_db_has_schema(tmp_db):
    conn = sqlite3.connect(tmp_db)
    try:
        names = {r[0] for r in conn.execute(
            "SELECT name FROM sqlite_master WHERE type='table'"
        )}
    finally:
        conn.close()
    assert {"entities", "formulation_sources", "entity_dependency"} <= names


def test_fake_mgr_is_deterministic(fake_mgr):
    a = fake_mgr.get_embedding("предел функции")
    b = fake_mgr.get_embedding("предел функции")
    assert a == b
    assert len(a) == 8

    fake_mgr.responses = {"hello": "world"}
    assert fake_mgr.query_llm("say hello please") == "world"
    assert fake_mgr.query_llm("unmatched") == ""
