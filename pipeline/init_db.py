import sqlite3
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "mathesis_index.db"

def init_db():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Table for canonical entities
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS entities (
            entity_id TEXT PRIMARY KEY,
            type TEXT NOT NULL,
            title TEXT NOT NULL,
            path TEXT NOT NULL
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
            source_book TEXT,
            raw_text TEXT,
            embedding BLOB,
            temp_cluster_id TEXT
        )
    """)

    conn.commit()
    conn.close()
    print(f"Database initialized at {DB_PATH}")

if __name__ == "__main__":
    init_db()
