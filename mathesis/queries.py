"""Query engine for mathesis.

All read operations: backlinks, DAG trace, FTS search, listing.
Functions accept a sqlite3.Connection and return model objects.
"""

from __future__ import annotations

import json
import sqlite3
from typing import Optional

from . import models


# ---------------------------------------------------------------------------
# Entity getters
# ---------------------------------------------------------------------------

def get_object(conn: sqlite3.Connection, id: str) -> Optional[models.Object]:
    row = conn.execute("SELECT * FROM object WHERE id = ?", (id,)).fetchone()
    if not row:
        return None
    return models.Object(
        id=row["id"], name=row["name"],
        aliases=json.loads(row["aliases"] or "[]"),
        module=row["module"],
        formal_definition=row["formal_definition"],
        intuition=row["intuition"],
        file_path=row["file_path"],
    )


def get_property(conn: sqlite3.Connection, id: str) -> Optional[models.Property]:
    row = conn.execute("SELECT * FROM property WHERE id = ?", (id,)).fetchone()
    if not row:
        return None
    return models.Property(
        id=row["id"], name=row["name"],
        aliases=json.loads(row["aliases"] or "[]"),
        module=row["module"],
        formal_definition=row["formal_definition"],
        equivalent_forms=row["equivalent_forms"],
        file_path=row["file_path"],
    )


def get_operation(conn: sqlite3.Connection, id: str) -> Optional[models.Operation]:
    row = conn.execute("SELECT * FROM operation WHERE id = ?", (id,)).fetchone()
    if not row:
        return None
    return models.Operation(
        id=row["id"], name=row["name"],
        aliases=json.loads(row["aliases"] or "[]"),
        module=row["module"], arity=row["arity"],
        formal_definition=row["formal_definition"],
        codomain_id=row["codomain_id"],
        file_path=row["file_path"],
    )


def get_theorem(conn: sqlite3.Connection, id: str) -> Optional[models.Theorem]:
    row = conn.execute("SELECT * FROM theorem WHERE id = ?", (id,)).fetchone()
    if not row:
        return None
    return models.Theorem(
        id=row["id"], name=row["name"],
        subtype=row["subtype"],
        parent_theorem_id=row["parent_theorem_id"],
        module=row["module"],
        statement=row["statement"], proof=row["proof"],
        strategy=row["strategy"],
        file_path=row["file_path"],
    )


def get_axiom(conn: sqlite3.Connection, id: str) -> Optional[models.Axiom]:
    row = conn.execute("SELECT * FROM axiom WHERE id = ?", (id,)).fetchone()
    if not row:
        return None
    return models.Axiom(
        id=row["id"], name=row["name"],
        system=row["system"], statement=row["statement"],
        file_path=row["file_path"],
    )


# ---------------------------------------------------------------------------
# Listing
# ---------------------------------------------------------------------------

def _rows_to_objects(rows) -> list[models.Object]:
    return [models.Object(
        id=r["id"], name=r["name"],
        aliases=json.loads(r["aliases"] or "[]"),
        module=r["module"],
        formal_definition=r["formal_definition"],
        intuition=r["intuition"], file_path=r["file_path"],
    ) for r in rows]


def list_objects(conn: sqlite3.Connection,
                 module: str = None) -> list[models.Object]:
    if module:
        rows = conn.execute(
            "SELECT * FROM object WHERE module = ? ORDER BY name", (module,)
        ).fetchall()
    else:
        rows = conn.execute("SELECT * FROM object ORDER BY name").fetchall()
    return _rows_to_objects(rows)


def list_properties(conn: sqlite3.Connection,
                    module: str = None) -> list[models.Property]:
    sql = "SELECT * FROM property"
    params: tuple = ()
    if module:
        sql += " WHERE module = ?"
        params = (module,)
    sql += " ORDER BY name"
    return [models.Property(
        id=r["id"], name=r["name"],
        aliases=json.loads(r["aliases"] or "[]"),
        module=r["module"],
        formal_definition=r["formal_definition"],
        equivalent_forms=r["equivalent_forms"],
        file_path=r["file_path"],
    ) for r in conn.execute(sql, params).fetchall()]


