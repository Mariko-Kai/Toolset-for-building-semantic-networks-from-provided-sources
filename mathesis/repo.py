"""Типизированный слой доступа к канонической схеме (ТЗ Этап 2.2).

Все функции принимают `sqlite3.Connection` первым аргументом (без скрытого
глобального состояния). Сущность `Entity` — источник истины: `upsert_entity`
синхронизирует и FTS-индекс, и алиасы.
"""
from __future__ import annotations

import datetime
import sqlite3
from typing import Optional

from .models import (
    DepRole,
    Dependency,
    Entity,
    Kind,
    SearchResult,
    Source,
    TraceNode,
    UsedByResult,
)

_MAX_TRACE_DEPTH = 64  # предохранитель от циклов в рекурсивном CTE

_ENTITY_COLS = (
    "entity_id, type, title, path, file_path, lean_path, nl_desc, module, "
    "latex, lean_code, lean_decl, lean_status, created_at, updated_at"
)


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def _row_to_entity(row: sqlite3.Row, aliases: Optional[list[str]] = None) -> Entity:
    return Entity(
        id=row["entity_id"],
        kind=row["type"],
        title=row["title"],
        module=row["module"] or "",
        nl_desc=row["nl_desc"] or "",
        latex=row["latex"] or "",
        lean_code=row["lean_code"] or "",
        lean_decl=row["lean_decl"] or "",
        lean_status=row["lean_status"] or "unvalidated",
        tex_path=row["file_path"] or "",
        lean_path=row["lean_path"] or "",
        path=row["path"] or "",
        aliases=aliases if aliases is not None else [],
        created_at=row["created_at"] or "",
        updated_at=row["updated_at"] or "",
    )


# --- Валидация enum ----------------------------------------------------------
def _check_kind(kind: str) -> None:
    if kind not in (Kind.DEF.value, Kind.PROP.value):
        raise ValueError(f"Недопустимый kind '{kind}'. Допустимо: def | prop.")


def _check_role(role: str) -> None:
    valid = {r.value for r in DepRole}
    if role not in valid:
        raise ValueError(f"Недопустимая роль ребра '{role}'. Допустимо: {sorted(valid)}.")


# --- CRUD: сущности ----------------------------------------------------------
def get_entity(conn: sqlite3.Connection, entity_id: str) -> Optional[Entity]:
    row = conn.execute(
        f"SELECT {_ENTITY_COLS} FROM entities WHERE entity_id = ?", (entity_id,)
    ).fetchone()
    if not row:
        return None
    aliases = [r[0] for r in conn.execute(
        "SELECT alias FROM alias WHERE entity_id = ? ORDER BY alias", (entity_id,)
    )]
    return _row_to_entity(row, aliases)


def list_modules(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT DISTINCT module FROM entities WHERE module IS NOT NULL AND module != '' ORDER BY module"
    )
    return [r[0] for r in rows]


def list_entities(conn: sqlite3.Connection, kind: Optional[str] = None,
                  module: Optional[str] = None) -> list[Entity]:
    sql = f"SELECT {_ENTITY_COLS} FROM entities"
    clauses, params = [], []
    if kind:
        _check_kind(kind)
        clauses.append("type = ?")
        params.append(kind)
    if module:
        clauses.append("module = ?")
        params.append(module)
    if clauses:
        sql += " WHERE " + " AND ".join(clauses)
    sql += " ORDER BY entity_id"
    return [_row_to_entity(r) for r in conn.execute(sql, params)]


def upsert_entity(conn: sqlite3.Connection, entity: Entity, commit: bool = True) -> Entity:
    """Создаёт/обновляет сущность и синхронизирует FTS-индекс и алиасы.

    `embedding` НЕ трогается (управляется отдельно через set_embedding), поэтому
    повторный upsert не затирает ранее посчитанный вектор.
    """
    _check_kind(entity.kind)
    now = _now()
    created = entity.created_at or now
    conn.execute(
        f"""
        INSERT INTO entities ({_ENTITY_COLS})
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(entity_id) DO UPDATE SET
            type=excluded.type, title=excluded.title, path=excluded.path,
            file_path=excluded.file_path, lean_path=excluded.lean_path,
            nl_desc=excluded.nl_desc, module=excluded.module, latex=excluded.latex,
            lean_code=excluded.lean_code, lean_decl=excluded.lean_decl,
            lean_status=excluded.lean_status, updated_at=excluded.updated_at
        """,
        (entity.id, entity.kind, entity.title, entity.path, entity.tex_path,
         entity.lean_path, entity.nl_desc, entity.module, entity.latex,
         entity.lean_code, entity.lean_decl, entity.lean_status, created, now),
    )
    _sync_fts(conn, entity)
    _sync_aliases(conn, entity.id, entity.aliases)
    if commit:
        conn.commit()
    entity.created_at = created
    entity.updated_at = now
    return entity


