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
