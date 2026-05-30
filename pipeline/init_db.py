"""Инициализация БД — тонкая обёртка над канонической схемой (ТЗ Этап 2.3).

Схема определена в `mathesis/schema.py` (единый источник истины). Здесь только
создаём её по пути из `pipeline.config.get_db_path()`. Имена `init_db`/`DB_PATH`
сохранены ради обратной совместимости со старыми импортами.
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from mathesis import db as _db  # noqa: E402  (импорт после настройки sys.path)
from pipeline.config import get_db_path  # noqa: E402

DB_PATH = get_db_path()


def init_db(db_path: str | None = None) -> str:
    """Создаёт каноническую + staging схему (idempotent). Возвращает путь к БД."""
    path = db_path or get_db_path()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    conn = _db.connect(path)
    try:
        _db.init_schema(conn)
    finally:
        conn.close()
    print(f"Database initialized at {path}")
    return path


if __name__ == "__main__":
    init_db()
