"""Тесты CLI-мониторинга (ТЗ: мониторинг в CLI)."""
from __future__ import annotations

from pipeline import monitor
from pipeline.nodes import NodeResult, NodeStatus
from pipeline.orchestration import list_runs, open_incidents, save_incident, save_run_state, set_incident_resolution
from pipeline.orchestration.incidents import Incident
from pipeline.orchestration.state import RunState


def _seed(conn):
    s = RunState(run_id="r1")
    s.record_start("extract")
    s.record_result("extract", NodeResult(NodeStatus.OK))
    s.record_start("synth")
    s.record_result("synth", NodeResult(NodeStatus.DEVIATION, message="0 entities"))
    s.status = "paused"
    save_run_state(conn, s)
    save_incident(conn, Incident(run_id="r1", node="synth", status="deviation", severity="warning"))
    return s


def test_list_runs_and_format(canon_conn):
    _seed(canon_conn)
    runs = list_runs(canon_conn)
    assert runs and runs[0]["run_id"] == "r1"
    text = monitor.format_run_list(runs)
    assert "r1" in text and "paused" in text


def test_format_run_detail(canon_conn):
    _seed(canon_conn)
    from pipeline.orchestration import load_run
    text = monitor.format_run_detail(load_run(canon_conn, "r1"))
    assert "synth" in text
    assert "0 entities" in text
    assert "Инциденты" in text


def test_open_incidents_and_resolution(canon_conn):
    _seed(canon_conn)
    inc = open_incidents(canon_conn)
    assert len(inc) == 1
    iid = inc[0]["id"]
    text = monitor.format_incident_list(inc)
    assert "synth" in text
    # подтверждение/отклонение убирает из открытых
    set_incident_resolution(canon_conn, iid, "rejected")
    assert open_incidents(canon_conn) == []


def test_format_empty():
    assert "не найден" in monitor.format_run_list([]).lower()
    assert monitor.format_run_detail(None) == "Прогон не найден."
    assert "нет" in monitor.format_incident_list([]).lower()
