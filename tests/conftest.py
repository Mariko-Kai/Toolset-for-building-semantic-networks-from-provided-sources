"""Общие фикстуры для тестов Mathesis.

Главный принцип: тесты НЕ обращаются к реальным LLM/Lean/сети. Для LLM есть
детерминированный `FakeModelManager`. Для БД — временная SQLite со схемой,
повторяющей текущую (entities-based) модель конвейера.

Схема здесь намеренно автономна (не импортирует pipeline.init_db с его
захардкоженным путём). На Этапе 2 она будет заменена на каноническую.
"""
from __future__ import annotations

import hashlib
import sqlite3
import sys
from pathlib import Path

import pytest

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


# --- Схема текущей (entities) модели, зеркало pipeline/init_db.py ------------
_SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS entities (
    entity_id TEXT PRIMARY KEY,
    type TEXT NOT NULL,
    title TEXT NOT NULL,
    path TEXT NOT NULL,
    file_path TEXT,
    lean_path TEXT,
    nl_desc TEXT,
    embedding BLOB
);
CREATE TABLE IF NOT EXISTS formulation_sources (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_id TEXT NOT NULL,
    source_book TEXT NOT NULL,
    page_info TEXT,
    FOREIGN KEY (entity_id) REFERENCES entities(entity_id)
);
CREATE TABLE IF NOT EXISTS entity_dependency (
    source_id TEXT,
    target_id TEXT,
    PRIMARY KEY (source_id, target_id),
    FOREIGN KEY (source_id) REFERENCES entities(entity_id),
    FOREIGN KEY (target_id) REFERENCES entities(entity_id)
);
"""


@pytest.fixture
def tmp_db(tmp_path) -> Path:
    """Создаёт временную БД со схемой entities и возвращает путь к файлу."""
    db_path = tmp_path / "test.db"
    conn = sqlite3.connect(db_path)
    try:
        conn.executescript(_SCHEMA_SQL)
        conn.commit()
    finally:
        conn.close()
    return db_path


@pytest.fixture
def sample_content(tmp_path) -> Path:
    """Каталог с парой минимальных .tex для парсинга зависимостей/макросов."""
    content = tmp_path / "content"
    content.mkdir()
    (content / "limit.tex").write_text(
        "% entity-id: def-limit\n"
        "% macro: \\Limit\n"
        "% notation: \\lim\n"
        "% args: 0\n"
        "\\[ \\Limit f = L \\]\n",
        encoding="utf-8",
    )
    (content / "real.tex").write_text(
        "% entity-id: def-real-numbers\n"
        "% macro: \\RealNumbers\n"
        "% args: 0\n"
        "\\[ \\RealNumbers \\]\n",
        encoding="utf-8",
    )
    return content


class FakeModelManager:
    """Детерминированная замена ModelManager для тестов (без сети).

    Интерфейс совместим с pipeline.model_manager.ModelManager:
      - query_llm(prompt, ..., role=...) -> str
      - get_embedding(text, ..., role=...) -> list[float]

    Поведение настраивается:
      - responses: dict-маршрутизация по подстроке в промпте → ответ;
      - default_response: что вернуть, если ничего не совпало;
      - raise_on: если подстрока встречается в промпте — бросить RuntimeError
        (для проверки обработки ошибок);
      - calls: журнал вызовов для ассертов.
    """

    def __init__(self, responses=None, default_response="", raise_on=None, embed_dim=8):
        self.responses = responses or {}
        self.default_response = default_response
        self.raise_on = raise_on or []
        self.embed_dim = embed_dim
        self.calls: list[tuple[str, str]] = []

    def query_llm(self, prompt: str, model=None, json_mode=False, provider=None,
                  system_prompt=None, role=None, stream_callback=None) -> str:
        self.calls.append(("query_llm", prompt))
        for needle in self.raise_on:
            if needle in prompt:
                raise RuntimeError(f"FakeModelManager forced error on: {needle}")
        for needle, resp in self.responses.items():
            if needle in prompt:
                if stream_callback:
                    stream_callback(resp)
                return resp
        if stream_callback and self.default_response:
            stream_callback(self.default_response)
        return self.default_response

    def get_embedding(self, text: str, provider=None, model=None, role=None):
        self.calls.append(("get_embedding", text))
        # Детерминированный псевдо-эмбеддинг из хеша текста.
        h = hashlib.sha256(text.encode("utf-8")).digest()
        return [h[i % len(h)] / 255.0 for i in range(self.embed_dim)]


@pytest.fixture
def fake_mgr() -> FakeModelManager:
    return FakeModelManager()
