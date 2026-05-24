import sqlite3
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "db/mathesis_index.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Table for canonical entities
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS entities (
            entity_id TEXT PRIMARY KEY,
            type TEXT NOT NULL,
            title TEXT NOT NULL,
            path TEXT NOT NULL,
            file_path TEXT,
            lean_path TEXT,
            nl_desc TEXT,
            embedding BLOB
        )
    """)

    # Table linking entities to multiple sources
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS formulation_sources (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            entity_id TEXT NOT NULL,
            source_book TEXT NOT NULL,
            page_info TEXT,
            FOREIGN KEY (entity_id) REFERENCES entities(entity_id)
        )
    """)

    # Temporary table for caching raw extracted texts and their embeddings
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS formulation_raw_cache (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            discipline TEXT,
            source_book TEXT NOT NULL,
            raw_text TEXT NOT NULL,
            entity_type TEXT DEFAULT 'definition',
            has_proof INTEGER DEFAULT 0,
            page_ref INTEGER,
            raw_deps TEXT,
            temp_cluster_id TEXT,
            embedding BLOB
        )
    """)

    # Table for entity dependencies
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS entity_dependency (
            source_id TEXT,
            target_id TEXT,
            PRIMARY KEY (source_id, target_id),
            FOREIGN KEY (source_id) REFERENCES entities(entity_id),
            FOREIGN KEY (target_id) REFERENCES entities(entity_id)
        )
    """)

    conn.commit()
    conn.close()
    print(f"Database initialized at {DB_PATH}")

if __name__ == "__main__":
    init_db()
