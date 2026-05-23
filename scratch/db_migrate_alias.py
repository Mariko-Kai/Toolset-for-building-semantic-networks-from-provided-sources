import sqlite3
import sys
from pathlib import Path

def migrate():
    db_path = Path(r"f:\Universe\Projects\Учебник по матанализу\mathesis_index.db")
    if not db_path.exists():
        print(f"Error: {db_path} not found.")
        sys.exit(1)
        
    conn = sqlite3.connect(db_path)
    try:
        # Create alias_registry table
        conn.execute("""
            CREATE TABLE IF NOT EXISTS alias_registry (
                alias TEXT PRIMARY KEY,
                entity_id TEXT NOT NULL
            );
        """)
        
        # Populate with existing aliases if needed (we can parse JSON aliases from object, property, operation)
        for table in ["object", "property", "operation"]:
            rows = conn.execute(f"SELECT id, aliases FROM {table}").fetchall()
            import json
            for row in rows:
                entity_id = row[0]
                aliases_json = row[1]
                if aliases_json:
                    try:
                        aliases = json.loads(aliases_json)
                        for alias in aliases:
                            conn.execute("INSERT OR IGNORE INTO alias_registry (alias, entity_id) VALUES (?, ?)", (alias.lower().strip(), entity_id))
                    except Exception as e:
                        print(f"Failed to parse aliases for {entity_id}: {e}")
        
        conn.commit()
        print("Migration successful: alias_registry created and populated.")
    except Exception as e:
        print(f"Migration failed: {e}")
        conn.rollback()
    finally:
        conn.close()

if __name__ == "__main__":
    migrate()
