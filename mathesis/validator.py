"""Validation utilities for mathesis.

Checks referential integrity, DAG acyclicity, and data consistency.
"""

from __future__ import annotations

import sqlite3

from . import models


def validate(conn: sqlite3.Connection) -> models.ValidationReport:
    """Run all validation checks and return a report."""
    report = models.ValidationReport()

    _check_broken_refs(conn, report)
    _check_dag_cycles(conn, report)
    _check_orphan_lemmas(conn, report)

    report.is_valid = (
        not report.broken_refs
        and not report.cycles
        and not report.orphan_lemmas
    )
    return report


def _check_broken_refs(conn: sqlite3.Connection,
                       report: models.ValidationReport) -> None:
    """Check all FK-like references for dangling IDs."""

    # theorem_object → object
    for r in conn.execute("""
        SELECT to2.object_id FROM theorem_object to2
        LEFT JOIN object o ON o.id = to2.object_id
        WHERE o.id IS NULL
    """).fetchall():
        report.broken_refs.append(f"theorem_object → object '{r[0]}' not found")

    # theorem_property → property
    for r in conn.execute("""
        SELECT tp.property_id FROM theorem_property tp
        LEFT JOIN property p ON p.id = tp.property_id
        WHERE p.id IS NULL
    """).fetchall():
        report.broken_refs.append(f"theorem_property → property '{r[0]}' not found")

    # theorem_operation → operation
    for r in conn.execute("""
        SELECT top.operation_id FROM theorem_operation top
        LEFT JOIN operation op ON op.id = top.operation_id
        WHERE op.id IS NULL
    """).fetchall():
        report.broken_refs.append(
            f"theorem_operation → operation '{r[0]}' not found"
        )

    # theorem_axiom → axiom
    for r in conn.execute("""
        SELECT ta.axiom_id FROM theorem_axiom ta
        LEFT JOIN axiom a ON a.id = ta.axiom_id
        WHERE a.id IS NULL
    """).fetchall():
        report.broken_refs.append(f"theorem_axiom → axiom '{r[0]}' not found")

    # theorem_dependency → theorem
    for r in conn.execute("""
        SELECT td.used_thm_id FROM theorem_dependency td
        LEFT JOIN theorem t ON t.id = td.used_thm_id
        WHERE t.id IS NULL
    """).fetchall():
        report.broken_refs.append(
            f"theorem_dependency → theorem '{r[0]}' not found"
        )

    # operation.codomain_id → object
    for r in conn.execute("""
        SELECT op.id, op.codomain_id FROM operation op
        LEFT JOIN object o ON o.id = op.codomain_id
        WHERE op.codomain_id IS NOT NULL AND o.id IS NULL
    """).fetchall():
        report.broken_refs.append(
            f"operation '{r[0]}' → codomain '{r[1]}' not found"
        )


def _check_dag_cycles(conn: sqlite3.Connection,
                      report: models.ValidationReport) -> None:
    """Detect cycles in the theorem_dependency graph using DFS."""
    edges: dict[str, list[str]] = {}
    for r in conn.execute("SELECT theorem_id, used_thm_id FROM theorem_dependency"):
        edges.setdefault(r[0], []).append(r[1])

    visited: set[str] = set()
    in_stack: set[str] = set()
    path: list[str] = []

    def dfs(node: str) -> None:
        if node in in_stack:
            cycle_start = path.index(node)
            report.cycles.append(path[cycle_start:] + [node])
            return
        if node in visited:
            return
        visited.add(node)
        in_stack.add(node)
        path.append(node)
        for neighbor in edges.get(node, []):
            dfs(neighbor)
        path.pop()
        in_stack.discard(node)

    for node in edges:
        if node not in visited:
            dfs(node)


def _check_orphan_lemmas(conn: sqlite3.Connection,
                         report: models.ValidationReport) -> None:
    """Find lemmas whose parent_theorem_id points to a non-existent theorem."""
    for r in conn.execute("""
        SELECT l.id, l.parent_theorem_id FROM theorem l
        LEFT JOIN theorem p ON p.id = l.parent_theorem_id
        WHERE l.subtype = 'lemma' AND p.id IS NULL
    """).fetchall():
        report.orphan_lemmas.append(
            f"lemma '{r[0]}' → parent '{r[1]}' not found"
        )
