import os
import re
import sys
import sqlite3
from pathlib import Path

# Adjust paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
DB_PATH = PROJECT_ROOT / "db/mathesis_index.db"
CONTENT_DIR = PROJECT_ROOT / "content"

# Ensure we use init_db from pipeline
try:
    from pipeline.init_db import init_db
except ImportError:
    # fallback if run from root
    from init_db import init_db

def clean_latex(text: str) -> str:
    if not text:
        return ""
    text = re.sub(r'\\label\{.*?\}', '', text)
    text = text.replace('\\\\varnothing', '\\varnothing')
    lines = []
    for line in text.split('\n'):
        parts = re.split(r'(?<!\\)%', line, maxsplit=1)
        clean_line = parts[0].strip()
        if clean_line:
            lines.append(clean_line)
    return '\n'.join(lines).strip()

def drop_all_tables(conn: sqlite3.Connection):
    """Drops all tables in the database to start completely fresh."""
    cursor = conn.cursor()
    cursor.execute("SELECT name FROM sqlite_master WHERE type='table';")
    tables = cursor.fetchall()
    for table_name in tables:
        name = table_name[0]
        if name != "sqlite_sequence":
            cursor.execute(f"DROP TABLE IF EXISTS {name}")
    conn.commit()

def extract_dependencies(content: str) -> list[str]:
    """
    Extracts dependencies by looking for semantic macros:
    macro{entity-id}{...} or \macro{entity-id} or whatever was used.
    Since we saw `macro{def-real-numbers}{\mathbb{R}}`, we'll parse `macro\{([^\}]+)\}`.
    Also we can parse `\SemanticMacro` if present.
    """
    deps = set()
    # Find macro{entity-id}{symbol}
    matches = re.findall(r'macro\{([^}]+)\}', content)
    for m in matches:
        deps.add(m)
        
    return list(deps)

def main():
    print(f"=== Reseeding Mathesis Database ===")
    print(f"DB Path: {DB_PATH}")
    
    # 1. Connect and drop tables
    conn = sqlite3.connect(DB_PATH)
    drop_all_tables(conn)
    conn.close()
    
    # 2. Reinitialize the schema (entities, entity_dependency, etc.)
    init_db()
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    # 3. Parse content files
    entity_types = {}
    entity_files = {}
    processed_ids = set()
    
    for root, dirs, files in os.walk(CONTENT_DIR):
        for file in files:
            if not file.endswith(".tex") or file in ("master.tex", "mathesis.sty", "TEMPLATE.tex"):
                continue
                
            filepath = Path(root) / file
            
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
                
            # Determine ID
            id_match = re.search(r'% entity-id:\s*(.*)', content)
            if not id_match:
                fn_match = re.search(r'\[([^\]]+)\]\.tex$', file)
                entity_id = fn_match.group(1).strip() if fn_match else None
            else:
                entity_id = id_match.group(1).strip()
                
            if not entity_id:
                continue
                
            if entity_id in processed_ids:
                print(f"  [!] Skipping duplicate entity {entity_id} from {filepath.name}")
                continue
                
            # Determine type (def or prop)
            type_match = re.search(r'% entity-type:\s*(.*)', content)
            if type_match:
                entity_type = type_match.group(1).strip().lower()
                if entity_type not in ('def', 'prop'):
                    entity_type = 'def' if entity_id.startswith('def') else 'prop'
            else:
                entity_type = 'def' if entity_id.startswith('def') else 'prop'
                
            # Name
            name_match = re.search(r'% name-ru:\s*(.*)', content)
            if name_match:
                name = name_match.group(1).strip()
            else:
                # Try \section
                sec_match = re.search(r'\\section\{([^}]+)\}', content)
                if sec_match:
                    name = sec_match.group(1).strip()
                else:
                    env_match = re.search(r'\\begin\{(?:definition|proposition)\}\[([^\]]+)\]', content)
                    if env_match:
                        name = env_match.group(1).strip()
                    else:
                        name = entity_id
                        
            # NL description (intuition)
            desc_match = re.search(r'\\textbf\{Описание:\}\s*(.*?)(?=\\begin\{|\Z)', content, re.DOTALL)
            intuition = clean_latex(desc_match.group(1).strip()) if desc_match else ""
            
            # Record
            rel_path = str(filepath.relative_to(PROJECT_ROOT))
            entity_types[entity_id] = entity_type
            entity_files[entity_id] = (filepath, content)
            processed_ids.add(entity_id)
            
            cursor.execute(
                """
                INSERT INTO entities (entity_id, type, title, path, file_path, nl_desc)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (entity_id, entity_type, name, str(filepath.parent), rel_path, intuition)
            )
            print(f"  Indexed [{entity_type}]: {entity_id}")
            
    # 4. Extract dependencies and insert
    print("\n--- Establishing Relationships ---")
    for entity_id, (filepath, content) in entity_files.items():
        deps = extract_dependencies(content)
        # Add to entity_dependency
        for dep_id in deps:
            if dep_id == entity_id:
                continue
            # Validate dep_id exists
            if dep_id in processed_ids:
                try:
                    cursor.execute(
                        "INSERT INTO entity_dependency (source_id, target_id) VALUES (?, ?)",
                        (entity_id, dep_id)
                    )
                except sqlite3.IntegrityError:
                    pass # Ignore duplicate edges
            else:
                print(f"  [WARN] {entity_id} depends on unknown entity '{dep_id}'")
                
    conn.commit()
    conn.close()
    print("Reseed complete! Database successfully populated.")

if __name__ == "__main__":
    main()
