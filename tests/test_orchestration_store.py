"""Тесты персистенции прогонов/инцидентов (ТЗ Этап 5.1)."""
from __future__ import annotations

from pipeline.nodes import NodeResult, NodeStatus
from pipeline.orchestration.incidents import Incident, PatchPlan
from pipeline.orchestration.state import RunState
from pipeline.orchestration.store import load_run, save_incident, save_run_state


def _state_with_events(run_id="r1"):
    s = RunState(run_id=run_id)
    s.record_start("extract")
    s.record_result("extract", NodeResult(NodeStatus.OK, metrics={"t": 1.0}))
    s.record_start("synth")
    s.record_result("synth", NodeResult(NodeStatus.DEVIATION, message="0 entities"))
    s.status = "paused"
    return s


def test_save_and_load_run(canon_conn):
    s = _state_with_events()
    save_run_state(canon_conn, s)
    loaded = load_run(canon_conn, "r1")
    assert loaded is not None
    assert loaded["status"] == "paused"
    assert loaded["health"]["deviations"] == 1
    # события сохранены (start+result для двух узлов = 4)
    assert len(loaded["events"]) == 4
    assert loaded["created_at"] and loaded["updated_at"]


def test_save_run_state_idempotent(canon_conn):
    s = _state_with_events()
    save_run_state(canon_conn, s)
    created_first = load_run(canon_conn, "r1")["created_at"]
    save_run_state(canon_conn, s)  # повторно
    loaded = load_run(canon_conn, "r1")
    assert len(loaded["events"]) == 4          # не задвоилось
    assert loaded["created_at"] == created_first  # created_at сохранён


def test_save_incident_with_plan(canon_conn):
    save_run_state(canon_conn, RunState(run_id="r2", status="paused"))
    inc = Incident(run_id="r2", node="synth", status="deviation", severity="warning",
                   signals=["missing_dep:x"], message="bad")
    plan = PatchPlan(summary="fix synth", risk="low")
    save_incident(canon_conn, inc, patch_plan=plan, resolution="open")
    loaded = load_run(canon_conn, "r2")
    assert len(loaded["incidents"]) == 1
    assert loaded["incidents"][0]["node"] == "synth"
    assert loaded["incidents"][0]["resolution"] == "open"


def test_load_missing_run_returns_none(canon_conn):
    assert load_run(canon_conn, "nope") is None
