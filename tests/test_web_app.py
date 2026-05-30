"""Тесты web-роутов на канонической модели (ТЗ Этап 2.5)."""
from __future__ import annotations

import pytest

pytest.importorskip("httpx")  # нужен для TestClient


@pytest.fixture
def web_client(tmp_path, monkeypatch):
    db_file = tmp_path / "web.db"
    monkeypatch.setenv("MATHESIS_DB_PATH", str(db_file))

    # Сидируем каноническую БД до импорта web.app.
    from mathesis import db as mdb
    from mathesis import repo
    from mathesis.models import Dependency, Entity
    conn = mdb.connect(str(db_file))
    mdb.init_schema(conn)
    repo.upsert_entity(conn, Entity(id="def-x", kind="def", title="Объект Икс",
                                    nl_desc="описание объекта", latex=r"\mathbb{X}",
                                    aliases=["X"]))
    repo.upsert_entity(conn, Entity(id="prop-y", kind="prop", title="Утверждение Игрек"))
    repo.add_dependency(conn, Dependency("prop-y", "def-x"))
    # Сидируем прогон и инцидент для монитора.
    from pipeline.nodes import NodeResult, NodeStatus
    from pipeline.orchestration.incidents import Incident
    from pipeline.orchestration.state import RunState
    from pipeline.orchestration.store import save_incident, save_run_state
    st = RunState(run_id="run-1")
    st.record_start("synth")
    st.record_result("synth", NodeResult(NodeStatus.DEVIATION, message="0 entities"))
    st.status = "paused"
    save_run_state(conn, st)
    save_incident(conn, Incident(run_id="run-1", node="synth", status="deviation", severity="warning"))
    conn.close()

    import web.app as webapp
    # Не даём startup писать api_config.json и поднимать публичный Cloudflare-туннель.
    monkeypatch.setattr(webapp, "load_or_create_api_config", lambda: {})
    monkeypatch.setattr(webapp, "start_cloudflare_tunnel", lambda: None)

    from fastapi.testclient import TestClient
    with TestClient(webapp.app) as client:
        yield client


def test_entity_page_renders(web_client):
    r = web_client.get("/entity/def-x")
    assert r.status_code == 200
    assert "Объект Икс" in r.text
    assert "описание объекта" in r.text


def test_entity_dependency_and_backlink(web_client):
    # prop-y зависит от def-x -> ссылка на def-x на странице prop-y
    r = web_client.get("/entity/prop-y")
    assert r.status_code == 200
    assert "/entity/def-x" in r.text
    # обратная ссылка: на странице def-x видно, что его использует prop-y
    r2 = web_client.get("/entity/def-x")
    assert "/entity/prop-y" in r2.text


def test_legacy_paths_still_work(web_client):
    assert web_client.get("/objects/def-x").status_code == 200
    assert web_client.get("/properties/prop-y").status_code == 200


def test_missing_entity_404(web_client):
    assert web_client.get("/entity/does-not-exist").status_code == 404


def test_catalog_and_index_ok(web_client):
    assert web_client.get("/catalog").status_code == 200
    assert web_client.get("/").status_code == 200


def test_monitor_page_lists_run(web_client):
    r = web_client.get("/monitor")
    assert r.status_code == 200
    assert "run-1" in r.text
    assert "synth" in r.text  # открытый инцидент


def test_monitor_run_detail(web_client):
    r = web_client.get("/monitor/run-1")
    assert r.status_code == 200
    assert "0 entities" in r.text
    assert web_client.get("/monitor/missing").status_code == 404


def test_api_runs_and_resolve(web_client):
    data = web_client.get("/api/runs").json()
    assert any(run["run_id"] == "run-1" for run in data["runs"])
    detail = web_client.get("/api/runs/run-1").json()
    assert detail["status"] == "paused"
    assert len(detail["incidents"]) == 1
    iid = detail["incidents"][0]["id"]
    resp = web_client.post(f"/api/incidents/{iid}/resolve?resolution=confirmed")
    assert resp.status_code == 200
    # инцидент больше не «открыт» -> на странице монитора его нет
    assert "Открытых инцидентов нет" in web_client.get("/monitor").text
