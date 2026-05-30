"""Персистенция прогонов и инцидентов (ТЗ Этап 5.1).

Сохраняет RunState/EventLog/Incident в канонической БД (таблицы run/run_event/
incident), чтобы мониторинг переживал падения и был доступен для live-инспекции
(монитор-UI). Работает с обычным sqlite3.Connection.
"""
from __future__ import annotations

import datetime
import json
import sqlite3

from pipeline.orchestration.incidents import Incident, PatchPlan
from pipeline.orchestration.state import RunState


def _now() -> str:
    return datetime.datetime.now(datetime.timezone.utc).isoformat()


def save_run_state(conn: sqlite3.Connection, state: RunState, commit: bool = True) -> None:
    """Сохраняет/обновляет прогон и перезаписывает его события (идемпотентно)."""
    now = _now()
    created = conn.execute("SELECT created_at FROM run WHERE run_id = ?", (state.run_id,)).fetchone()
    created_at = created[0] if created and created[0] else now
    conn.execute(
        """
        INSERT INTO run (run_id, status, created_at, updated_at, health)
        VALUES (?, ?, ?, ?, ?)
        ON CONFLICT(run_id) DO UPDATE SET
            status=excluded.status, updated_at=excluded.updated_at, health=excluded.health
        """,
        (state.run_id, state.status, created_at, now, json.dumps(state.health(), ensure_ascii=False)),
    )
    # События перезаписываем целиком (append-only журнал прогона).
    conn.execute("DELETE FROM run_event WHERE run_id = ?", (state.run_id,))
    for e in state.events:
        conn.execute(
            "INSERT INTO run_event (run_id, seq, node, kind, status, message) VALUES (?, ?, ?, ?, ?, ?)",
            (state.run_id, e.seq, e.node, e.kind, e.status, e.message),
        )
    if commit:
        conn.commit()


def save_incident(conn: sqlite3.Connection, incident: Incident,
                  patch_plan: PatchPlan | None = None, resolution: str = "open",
                  commit: bool = True) -> int:
    """Сохраняет инцидент (+ опциональный план патча). Возвращает его id."""
    plan_json = None
    if patch_plan is not None:
        plan_json = json.dumps({
            "summary": patch_plan.summary, "steps": patch_plan.steps,
            "files": patch_plan.files, "tests": patch_plan.tests,
            "risk": patch_plan.risk, "auto_applicable": patch_plan.auto_applicable,
        }, ensure_ascii=False)
    cur = conn.execute(
        """
        INSERT INTO incident (run_id, node, status, severity, signals, context, message, resolution, patch_plan)
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (incident.run_id, incident.node, incident.status, incident.severity,
         json.dumps(incident.signals, ensure_ascii=False),
         json.dumps(incident.context, ensure_ascii=False),
         incident.message, resolution, plan_json),
    )
    if commit:
        conn.commit()
    return cur.lastrowid


def list_runs(conn: sqlite3.Connection, limit: int = 50) -> list[dict]:
    """Список последних прогонов (для монитора CLI/web)."""
    try:
        rows = conn.execute(
            "SELECT run_id, status, created_at, updated_at, health FROM run "
            "ORDER BY updated_at DESC LIMIT ?", (limit,)
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    out = []
    for r in rows:
        health = {}
        if r[4]:
            try:
                health = json.loads(r[4])
            except Exception:
                health = {}
        out.append({"run_id": r[0], "status": r[1], "created_at": r[2],
                    "updated_at": r[3], "health": health})
    return out


def open_incidents(conn: sqlite3.Connection) -> list[dict]:
    """Открытые инциденты (ожидающие решения человека)."""
    try:
        rows = conn.execute(
            "SELECT id, run_id, node, status, severity FROM incident "
            "WHERE resolution = 'open' ORDER BY id DESC"
        ).fetchall()
    except sqlite3.OperationalError:
        return []
    return [{"id": r[0], "run_id": r[1], "node": r[2], "status": r[3], "severity": r[4]} for r in rows]


def set_incident_resolution(conn: sqlite3.Connection, incident_id: int, resolution: str,
                            commit: bool = True) -> None:
    """Помечает инцидент confirmed/rejected/applied (для gate подтверждения)."""
    conn.execute("UPDATE incident SET resolution = ? WHERE id = ?", (resolution, incident_id))
    if commit:
        conn.commit()


def load_run(conn: sqlite3.Connection, run_id: str) -> dict | None:
    """Загружает прогон с событиями и инцидентами (для монитора/инспекции)."""
    row = conn.execute(
        "SELECT run_id, status, created_at, updated_at, health FROM run WHERE run_id = ?", (run_id,)
    ).fetchone()
    if not row:
        return None
    events = [
        {"seq": r[0], "node": r[1], "kind": r[2], "status": r[3], "message": r[4]}
        for r in conn.execute(
            "SELECT seq, node, kind, status, message FROM run_event WHERE run_id = ? ORDER BY seq", (run_id,)
        )
    ]
    incidents = [
        {"id": r[0], "node": r[1], "status": r[2], "severity": r[3], "resolution": r[4]}
        for r in conn.execute(
            "SELECT id, node, status, severity, resolution FROM incident WHERE run_id = ? ORDER BY id", (run_id,)
        )
    ]
    return {
        "run_id": row[0], "status": row[1], "created_at": row[2], "updated_at": row[3],
        "health": json.loads(row[4]) if row[4] else {},
        "events": events, "incidents": incidents,
    }