def list_operations(conn: sqlite3.Connection,
                    module: str = None) -> list[models.Operation]:
    sql = "SELECT * FROM operation"
    params: tuple = ()
    if module:
        sql += " WHERE module = ?"
        params = (module,)
    sql += " ORDER BY name"
    return [models.Operation(
        id=r["id"], name=r["name"],
        aliases=json.loads(r["aliases"] or "[]"),
        module=r["module"], arity=r["arity"],
        formal_definition=r["formal_definition"],
        codomain_id=r["codomain_id"],
        file_path=r["file_path"],
    ) for r in conn.execute(sql, params).fetchall()]


def list_theorems(conn: sqlite3.Connection,
                  module: str = None,
                  subtype: str = None) -> list[models.Theorem]:
    sql = "SELECT * FROM theorem WHERE 1=1"
    params: list = []
    if module:
        sql += " AND module = ?"
        params.append(module)
    if subtype:
        sql += " AND subtype = ?"
        params.append(subtype)
    sql += " ORDER BY name"
    return [models.Theorem(
        id=r["id"], name=r["name"],
        subtype=r["subtype"],
        parent_theorem_id=r["parent_theorem_id"],
        module=r["module"],
        statement=r["statement"], proof=r["proof"],
        strategy=r["strategy"], file_path=r["file_path"],
    ) for r in conn.execute(sql, params).fetchall()]


def list_axioms(conn: sqlite3.Connection) -> list[models.Axiom]:
    return [models.Axiom(
        id=r["id"], name=r["name"],
        system=r["system"], statement=r["statement"],
        file_path=r["file_path"],
    ) for r in conn.execute("SELECT * FROM axiom ORDER BY name").fetchall()]


def list_modules(conn: sqlite3.Connection) -> list[str]:
    """Get all distinct module names across all entity types."""
    modules = set()
    for table in ("object", "property", "operation", "theorem"):
        rows = conn.execute(
            f"SELECT DISTINCT module FROM {table} WHERE module != ''"
        ).fetchall()
        modules.update(r["module"] for r in rows)
    return sorted(modules)


def list_by_module(conn: sqlite3.Connection, module: str) -> dict:
    """Get all entities in a module, grouped by type."""
    return {
        "objects": list_objects(conn, module),
        "properties": list_properties(conn, module),
        "operations": list_operations(conn, module),
        "theorems": list_theorems(conn, module),
    }


# ---------------------------------------------------------------------------
# Relationships
# ---------------------------------------------------------------------------

def get_object_properties(conn: sqlite3.Connection,
                          object_id: str) -> list[models.ObjectProperty]:
    rows = conn.execute(
        "SELECT * FROM object_property WHERE object_id = ?", (object_id,)
    ).fetchall()
    return [models.ObjectProperty(
        id=r["id"], object_id=r["object_id"],
        property_id=r["property_id"],
        context=r["context"], context_ref=r["context_ref"],
    ) for r in rows]


def get_operation_arguments(conn: sqlite3.Connection,
                            operation_id: str) -> list[models.OperationArgument]:
    rows = conn.execute(
        "SELECT * FROM operation_argument WHERE operation_id = ? ORDER BY position",
        (operation_id,)
    ).fetchall()
    return [models.OperationArgument(
        operation_id=r["operation_id"], position=r["position"],
        object_id=r["object_id"], role=r["role"],
    ) for r in rows]


def get_lemmas(conn: sqlite3.Connection,
               theorem_id: str) -> list[models.Theorem]:
    rows = conn.execute(
        "SELECT * FROM theorem WHERE parent_theorem_id = ? ORDER BY name",
        (theorem_id,)
    ).fetchall()
    return [models.Theorem(
        id=r["id"], name=r["name"],
        subtype=r["subtype"],
        parent_theorem_id=r["parent_theorem_id"],
        module=r["module"],
        statement=r["statement"], proof=r["proof"],
        strategy=r["strategy"], file_path=r["file_path"],
    ) for r in rows]


