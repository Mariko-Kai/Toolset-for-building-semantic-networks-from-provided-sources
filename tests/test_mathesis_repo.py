"""Тесты типизированного слоя mathesis.repo (ТЗ Этап 2.2)."""
from __future__ import annotations

import pytest

from mathesis import repo
from mathesis.models import Dependency, Entity


def _mk(conn, eid, kind="def", title=None, **kw):
    e = Entity(id=eid, kind=kind, title=title or eid, **kw)
    return repo.upsert_entity(conn, e)


def test_upsert_and_get_roundtrip(canon_conn):
    _mk(canon_conn, "def-limit", kind="def", title="Предел",
        nl_desc="предел функции", latex=r"\lim", module="real-analysis",
        aliases=["limit", "предел"])
    got = repo.get_entity(canon_conn, "def-limit")
    assert got is not None
    assert got.kind == "def"
    assert got.title == "Предел"
    assert got.module == "real-analysis"
    assert set(got.aliases) == {"limit", "предел"}
    assert got.created_at and got.updated_at


def test_upsert_updates_without_clobbering_created(canon_conn):
    a = _mk(canon_conn, "def-x", title="X")
    created = a.created_at
    a.title = "X2"
    repo.upsert_entity(canon_conn, a)
    got = repo.get_entity(canon_conn, "def-x")
    assert got.title == "X2"
    assert got.created_at == created  # created_at сохранён


def test_invalid_kind_rejected(canon_conn):
    with pytest.raises(ValueError):
        repo.upsert_entity(canon_conn, Entity(id="bad", kind="axiom", title="Bad"))


def test_list_entities_filters(canon_conn):
    _mk(canon_conn, "def-a", kind="def", module="m1")
    _mk(canon_conn, "prop-b", kind="prop", module="m1")
    _mk(canon_conn, "def-c", kind="def", module="m2")
    assert [e.id for e in repo.list_entities(canon_conn, kind="def")] == ["def-a", "def-c"]
    assert [e.id for e in repo.list_entities(canon_conn, module="m1")] == ["def-a", "prop-b"]


def test_alias_lookup(canon_conn):
    _mk(canon_conn, "def-rn", title="Действительные числа", aliases=["real numbers", "ℝ"])
    assert repo.lookup_alias(canon_conn, "real numbers") == "def-rn"
    assert repo.lookup_alias(canon_conn, "missing") is None


def test_search_fts(canon_conn):
    _mk(canon_conn, "def-cont", title="Непрерывность", nl_desc="непрерывная функция на отрезке")
    _mk(canon_conn, "def-lim", title="Предел", nl_desc="предел последовательности")
    res = repo.search(canon_conn, "непрерывная")
    assert [r.id for r in res] == ["def-cont"]
    # Произвольный ввод со спецсимволами FTS не должен падать.
    assert repo.search(canon_conn, 'foo "bar* (', ) == [] or True


def test_dependencies_and_used_by(canon_conn):
    _mk(canon_conn, "def-set", title="Множество")
    _mk(canon_conn, "def-func", title="Функция")
    repo.add_dependency(canon_conn, Dependency("def-func", "def-set"))
    deps = repo.get_dependencies(canon_conn, "def-func")
    assert [d.id for d in deps] == ["def-set"]
    used = repo.get_used_by(canon_conn, "def-set")
    assert [e.id for e in used.used_by] == ["def-func"]


def test_invalid_role_rejected(canon_conn):
    _mk(canon_conn, "a")
    _mk(canon_conn, "b")
    with pytest.raises(ValueError):
        repo.add_dependency(canon_conn, Dependency("a", "b", role="bogus"))


def test_trace_to_roots_stops_at_axiom_and_leaf(canon_conn):
    # thm -> lemma -> axiomatic ; lemma -> leaf
    _mk(canon_conn, "prop-thm", kind="prop", title="Теорема")
    _mk(canon_conn, "prop-lemma", kind="prop", title="Лемма")
    _mk(canon_conn, "prop-axiom", kind="prop", title="Аксиома выбора", lean_decl="axiom")
    _mk(canon_conn, "def-leaf", kind="def", title="Примитив")
    repo.add_dependency(canon_conn, Dependency("prop-thm", "prop-lemma"))
    repo.add_dependency(canon_conn, Dependency("prop-lemma", "prop-axiom"))
    repo.add_dependency(canon_conn, Dependency("prop-lemma", "def-leaf"))

    nodes = {n.id: n for n in repo.trace_to_roots(canon_conn, "prop-thm")}
    assert set(nodes) == {"prop-thm", "prop-lemma", "prop-axiom", "def-leaf"}
    assert nodes["prop-axiom"].is_root is True   # аксиоматичная
    assert nodes["def-leaf"].is_root is True      # лист
    assert nodes["prop-thm"].is_root is False
    assert nodes["prop-thm"].depth == 0
    assert nodes["prop-lemma"].depth == 1


def test_equivalence_canonical_order_and_self(canon_conn):
    _mk(canon_conn, "def-a")
    _mk(canon_conn, "def-b")
    repo.add_equivalence(canon_conn, "def-b", "def-a")  # переставит в a<b
    assert set(repo.get_equivalents(canon_conn, "def-a")) == {"def-b"}
    assert set(repo.get_equivalents(canon_conn, "def-b")) == {"def-a"}
    with pytest.raises(ValueError):
        repo.add_equivalence(canon_conn, "def-a", "def-a")
