"""Каноническая схема Mathesis (ТЗ Этап 2.1) — единый источник истины.

Принципиальные решения:
  * Ось знаний строго бинарна: `entities.type ∈ {def, prop}` — зеркало Lean
    (def / prop-theorem). Отдельного вида `axiom` НЕТ; аксиомы вносятся как `def`
    или `prop`, а «постулируется без доказательства» выражается через
    `lean_decl='axiom'`.
  * Схема — НАДМНОЖЕСТВО прежней «плоской» (`entities` сохраняет имя и все старые
    колонки), поэтому существующие читатели/писатели не ломаются, а типизированный
    слой `mathesis/` видит обогащённую модель.
  * Канонические таблицы и staging (черновики экстракции) собраны в одном месте.

Версионирование: `schema_meta.value WHERE key='version'`. Меняя схему —
поднимай SCHEMA_VERSION и добавляй миграцию.
"""
from __future__ import annotations

SCHEMA_VERSION = 2

# Допустимые значения (используются и кодом, и в CHECK-ограничениях).
KINDS = ("def", "prop")
LEAN_DECLS = ("def", "abbrev", "structure", "class", "instance", "theorem", "lemma", "axiom")
LEAN_STATUSES = ("unvalidated", "valid", "sorry", "failed")
DEP_ROLES = ("uses", "generalizes", "instance_of", "proof_uses", "component")

# --- Канонические таблицы ----------------------------------------------------
CANONICAL_SQL = """
PRAGMA foreign_keys = ON;

-- Единая таблица сущностей. type = ось Lean (def|prop).
CREATE TABLE IF NOT EXISTS entities (
    entity_id   TEXT PRIMARY KEY,
    type        TEXT NOT NULL CHECK (type IN ('def','prop')),
    title       TEXT NOT NULL,
    path        TEXT,                       -- директория .tex (легаси-поле)
    file_path   TEXT,                       -- относительный путь .tex
    lean_path   TEXT,                       -- путь валидированного .lean
    nl_desc     TEXT,                       -- описание на естественном языке
    module      TEXT,                       -- раздел математики
    latex       TEXT,                       -- канонический формальный LaTeX
    lean_code   TEXT,                       -- сгенерированный Lean 4
    lean_decl   TEXT,                        -- форма Lean-декларации (вкл. 'axiom')
    lean_status TEXT NOT NULL DEFAULT 'unvalidated'
                CHECK (lean_status IN ('unvalidated','valid','sorry','failed')),
    embedding   BLOB,
    created_at  TEXT,
    updated_at  TEXT
);

-- Мультиязычные алиасы для O(1) разрешения сущностей.
CREATE TABLE IF NOT EXISTS alias (
    alias     TEXT PRIMARY KEY,
    entity_id TEXT NOT NULL REFERENCES entities(entity_id) ON DELETE CASCADE
);

-- Провенанс: из каких источников/страниц извлечена сущность.
CREATE TABLE IF NOT EXISTS formulation_sources (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    entity_id   TEXT NOT NULL REFERENCES entities(entity_id) ON DELETE CASCADE,
    source_book TEXT NOT NULL,
    page_info   TEXT
);

-- Типизированный граф зависимостей (сворачивает прежние junction-таблицы).
CREATE TABLE IF NOT EXISTS entity_dependency (
    source_id  TEXT NOT NULL REFERENCES entities(entity_id) ON DELETE CASCADE,
    target_id  TEXT NOT NULL REFERENCES entities(entity_id) ON DELETE CASCADE,
    role       TEXT NOT NULL DEFAULT 'uses'
               CHECK (role IN ('uses','generalizes','instance_of','proof_uses','component')),
    proof_step TEXT,
    PRIMARY KEY (source_id, target_id, role)
);

-- Симметричные эквивалентности (хранится в каноническом порядке a < b).
CREATE TABLE IF NOT EXISTS equivalence (
    entity_a_id TEXT NOT NULL REFERENCES entities(entity_id) ON DELETE CASCADE,
    entity_b_id TEXT NOT NULL REFERENCES entities(entity_id) ON DELETE CASCADE,
    proof_id    TEXT REFERENCES entities(entity_id),
    PRIMARY KEY (entity_a_id, entity_b_id),
    CHECK (entity_a_id < entity_b_id)
);

-- Полнотекстовый поиск (FTS5). entity_id/type — UNINDEXED (только хранение).
CREATE VIRTUAL TABLE IF NOT EXISTS entity_fts USING fts5(
    entity_id UNINDEXED,
    type      UNINDEXED,
    title,
    nl_desc,
    latex,
    tokenize = 'unicode61'
);

-- Индексы под частые запросы.
CREATE INDEX IF NOT EXISTS idx_entities_type   ON entities(type);
CREATE INDEX IF NOT EXISTS idx_entities_module ON entities(module);
CREATE INDEX IF NOT EXISTS idx_dep_target      ON entity_dependency(target_id);
CREATE INDEX IF NOT EXISTS idx_alias_entity    ON alias(entity_id);
CREATE INDEX IF NOT EXISTS idx_src_entity      ON formulation_sources(entity_id);
"""

# --- Staging (черновики экстракции; можно очищать без потери канона) ----------
STAGING_SQL = """
-- Сырые формулировки, извлечённые из учебников до синтеза.
CREATE TABLE IF NOT EXISTS formulation_raw_cache (
    id              INTEGER PRIMARY KEY AUTOINCREMENT,
    discipline      TEXT,
    source_book     TEXT NOT NULL,
    raw_text        TEXT NOT NULL,
    entity_type     TEXT DEFAULT 'definition',
    has_proof       INTEGER DEFAULT 0,
    page_ref        INTEGER,
    raw_deps        TEXT,
    temp_cluster_id TEXT,
    embedding       BLOB
);

-- Сопоставление кластера черновиков -> промоутнутая сущность.
CREATE TABLE IF NOT EXISTS cluster_entity_map (
    cluster_id TEXT PRIMARY KEY,
    entity_id  TEXT
);

-- Очередь нерешённых рёбер (зависимость, для которой ещё нет сущности-цели).
CREATE TABLE IF NOT EXISTS pending_edges (
    source_id TEXT,
    raw_dep   TEXT,
    status    TEXT DEFAULT 'pending'
);
"""

META_SQL = """
CREATE TABLE IF NOT EXISTS schema_meta (
    key   TEXT PRIMARY KEY,
    value TEXT
);
"""

SCHEMA_SQL = CANONICAL_SQL + STAGING_SQL + META_SQL


def all_table_names() -> list[str]:
    """Имена всех таблиц схемы (для пересоздания/сброса)."""
    return [
        "entity_fts", "alias", "formulation_sources", "entity_dependency",
        "equivalence", "entities",
        "formulation_raw_cache", "cluster_entity_map", "pending_edges",
        "schema_meta",
    ]