def get_dependencies(conn: sqlite3.Connection,
                     theorem_id: str) -> list[models.Theorem]:
    rows = conn.execute("""
        SELECT t.* FROM theorem t
        JOIN theorem_dependency td ON t.id = td.used_thm_id
        WHERE td.theorem_id = ?
        ORDER BY t.name
    """, (theorem_id,)).fetchall()
    return [models.Theorem(
        id=r["id"], name=r["name"],
        subtype=r["subtype"],
        parent_theorem_id=r["parent_theorem_id"],
        module=r["module"],
        statement=r["statement"], proof=r["proof"],
        strategy=r["strategy"], file_path=r["file_path"],
    ) for r in rows]


# ---------------------------------------------------------------------------
# Backlinks
# ---------------------------------------------------------------------------

def get_used_by(conn: sqlite3.Connection,
                entity_id: str) -> models.UsedByResult:
    """Find all entities that reference the given entity_id."""
    result = models.UsedByResult(entity_id=entity_id)

    # Theorems referencing this object
    for r in conn.execute(
        "SELECT t.* FROM theorem t JOIN theorem_object to2 ON t.id = to2.theorem_id "
        "WHERE to2.object_id = ?", (entity_id,)
    ).fetchall():
        result.theorems.append(models.Theorem(
            id=r["id"], name=r["name"], subtype=r["subtype"],
            module=r["module"], statement=r["statement"],
            file_path=r["file_path"],
        ))

    # Theorems referencing this property
    for r in conn.execute(
        "SELECT t.* FROM theorem t JOIN theorem_property tp ON t.id = tp.theorem_id "
        "WHERE tp.property_id = ?", (entity_id,)
    ).fetchall():
        if not any(t.id == r["id"] for t in result.theorems):
            result.theorems.append(models.Theorem(
                id=r["id"], name=r["name"], subtype=r["subtype"],
                module=r["module"], statement=r["statement"],
                file_path=r["file_path"],
            ))

    # Theorems referencing this operation
    for r in conn.execute(
        "SELECT t.* FROM theorem t JOIN theorem_operation top ON t.id = top.theorem_id "
        "WHERE top.operation_id = ?", (entity_id,)
    ).fetchall():
        if not any(t.id == r["id"] for t in result.theorems):
            result.theorems.append(models.Theorem(
                id=r["id"], name=r["name"], subtype=r["subtype"],
                module=r["module"], statement=r["statement"],
                file_path=r["file_path"],
            ))

    # Theorems depending on this theorem (reverse DAG)
    for r in conn.execute(
        "SELECT t.* FROM theorem t JOIN theorem_dependency td ON t.id = td.theorem_id "
        "WHERE td.used_thm_id = ?", (entity_id,)
    ).fetchall():
        if not any(t.id == r["id"] for t in result.theorems):
            result.theorems.append(models.Theorem(
                id=r["id"], name=r["name"], subtype=r["subtype"],
                module=r["module"], statement=r["statement"],
                file_path=r["file_path"],
            ))

    return result


# ---------------------------------------------------------------------------
# Graph: trace to axioms (recursive CTE)
# ---------------------------------------------------------------------------

def trace_to_axioms(conn: sqlite3.Connection,
                    theorem_id: str) -> list[models.TraceNode]:
    """Walk the dependency DAG from theorem_id down to axioms."""
    rows = conn.execute("""
        WITH RECURSIVE dep_chain(thm_id, depth) AS (
            SELECT ?, 0
            UNION ALL
            SELECT td.used_thm_id, dc.depth + 1
            FROM theorem_dependency td
            JOIN dep_chain dc ON dc.thm_id = td.theorem_id
        )
        SELECT
            t.id, t.name, t.subtype, dc.depth,
            GROUP_CONCAT(ta.axiom_id) AS axiom_ids
        FROM dep_chain dc
        JOIN theorem t ON t.id = dc.thm_id
        LEFT JOIN theorem_axiom ta ON ta.theorem_id = t.id
        GROUP BY t.id
        ORDER BY dc.depth
    """, (theorem_id,)).fetchall()

    return [models.TraceNode(
        id=r["id"], name=r["name"],
        subtype=r["subtype"], depth=r["depth"],
        axiom_ids=(r["axiom_ids"] or "").split(",") if r["axiom_ids"] else [],
    ) for r in rows]


