"""MathesisDB — единственная точка входа в ядро Mathesis (ТЗ Этап 2.2).

Тонкий фасад над `repo`/`validator` поверх канонической схемы (`Entity`,
kind ∈ {def, prop}). Транспортные слои (web, CLI) работают только с ним.
"""
from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Optional

from . import db, repo, validator
from .exceptions import EntityNotFoundError
from .models import (
    Dependency,
    Entity,
    SearchResult,
    Source,
    TraceNode,
    UsedByResult,
    ValidationReport,
)


class MathesisDB:
    """Фасад над канонической базой знаний."""

    def __init__(self, db_path: str, content_dir: str = ""):
        self._db_path = db_path
        self._content_dir = Path(content_dir) if content_dir else None
        self._conn: Optional[sqlite3.Connection] = None

    # --- Жизненный цикл соединения ---
    def connect(self) -> None:
        self._conn = db.connect(self._db_path)

    def close(self) -> None:
        if self._conn:
            self._conn.close()
            self._conn = None

    @property
    def conn(self) -> sqlite3.Connection:
        if self._conn is None:
            self.connect()
        return self._conn

    def __enter__(self) -> "MathesisDB":
        self.connect()
        return self

    def __exit__(self, exc_type, exc, tb) -> None:
        self.close()

    def init_db(self) -> None:
        db.init_schema(self.conn)

    def reset_db(self) -> None:
        db.reset_db(self.conn)

    def schema_version(self) -> Optional[int]:
        return db.get_schema_version(self.conn)

    # --- CRUD сущностей ---
    def get_entity(self, entity_id: str) -> Entity:
        entity = repo.get_entity(self.conn, entity_id)
        if entity is None:
            raise EntityNotFoundError("entity", entity_id)
        return entity

    def find_entity(self, entity_id: str) -> Optional[Entity]:
        """Как get_entity, но возвращает None вместо исключения."""
        return repo.get_entity(self.conn, entity_id)

    def list_entities(self, kind: Optional[str] = None,
                      module: Optional[str] = None) -> list[Entity]:
        return repo.list_entities(self.conn, kind, module)

    def upsert_entity(self, entity: Entity) -> Entity:
        return repo.upsert_entity(self.conn, entity)

    def delete_entity(self, entity_id: str) -> None:
        repo.delete_entity(self.conn, entity_id)

    def set_embedding(self, entity_id: str, blob: bytes) -> None:
        repo.set_embedding(self.conn, entity_id, blob)

    # --- Поиск и алиасы ---
    def search(self, query: str, kind: Optional[str] = None,
               limit: int = 50, offset: int = 0) -> list[SearchResult]:
        return repo.search(self.conn, query, kind, limit, offset)

    def reindex_fts(self) -> int:
        return repo.reindex_fts(self.conn)

    def lookup_alias(self, alias: str) -> Optional[str]:
        return repo.lookup_alias(self.conn, alias)

    # --- Провенанс ---
    def add_source(self, source: Source) -> None:
        repo.add_source(self.conn, source)

    def get_sources(self, entity_id: str) -> list[Source]:
        return repo.get_sources(self.conn, entity_id)

    # --- Граф зависимостей ---
    def add_dependency(self, source_id: str, target_id: str,
                       role: str = "uses", proof_step: str = "") -> None:
        repo.add_dependency(self.conn, Dependency(source_id, target_id, role, proof_step))

    def get_dependencies(self, entity_id: str) -> list[Entity]:
        return repo.get_dependencies(self.conn, entity_id)

    def get_used_by(self, entity_id: str) -> UsedByResult:
        return repo.get_used_by(self.conn, entity_id)

    def get_full_dag(self) -> list[Dependency]:
        return repo.get_full_dag(self.conn)

    def trace_to_roots(self, entity_id: str) -> list[TraceNode]:
        return repo.trace_to_roots(self.conn, entity_id)

    # --- Эквивалентности ---
    def add_equivalence(self, a_id: str, b_id: str, proof_id: Optional[str] = None) -> None:
        repo.add_equivalence(self.conn, a_id, b_id, proof_id)

    def get_equivalents(self, entity_id: str) -> list[str]:
        return repo.get_equivalents(self.conn, entity_id)

    # --- Каталог ---
    def list_modules(self) -> list[str]:
        return repo.list_modules(self.conn)

    # --- Валидация ---
    def validate(self) -> ValidationReport:
        return validator.validate(self.conn)
