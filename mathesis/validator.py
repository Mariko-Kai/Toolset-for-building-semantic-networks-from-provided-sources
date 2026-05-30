"""Проверки целостности канонического графа (ТЗ Этап 2.2).

  * битые ссылки — рёбра/алиасы/источники, указывающие на отсутствующие сущности
    (возможно, если БД собиралась с выключенными FK);
  * циклы — поиск SCC алгоритмом Тарьяна (итеративно, без рекурсии и без ложных
    срабатываний наивного рекурсивного DFS);
  * недоказанные — сущности с lean_status ∈ {sorry, failed}.
"""
from __future__ import annotations

import sqlite3

from .models import ValidationReport


def validate(conn: sqlite3.Connection) -> ValidationReport:
    report = ValidationReport()
    report.broken_refs = _broken_refs(conn)
    report.cycles = _find_cycles(conn)
    report.unproven = _unproven(conn)
    report.is_valid = not (report.broken_refs or report.cycles)
    return report


def _broken_refs(conn: sqlite3.Connection) -> list[str]:
    broken: list[str] = []
    checks = [
        ("entity_dependency.source_id",
         "SELECT DISTINCT source_id FROM entity_dependency "
         "WHERE source_id NOT IN (SELECT entity_id FROM entities)"),
        ("entity_dependency.target_id",
         "SELECT DISTINCT target_id FROM entity_dependency "
         "WHERE target_id NOT IN (SELECT entity_id FROM entities)"),
        ("alias.entity_id",
         "SELECT DISTINCT entity_id FROM alias "
         "WHERE entity_id NOT IN (SELECT entity_id FROM entities)"),
        ("formulation_sources.entity_id",
         "SELECT DISTINCT entity_id FROM formulation_sources "
         "WHERE entity_id NOT IN (SELECT entity_id FROM entities)"),
    ]
    for label, sql in checks:
        for row in conn.execute(sql):
            broken.append(f"{label} -> {row[0]}")
    return broken


def _find_cycles(conn: sqlite3.Connection) -> list[list[str]]:
    """Поиск циклов через сильно связные компоненты (Тарьян, итеративно)."""
    adj: dict[str, list[str]] = {}
    for src, tgt in conn.execute("SELECT source_id, target_id FROM entity_dependency"):
        adj.setdefault(src, []).append(tgt)
        adj.setdefault(tgt, [])

    index_counter = [0]
    indexes: dict[str, int] = {}
    lowlink: dict[str, int] = {}
    on_stack: dict[str, bool] = {}
    stack: list[str] = []
    cycles: list[list[str]] = []

    for start in list(adj.keys()):
        if start in indexes:
            continue
        # Итеративный Тарьян: work-stack из (узел, итератор по соседям).
        work = [(start, iter(adj[start]))]
        indexes[start] = lowlink[start] = index_counter[0]
        index_counter[0] += 1
        stack.append(start)
        on_stack[start] = True

        while work:
            node, it = work[-1]
            advanced = False
            for w in it:
                if w not in indexes:
                    indexes[w] = lowlink[w] = index_counter[0]
                    index_counter[0] += 1
                    stack.append(w)
                    on_stack[w] = True
                    work.append((w, iter(adj[w])))
                    advanced = True
                    break
                elif on_stack.get(w):
                    lowlink[node] = min(lowlink[node], indexes[w])
            if advanced:
                continue
            work.pop()
            if work:
                parent = work[-1][0]
                lowlink[parent] = min(lowlink[parent], lowlink[node])
            if lowlink[node] == indexes[node]:
                comp = []
                while True:
                    w = stack.pop()
                    on_stack[w] = False
                    comp.append(w)
                    if w == node:
                        break
                # Цикл = SCC размера >1 ИЛИ петля сама на себя.
                if len(comp) > 1 or (comp[0] in adj.get(comp[0], [])):
                    cycles.append(sorted(comp))
    return cycles


def _unproven(conn: sqlite3.Connection) -> list[str]:
    rows = conn.execute(
        "SELECT entity_id FROM entities WHERE lean_status IN ('sorry','failed') ORDER BY entity_id"
    )
    return [r[0] for r in rows]
