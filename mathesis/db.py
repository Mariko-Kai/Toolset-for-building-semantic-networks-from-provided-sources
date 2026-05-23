"""Database management for mathesis.

Handles connection lifecycle, schema initialization, and low-level operations.
All public functions work with plain sqlite3 connections (sync).
"""

import sqlite3
from pathlib import Path

SCHEMA_SQL = """
PRAGMA foreign_keys = ON;
PRAGMA journal_mode = WAL;

-- === CORE ENTITIES ===

CREATE TABLE IF NOT EXISTS axiom (
    id        TEXT PRIMARY KEY,
    name      TEXT NOT NULL,
    system    TEXT NOT NULL,
    statement TEXT NOT NULL,
    file_path TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS object (
    id                TEXT PRIMARY KEY,
    name              TEXT NOT NULL,
    aliases           TEXT DEFAULT '[]',
    module            TEXT NOT NULL DEFAULT '',
    formal_definition TEXT NOT NULL DEFAULT '',
    intuition         TEXT DEFAULT '',
    file_path         TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS property (
    id                TEXT PRIMARY KEY,
    name              TEXT NOT NULL,
    aliases           TEXT DEFAULT '[]',
    module            TEXT NOT NULL DEFAULT '',
    formal_definition TEXT NOT NULL DEFAULT '',
    equivalent_forms  TEXT DEFAULT '',
    file_path         TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS operation (
    id                TEXT PRIMARY KEY,
    name              TEXT NOT NULL,
    aliases           TEXT DEFAULT '[]',
    module            TEXT NOT NULL DEFAULT '',
    arity             INTEGER NOT NULL DEFAULT 1,
    formal_definition TEXT NOT NULL DEFAULT '',
    codomain_id       TEXT REFERENCES object(id),
    file_path         TEXT NOT NULL DEFAULT ''
);

CREATE TABLE IF NOT EXISTS theorem (
    id                TEXT PRIMARY KEY,
    name              TEXT NOT NULL,
    subtype           TEXT NOT NULL DEFAULT 'theorem'
                      CHECK (subtype IN ('theorem', 'lemma')),
    parent_theorem_id TEXT REFERENCES theorem(id),
    module            TEXT NOT NULL DEFAULT '',
    statement         TEXT NOT NULL DEFAULT '',
    proof             TEXT NOT NULL DEFAULT '',
    strategy          TEXT DEFAULT '',
    file_path         TEXT NOT NULL DEFAULT '',
    CHECK (
        (subtype = 'lemma' AND parent_theorem_id IS NOT NULL) OR
        (subtype = 'theorem' AND parent_theorem_id IS NULL)
    )
);

-- === JUNCTION / RELATIONSHIP TABLES ===

CREATE TABLE IF NOT EXISTS object_property (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    object_id   TEXT NOT NULL REFERENCES object(id),
    property_id TEXT NOT NULL REFERENCES property(id),
    context     TEXT,
    context_ref TEXT REFERENCES object(id)
);

CREATE TABLE IF NOT EXISTS operation_argument (
    operation_id TEXT NOT NULL REFERENCES operation(id),
    position     INTEGER NOT NULL,
    object_id    TEXT NOT NULL REFERENCES object(id),
    role         TEXT DEFAULT 'operand',
    PRIMARY KEY (operation_id, position)
);

CREATE TABLE IF NOT EXISTS theorem_object (
    theorem_id TEXT NOT NULL REFERENCES theorem(id),
    object_id  TEXT NOT NULL REFERENCES object(id),
    PRIMARY KEY (theorem_id, object_id)
);

CREATE TABLE IF NOT EXISTS theorem_property (
    theorem_id  TEXT NOT NULL REFERENCES theorem(id),
    property_id TEXT NOT NULL REFERENCES property(id),
    PRIMARY KEY (theorem_id, property_id)
);

CREATE TABLE IF NOT EXISTS theorem_operation (
    theorem_id   TEXT NOT NULL REFERENCES theorem(id),
    operation_id TEXT NOT NULL REFERENCES operation(id),
    PRIMARY KEY (theorem_id, operation_id)
);

CREATE TABLE IF NOT EXISTS theorem_axiom (
    theorem_id TEXT NOT NULL REFERENCES theorem(id),
    axiom_id   TEXT NOT NULL REFERENCES axiom(id),
    PRIMARY KEY (theorem_id, axiom_id)
);

-- === EDGE CASE TABLES ===

CREATE TABLE IF NOT EXISTS theorem_dependency (
    theorem_id  TEXT NOT NULL REFERENCES theorem(id),
    used_thm_id TEXT NOT NULL REFERENCES theorem(id),
    proof_step  TEXT DEFAULT '',
    PRIMARY KEY (theorem_id, used_thm_id)
);

CREATE TABLE IF NOT EXISTS equivalence (
    entity_a_id TEXT NOT NULL,
    entity_b_id TEXT NOT NULL,
    proof_id    TEXT REFERENCES theorem(id),
    PRIMARY KEY (entity_a_id, entity_b_id),
    CHECK (entity_a_id < entity_b_id)
);

CREATE TABLE IF NOT EXISTS object_composition (
    container_id TEXT NOT NULL REFERENCES object(id),
    obj_comp_id  TEXT REFERENCES object(id),
    prop_comp_id TEXT REFERENCES property(id),
    op_comp_id   TEXT REFERENCES operation(id),
    role         TEXT NOT NULL,
    CHECK (
        (obj_comp_id  IS NOT NULL) +
        (prop_comp_id IS NOT NULL) +
        (op_comp_id   IS NOT NULL) = 1
    )
);

-- === ALIAS REGISTRY ===

CREATE TABLE IF NOT EXISTS alias_registry (
    alias TEXT PRIMARY KEY,
    entity_id TEXT NOT NULL
);

-- === FULL-TEXT SEARCH ===

CREATE VIRTUAL TABLE IF NOT EXISTS entity_fts USING fts5(
    entity_id,
    entity_type,
    name,
    content,
    tokenize='unicode61'
);
"""


def connect(db_path: str) -> sqlite3.Connection:
    """Open a connection with correct pragmas enabled."""
    conn = sqlite3.connect(db_path)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    try:
        conn.execute("PRAGMA journal_mode = WAL")
    except sqlite3.OperationalError:
        # WAL may fail on NTFS mounts from WSL — fall back to default
        pass
    return conn


def init_schema(conn: sqlite3.Connection) -> None:
    """Create all tables if they don't exist."""
    conn.executescript(SCHEMA_SQL)
    conn.commit()


def reset_db(conn: sqlite3.Connection) -> None:
    """Drop all tables and recreate (for reindexing)."""
    tables = [
        "entity_fts", "alias_registry",
        "object_composition", "equivalence", "theorem_dependency",
        "theorem_axiom", "theorem_operation", "theorem_property",
        "theorem_object", "operation_argument", "object_property",
        "theorem", "operation", "property", "object", "axiom",
    ]
    for table in tables:
        conn.execute(f"DROP TABLE IF EXISTS {table}")
    conn.commit()
    init_schema(conn)
