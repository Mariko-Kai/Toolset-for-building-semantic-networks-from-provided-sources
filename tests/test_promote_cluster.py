"""Тесты идемпотентного промоушена кластера в канон (ТЗ Этап 2.4)."""
from __future__ import annotations

from mathesis import repo
from pipeline.canonical_synthesizer import promote_cluster


def _promote(conn, **over):
    kw = dict(
        cluster_id="c1", entity_id="def-foo", entity_type="def",
        title="Foo", nl_desc="барбар", tex_path="content/defs/Foo [def-foo].tex",
        lean_code="def foo := 1", sources=["zorich", "fichtenholz"],
        page_refs=[10, 12], deps=["def-base", "def-base", " "],
    )
    kw.update(over)
    return promote_cluster(conn, **kw)


def _count(conn, sql, params=()):
    return conn.execute(sql, params).fetchone()[0]


def test_promote_creates_entity_with_lean_meta(canon_conn):
    _promote(canon_conn)
    e = repo.get_entity(canon_conn, "def-foo")
    assert e is not None
    assert e.kind == "def"
    assert e.nl_desc == "барбар"
    assert e.lean_code == "def foo := 1"
    assert e.lean_decl == "def"
    assert e.lean_status == "valid"
    assert e.tex_path.endswith("Foo [def-foo].tex")


def test_promote_syncs_fts(canon_conn):
    _promote(canon_conn)
    # Синтезированная сущность сразу видна полнотекстовому поиску.
    assert any(r.id == "def-foo" for r in repo.search(canon_conn, "барбар"))


def test_promote_sources_and_pending_and_map(canon_conn):
    _promote(canon_conn)
    srcs = repo.get_sources(canon_conn, "def-foo")
    assert {s.source_book for s in srcs} == {"zorich", "fichtenholz"}
    assert _count(canon_conn, "SELECT count(*) FROM pending_edges WHERE source_id='def-foo'") == 1
    assert _count(canon_conn, "SELECT count(*) FROM cluster_entity_map WHERE cluster_id='c1'") == 1


def test_promote_is_idempotent(canon_conn):
    _promote(canon_conn)
    _promote(canon_conn)  # повторный вызов с теми же данными
    assert _count(canon_conn, "SELECT count(*) FROM entities WHERE entity_id='def-foo'") == 1
    assert len(repo.get_sources(canon_conn, "def-foo")) == 2          # не задвоилось
    assert _count(canon_conn, "SELECT count(*) FROM pending_edges WHERE source_id='def-foo'") == 1


def test_promote_detects_sorry(canon_conn):
    _promote(canon_conn, entity_id="prop-t", entity_type="prop",
             lean_code="theorem t : True := by sorry", deps=[])
    e = repo.get_entity(canon_conn, "prop-t")
    assert e.lean_decl == "theorem"
    assert e.lean_status == "sorry"


def test_promote_without_lean_is_unvalidated(canon_conn):
    _promote(canon_conn, entity_id="def-bare", lean_code="", deps=[])
    e = repo.get_entity(canon_conn, "def-bare")
    assert e.lean_status == "unvalidated"
    assert e.lean_decl == ""
