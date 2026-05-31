"""Управление подключением и жизненным циклом канонической схемы Mathesis.

Все публичные функции работают с обычным sqlite3.Connection (sync).
Сама схема определена в `mathesis/schema.py` — единый источник истины.
"""
from __future__ import annotations

import logging
import sqlite3

from .schema import SCHEMA_SQL, SCHEMA_VERSION

logger = logging.getLogger("mathesis.db")


def connect(db_path: str) -> sqlite3.Connection:
    """Открывает соединение с корректными pragma (FK + WAL)."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        mode = conn.execute("PRAGMA journal_mode = WAL").fetchone()
        # PRAGMA journal_mode возвращает фактический режим. На некоторых ФС
        # (NTFS-маунты из WSL, сетевые диски) WAL молча откатывается.
        actual = (mode[0] if mode else "").lower()
        if actual != "wal":
            logger.warning("journal_mode=WAL не применился, активен режим '%s' (ФС может не поддерживать WAL).", actual)
    except sqlite3.OperationalError as e:
        logger.warning("Не удалось установить journal_mode=WAL: %s. Используется режим по умолчанию.", e)
    return conn


_ENTITIES_MIGRATIONS: dict[str, str] = {
    "module": "TEXT",
    "latex": "TEXT",
    "lean_code": "TEXT",
    "lean_decl": "TEXT",
    "lean_status": (
        "TEXT NOT NULL DEFAULT 'unvalidated' "
        "CHECK (lean_status IN ('unvalidated','valid','sorry','failed'))"
    ),
    "created_at": "TEXT",
    "updated_at": "TEXT",
}


def _migrate_legacy_entities(conn: sqlite3.Connection) -> None:
    """Дотягивает «плоскую» legacy-таблицу entities до канона.

    `CREATE TABLE IF NOT EXISTS` не добавляет колонки к уже существующей таблице,
    поэтому на старых БД (без module/latex/lean_* и т.д.) последующий
    `CREATE INDEX ... ON entities(module)` падал с `no such column: module`.
    Идемпотентно добавляем недостающие колонки через ALTER TABLE.
    """
    exists = conn.execute(
        "SELECT 1 FROM sqlite_master WHERE type='table' AND name='entities'"
    ).fetchone()
    if not exists:
        return  # свежая БД — таблицу создаст executescript(SCHEMA_SQL)
    have = {row[1] for row in conn.execute("PRAGMA table_info(entities)")}
    for col, decl in _ENTITIES_MIGRATIONS.items():
        if col not in have:
            conn.execute(f"ALTER TABLE entities ADD COLUMN {col} {decl}")


def init_schema(conn: sqlite3.Connection) -> None:
    """Создаёт все таблицы (если отсутствуют) и фиксирует версию схемы."""
    _migrate_legacy_entities(conn)
    conn.executescript(SCHEMA_SQL)
    conn.execute(
        "INSERT OR REPLACE INTO schema_meta (key, value) VALUES ('version', ?)",
        (str(SCHEMA_VERSION),),
    )
    conn.commit()


def get_schema_version(conn: sqlite3.Connection) -> int | None:
    """Возвращает версию схемы из schema_meta или None, если её нет."""
    try:
        row = conn.execute("SELECT value FROM schema_meta WHERE key='version'").fetchone()
        return int(row[0]) if row and row[0] is not None else None
    except (sqlite3.OperationalError, ValueError, TypeError):
        return None


def reset_db(conn: sqlite3.Connection) -> None:
    """Удаляет ВСЕ пользовательские таблицы (в т.ч. остатки старой схемы) и
    пересоздаёт каноническую. FTS-таблицы дропаются первыми (вместе с их
    скрытыми shadow-таблицами)."""
    conn.execute("PRAGMA foreign_keys = OFF")
    rows = conn.execute("SELECT name, sql FROM sqlite_master WHERE type='table'").fetchall()

    def _drop(name: str) -> None:
        try:
            conn.execute(f'DROP TABLE IF EXISTS "{name}"')
        except sqlite3.OperationalError:
            pass

    # Сначала виртуальные FTS-таблицы (их shadow-таблицы нельзя дропать напрямую).
    for name, sql in rows:
        if name.startswith("sqlite_"):
            continue
        if sql and "fts" in sql.lower():
            _drop(name)
    # Затем всё остальное.
    for name, sql in rows:
        if name.startswith("sqlite_"):
            continue
        _drop(name)

    conn.commit()
    conn.execute("PRAGMA foreign_keys = ON")
    init_schema(conn)