def delete_entity(conn: sqlite3.Connection, entity_id: str, commit: bool = True) -> None:
    conn.execute("DELETE FROM entity_fts WHERE entity_id = ?", (entity_id,))
    conn.execute("DELETE FROM entities WHERE entity_id = ?", (entity_id,))
    if commit:
        conn.commit()


def set_embedding(conn: sqlite3.Connection, entity_id: str, blob: bytes, commit: bool = True) -> None:
    conn.execute("UPDATE entities SET embedding = ? WHERE entity_id = ?", (blob, entity_id))
    if commit:
        conn.commit()


# --- FTS ---------------------------------------------------------------------
def _sync_fts(conn: sqlite3.Connection, entity: Entity) -> None:
    conn.execute("DELETE FROM entity_fts WHERE entity_id = ?", (entity.id,))
    conn.execute(
        "INSERT INTO entity_fts (entity_id, type, title, nl_desc, latex) VALUES (?, ?, ?, ?, ?)",
        (entity.id, entity.kind, entity.title, entity.nl_desc, entity.latex),
    )


def reindex_fts(conn: sqlite3.Connection, commit: bool = True) -> int:
    """Полностью перестраивает FTS-индекс из таблицы entities."""
    conn.execute("DELETE FROM entity_fts")
    n = conn.execute(
        "INSERT INTO entity_fts (entity_id, type, title, nl_desc, latex) "
        "SELECT entity_id, type, title, COALESCE(nl_desc,''), COALESCE(latex,'') FROM entities"
    ).rowcount
    if commit:
        conn.commit()
    return n


def search(conn: sqlite3.Connection, query: str, kind: Optional[str] = None,
           limit: int = 50, offset: int = 0) -> list[SearchResult]:
    """FTS-поиск с пагинацией. Запрос экранируется как фраза (безопасно для
    произвольного ввода пользователя)."""
    if not query or not query.strip():
        return []
    match = '"' + query.replace('"', '""') + '"'  # фразовый запрос, экранирование
    sql = (
        "SELECT f.entity_id, e.title, e.type, "
        "snippet(entity_fts, -1, '<b>', '</b>', '...', 16) AS snip "
        "FROM entity_fts f JOIN entities e ON e.entity_id = f.entity_id "
        "WHERE entity_fts MATCH ?"
    )
    params: list = [match]
    if kind:
        _check_kind(kind)
        sql += " AND e.type = ?"
        params.append(kind)
    sql += " ORDER BY rank LIMIT ? OFFSET ?"
    params.extend([limit, offset])
    try:
        rows = conn.execute(sql, params).fetchall()
    except sqlite3.OperationalError:
        return []
    return [SearchResult(id=r["entity_id"], title=r["title"], kind=r["type"], snippet=r["snip"]) for r in rows]


# --- Алиасы ------------------------------------------------------------------
def _sync_aliases(conn: sqlite3.Connection, entity_id: str, aliases: list[str]) -> None:
    conn.execute("DELETE FROM alias WHERE entity_id = ?", (entity_id,))
    for a in aliases:
        if a and a.strip():
            conn.execute(
                "INSERT OR REPLACE INTO alias (alias, entity_id) VALUES (?, ?)",
                (a.strip(), entity_id),
            )


def lookup_alias(conn: sqlite3.Connection, alias: str) -> Optional[str]:
    row = conn.execute("SELECT entity_id FROM alias WHERE alias = ?", (alias,)).fetchone()
    return row[0] if row else None


# --- Провенанс ---------------------------------------------------------------
def add_source(conn: sqlite3.Connection, source: Source, commit: bool = True) -> None:
    conn.execute(
        "INSERT INTO formulation_sources (entity_id, source_book, page_info) VALUES (?, ?, ?)",
        (source.entity_id, source.source_book, source.page_info),
    )
    if commit:
        conn.commit()


def get_sources(conn: sqlite3.Connection, entity_id: str) -> list[Source]:
    rows = conn.execute(
        "SELECT id, entity_id, source_book, page_info FROM formulation_sources "
        "WHERE entity_id = ? ORDER BY id", (entity_id,)
    )
    return [Source(entity_id=r["entity_id"], source_book=r["source_book"],
                   page_info=r["page_info"] or "", id=r["id"]) for r in rows]