# ---------------------------------------------------------------------------
# Full DAG export
# ---------------------------------------------------------------------------

def get_full_dag(conn: sqlite3.Connection) -> list[models.TheoremDependency]:
    rows = conn.execute("SELECT * FROM theorem_dependency").fetchall()
    return [models.TheoremDependency(
        theorem_id=r["theorem_id"],
        used_thm_id=r["used_thm_id"],
        proof_step=r["proof_step"],
    ) for r in rows]


# ---------------------------------------------------------------------------
# Equivalences & Composition
# ---------------------------------------------------------------------------

def get_equivalents(conn: sqlite3.Connection,
                    entity_id: str) -> list[models.Equivalence]:
    rows = conn.execute("""
        SELECT * FROM equivalence
        WHERE entity_a_id = ? OR entity_b_id = ?
    """, (entity_id, entity_id)).fetchall()
    return [models.Equivalence(
        entity_a_id=r["entity_a_id"],
        entity_b_id=r["entity_b_id"],
        proof_id=r["proof_id"],
    ) for r in rows]


def get_components(conn: sqlite3.Connection,
                   object_id: str) -> list[models.ObjectComposition]:
    rows = conn.execute(
        "SELECT * FROM object_composition WHERE container_id = ?", (object_id,)
    ).fetchall()
    return [models.ObjectComposition(
        container_id=r["container_id"],
        obj_comp_id=r["obj_comp_id"],
        prop_comp_id=r["prop_comp_id"],
        op_comp_id=r["op_comp_id"],
        role=r["role"],
    ) for r in rows]


def get_containers(conn: sqlite3.Connection,
                   component_id: str) -> list[models.Object]:
    """Find all container objects that include component_id."""
    rows = conn.execute("""
        SELECT o.* FROM object o
        JOIN object_composition oc ON o.id = oc.container_id
        WHERE oc.obj_comp_id = ? OR oc.prop_comp_id = ? OR oc.op_comp_id = ?
    """, (component_id, component_id, component_id)).fetchall()
    return _rows_to_objects(rows)


# ---------------------------------------------------------------------------
# Aliases & Future Nodes Pruning (PDSE)
# ---------------------------------------------------------------------------

def lookup_alias(conn: sqlite3.Connection, alias: str) -> Optional[str]:
    row = conn.execute("SELECT entity_id FROM alias_registry WHERE alias = ?", (alias,)).fetchone()
    return row["entity_id"] if row else None


def filter_future_nodes(conn: sqlite3.Connection, candidate_ids: list[str], current_page: int) -> list[str]:
    # Placeholder for page-based pruning if page data is injected, or topological pruning.
    # We return candidates as is for now, or filter if page info becomes available in SQL.
    # The actual implementation of "страницы > текущей" requires a page column.
    return candidate_ids


# ---------------------------------------------------------------------------
# Full-text search
# ---------------------------------------------------------------------------

def search(conn: sqlite3.Connection,
           query: str,
           entity_type: str = None) -> list[models.SearchResult]:
    sql = """
        SELECT entity_id, entity_type, name,
               snippet(entity_fts, 3, '<b>', '</b>', '...', 32) AS snippet
        FROM entity_fts
        WHERE entity_fts MATCH ?
    """
    params: list = [query]
    if entity_type:
        sql += " AND entity_type = ?"
        params.append(entity_type)
    sql += " ORDER BY rank LIMIT 50"

    return [models.SearchResult(
        id=r["entity_id"], name=r["name"],
        entity_type=r["entity_type"],
        snippet=r["snippet"],
    ) for r in conn.execute(sql, params).fetchall()]
