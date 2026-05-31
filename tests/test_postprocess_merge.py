"""Тесты атомарности и dry-run слияния (ТЗ 1.4) для cleanup_database."""
from __future__ import annotations

import logging
import sqlite3
import sys
import types

import pytest

# postprocess_equivalence импортирует `ollama` на уровне модуля (extra [ai]),
# но cleanup_database его не использует — подставляем заглушку для импорта.
sys.modules.setdefault("ollama", types.ModuleType("ollama"))

from pipeline import postprocess_equivalence as pe  # noqa: E402


def test_get_embedding_raises_instead_of_zero_vector(monkeypatch):
    """C.2: при сбое эмбеддинга НЕ подставляем нулевой вектор (он дал бы сходство 0
    ко всему -> молча отключил бы дедуп прямо перед удалением файлов). Падаем громко."""
    merger = pe.MathesisSemanticMerger.__new__(pe.MathesisSemanticMerger)
    merger.embed_model = "nomic-embed-text:latest"
    merger.logger = logging.getLogger("test-merger-embed")

    class _Boom:
        @staticmethod
        def embeddings(*a, **k):
            raise ConnectionError("ollama unavailable")

    monkeypatch.setattr(pe, "ollama", _Boom)
    with pytest.raises(RuntimeError):
        merger.get_embedding("any text")

_SCHEMA = """
CREATE TABLE entities (entity_id TEXT PRIMARY KEY, type TEXT, title TEXT, path TEXT);
CREATE TABLE formulation_sources (id INTEGER PRIMARY KEY AUTOINCREMENT, entity_id TEXT, source_book TEXT, page_info TEXT);
CREATE TABLE entity_dependency (source_id TEXT, target_id TEXT, PRIMARY KEY (source_id, target_id));
"""


def _make_db(path):
    conn = sqlite3.connect(path)
    conn.executescript(_SCHEMA)
    conn.execute("INSERT INTO entities VALUES ('e1','def','E1','a.tex')")
    conn.execute("INSERT INTO entities VALUES ('e2','def','E2','b.tex')")
    conn.execute("INSERT INTO entities VALUES ('x','def','X','x.tex')")
    conn.execute("INSERT INTO entity_dependency VALUES ('e2','x')")
    conn.execute("INSERT INTO formulation_sources (entity_id, source_book) VALUES ('e2','book')")
    conn.commit()
    conn.close()


def _merger(dry_run=False):
    m = object.__new__(pe.MathesisSemanticMerger)
    m.logger = logging.getLogger("test-merge")
    m.dry_run = dry_run
    return m


@pytest.fixture
def live_db(tmp_path, monkeypatch):
    db_dir = tmp_path / "db"
    db_dir.mkdir()
    db_file = db_dir / "mathesis_index.db"
    _make_db(db_file)
    monkeypatch.setattr(pe, "PROJECT_ROOT", str(tmp_path))
    return db_file


def _rows(db_file, sql):
    conn = sqlite3.connect(db_file)
    try:
        return conn.execute(sql).fetchall()
    finally:
        conn.close()


def test_cleanup_merges_and_redirects(live_db):
    ok = _merger().cleanup_database("e1", "e2")
    assert ok is True
    assert _rows(live_db, "SELECT entity_id FROM entities WHERE entity_id='e2'") == []
    # Зависимость e2->x перенаправлена на e1->x.
    assert _rows(live_db, "SELECT source_id FROM entity_dependency") == [("e1",)]
    assert _rows(live_db, "SELECT entity_id FROM formulation_sources WHERE entity_id='e2'") == []


def test_dry_run_changes_nothing(live_db):
    ok = _merger(dry_run=True).cleanup_database("e1", "e2")
    assert ok is True
    assert _rows(live_db, "SELECT entity_id FROM entities WHERE entity_id='e2'") == [("e2",)]


def test_failure_rolls_back_atomically(live_db):
    # Ломаем транзакцию: убираем таблицу formulation_sources — DELETE по ней упадёт,
    # и весь блок (включая UPDATE entity_dependency) должен откатиться.
    conn = sqlite3.connect(live_db)
    conn.execute("DROP TABLE formulation_sources")
    conn.commit()
    conn.close()

    ok = _merger().cleanup_database("e1", "e2")
    assert ok is False
    # Ничего не изменилось: e2 на месте, зависимость не перенаправлена.
    assert _rows(live_db, "SELECT entity_id FROM entities WHERE entity_id='e2'") == [("e2",)]
    assert _rows(live_db, "SELECT source_id FROM entity_dependency") == [("e2",)]