# --- Граф зависимостей -------------------------------------------------------
def add_dependency(conn: sqlite3.Connection, dep: Dependency, commit: bool = True) -> None:
    _check_role(dep.role)
    conn.execute(
        "INSERT OR IGNORE INTO entity_dependency (source_id, target_id, role, proof_step) "
        "VALUES (?, ?, ?, ?)",
        (dep.source_id, dep.target_id, dep.role, dep.proof_step or None),
    )
    if commit:
        conn.commit()


def get_dependencies(conn: sqlite3.Connection, entity_id: str) -> list[Entity]:
    """Сущности, от которых зависит `entity_id` (исходящие рёбра)."""
    rows = conn.execute(
        f"SELECT {_ENTITY_COLS} FROM entities e "
        "JOIN entity_dependency d ON d.target_id = e.entity_id "
        "WHERE d.source_id = ? ORDER BY e.entity_id", (entity_id,)
    )
    return [_row_to_entity(r) for r in rows]


def get_used_by(conn: sqlite3.Connection, entity_id: str) -> UsedByResult:
    """Сущности, которые зависят от `entity_id` (входящие рёбра, обратные ссылки)."""
    rows = conn.execute(
        f"SELECT DISTINCT {_ENTITY_COLS} FROM entities e "
        "JOIN entity_dependency d ON d.source_id = e.entity_id "
        "WHERE d.target_id = ? ORDER BY e.entity_id", (entity_id,)
    )
    return UsedByResult(entity_id=entity_id, used_by=[_row_to_entity(r) for r in rows])


def get_full_dag(conn: sqlite3.Connection) -> list[Dependency]:
    rows = conn.execute(
        "SELECT source_id, target_id, role, proof_step FROM entity_dependency "
        "ORDER BY source_id, target_id"
    )
    return [Dependency(source_id=r["source_id"], target_id=r["target_id"],
                       role=r["role"], proof_step=r["proof_step"] or "") for r in rows]


def trace_to_roots(conn: sqlite3.Connection, entity_id: str) -> list[TraceNode]:
    """Трассирует зависимости вглубь до корней. Корень = аксиоматичная сущность
    (`lean_decl='axiom'`) ИЛИ лист DAG (нет исходящих рёбер). Раскрытие не идёт
    дальше аксиом. Глубина ограничена предохранителем от циклов."""
    rows = conn.execute(
        """
        WITH RECURSIVE chain(id, depth) AS (
            SELECT ?, 0
            UNION
            SELECT d.target_id, c.depth + 1
            FROM chain c
            JOIN entity_dependency d ON d.source_id = c.id
            JOIN entities e ON e.entity_id = c.id
            WHERE c.depth < ? AND COALESCE(e.lean_decl, '') != 'axiom'
        )
        SELECT e.entity_id, e.title, e.type, e.lean_decl, MIN(chain.depth) AS depth
        FROM chain JOIN entities e ON e.entity_id = chain.id
        GROUP BY e.entity_id
        ORDER BY depth, e.entity_id
        """,
        (entity_id, _MAX_TRACE_DEPTH),
    ).fetchall()

    sources = {r[0] for r in conn.execute("SELECT DISTINCT source_id FROM entity_dependency")}
    nodes = []
    for r in rows:
        is_root = (r["lean_decl"] == "axiom") or (r["entity_id"] not in sources)
        nodes.append(TraceNode(id=r["entity_id"], title=r["title"], kind=r["type"],
                               depth=r["depth"], is_root=is_root))
    return nodes


# --- Эквивалентности ---------------------------------------------------------
def add_equivalence(conn: sqlite3.Connection, a_id: str, b_id: str,
                    proof_id: Optional[str] = None, commit: bool = True) -> None:
    if a_id == b_id:
        raise ValueError("Эквивалентность сущности самой с собой бессмысленна.")
    if a_id > b_id:
        a_id, b_id = b_id, a_id
    conn.execute(
        "INSERT OR IGNORE INTO equivalence (entity_a_id, entity_b_id, proof_id) VALUES (?, ?, ?)",
        (a_id, b_id, proof_id),
    )
    if commit:
        conn.commit()


def get_equivalents(conn: sqlite3.Connection, entity_id: str) -> list[str]:
    rows = conn.execute(
        "SELECT entity_b_id AS other FROM equivalence WHERE entity_a_id = ? "
        "UNION SELECT entity_a_id AS other FROM equivalence WHERE entity_b_id = ?",
        (entity_id, entity_id),
    )
    return [r[0] for r in rows]
