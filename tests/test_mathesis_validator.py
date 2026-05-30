"""Тесты валидатора целостности (ТЗ Этап 2.2)."""
from __future__ import annotations

from mathesis import repo, validator
from mathesis.models import Dependency, Entity


def _mk(conn, eid, kind="def", **kw):
    repo.upsert_entity(conn, Entity(id=eid, kind=kind, title=eid, **kw))


def test_clean_graph_is_valid(canon_conn):
    _mk(canon_conn, "def-a")
    _mk(canon_conn, "def-b")
    repo.add_dependency(canon_conn, Dependency("def-a", "def-b"))
    report = validator.validate(canon_conn)
    assert report.is_valid
    assert report.cycles == []
    assert report.broken_refs == []


def test_detects_cycle(canon_conn):
    for x in ("a", "b", "c"):
        _mk(canon_conn, x)
    repo.add_dependency(canon_conn, Dependency("a", "b"))
    repo.add_dependency(canon_conn, Dependency("b", "c"))
    repo.add_dependency(canon_conn, Dependency("c", "a"))
    report = validator.validate(canon_conn)
    assert not report.is_valid
    assert any(set(cycle) == {"a", "b", "c"} for cycle in report.cycles)


def test_detects_broken_ref(canon_conn):
    _mk(canon_conn, "def-a")
    # Вставляем висячее ребро при выключенных FK (имитируем «грязную» сборку).
    canon_conn.execute("PRAGMA foreign_keys = OFF")
    canon_conn.execute(
        "INSERT INTO entity_dependency (source_id, target_id, role) VALUES ('def-a','def-missing','uses')"
    )
    canon_conn.commit()
    report = validator.validate(canon_conn)
    assert not report.is_valid
    assert any("def-missing" in b for b in report.broken_refs)


def test_unproven_listed(canon_conn):
    _mk(canon_conn, "prop-ok", kind="prop", lean_status="valid")
    _mk(canon_conn, "prop-sorry", kind="prop", lean_status="sorry")
    _mk(canon_conn, "prop-bad", kind="prop", lean_status="failed")
    report = validator.validate(canon_conn)
    assert set(report.unproven) == {"prop-sorry", "prop-bad"}
    # Недоказанные не делают граф «невалидным» сами по себе (нет битых ссылок/циклов).
    assert report.is_valid
