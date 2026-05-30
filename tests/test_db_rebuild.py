"""Тесты пересборки канонической БД из content/ (ТЗ Этап 2.3)."""
from __future__ import annotations

import sys
import types

import pytest

# actualize_db импортирует ollama опционально; на всякий случай заглушка.
sys.modules.setdefault("ollama", types.ModuleType("ollama"))

from mathesis import db as mdb  # noqa: E402
from mathesis import repo  # noqa: E402
from pipeline import actualize_db, config  # noqa: E402


def test_get_db_path_env_override(monkeypatch):
    monkeypatch.setenv("MATHESIS_DB_PATH", "/tmp/custom.db")
    assert config.get_db_path() == "/tmp/custom.db"
    monkeypatch.delenv("MATHESIS_DB_PATH")
    assert config.get_db_path().endswith("mathesis_index.db")


@pytest.fixture
def mini_content(tmp_path, monkeypatch):
    content = tmp_path / "content"
    (content / "defs").mkdir(parents=True)
    (content / "props").mkdir(parents=True)
    (content / "defs" / "Base [def-base].tex").write_text(
        "% entity-id: def-base\n% entity-type: def\n% name-ru: Базовое множество\n"
        "\\textbf{Описание:} непустое множество\n\\begin{definition}[def-base]\nX\n\\end{definition}\n",
        encoding="utf-8",
    )
    (content / "props" / "Thm [prop-thm].tex").write_text(
        "% entity-id: prop-thm\n% entity-type: prop\n% name-ru: Теорема о непрерывности\n"
        "\\textbf{Описание:} использует macro{def-base}\n\\begin{proposition}[prop-thm]\nY\n\\end{proposition}\n",
        encoding="utf-8",
    )
    monkeypatch.setattr(actualize_db, "CONTENT_DIR", content)
    return content


def test_rebuild_populates_canonical_db(mini_content, tmp_path):
    db_file = tmp_path / "db" / "out.db"
    stats = actualize_db.rebuild(compute_embeddings=False, db_path=str(db_file))
    assert stats["entities"] == 2
    assert stats["deps"] == 1

    conn = mdb.connect(str(db_file))
    try:
        assert mdb.get_schema_version(conn) == 2
        ids = {e.id for e in repo.list_entities(conn)}
        assert ids == {"def-base", "prop-thm"}
        # Тип корректен
        assert repo.get_entity(conn, "def-base").kind == "def"
        assert repo.get_entity(conn, "prop-thm").kind == "prop"
        # Зависимость prop-thm -> def-base записана
        deps = repo.get_dependencies(conn, "prop-thm")
        assert [d.id for d in deps] == ["def-base"]
        # FTS наполнен (поиск по описанию работает)
        res = repo.search(conn, "непрерывности")
        assert any(r.id == "prop-thm" for r in res)
    finally:
        conn.close()
