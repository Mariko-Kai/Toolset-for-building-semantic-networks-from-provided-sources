import os
import re
import sys
import sqlite3
import struct
from pathlib import Path

# Попробуем импортировать ollama для генерации эмбеддингов
try:
    import ollama
    HAS_OLLAMA = True
except ImportError:
    HAS_OLLAMA = False
    print("[WARN] Модуль ollama не найден. Векторные эмбеддинги не будут сгенерированы.")

# Настройки путей
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(PROJECT_ROOT))
DB_PATH = PROJECT_ROOT / "db/mathesis_index.db"
CONTENT_DIR = PROJECT_ROOT / "content"

# Модель для эмбеддингов по умолчанию (совместимая с Shift Left)
EMBED_MODEL = "nomic-embed-text:latest"

try:
    from pipeline.init_db import init_db
except ImportError:
    from init_db import init_db

def clean_latex(text: str) -> str:
    """Удаляет мусорные теги из LaTeX для чистого сохранения текста в БД."""
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
    """Сбрасывает все таблицы, уничтожая старые висячие записи."""
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
    Ищет макросы \macro{entity-id} для построения графа зависимостей.
    """
    deps = set()
    matches = re.findall(r'macro\{([^}]+)\}', content)
    for m in matches:
        deps.add(m)
    return list(deps)

def get_binary_embedding(text: str) -> bytes:
    """Генерирует векторный эмбеддинг и упаковывает в бинарный BLOB (struct)."""
    if not HAS_OLLAMA or not text.strip():
        return None
    try:
        response = ollama.embeddings(model=EMBED_MODEL, prompt=text)
        emb = response.get('embedding')
        if emb:
            return struct.pack(f"{len(emb)}f", *emb)
    except Exception as e:
        print(f"  [ERROR] Не удалось сгенерировать эмбеддинг: {e}")
    return None

def main():
    print(f"=== Актуализация базы данных Mathesis ===")
    print(f"Путь БД: {DB_PATH}")
    
    # 1. Очистка старой базы данных (сброс таблиц)
    conn = sqlite3.connect(DB_PATH)
    drop_all_tables(conn)
    conn.close()
    
    # 2. Инициализация актуальной схемы
    init_db()
    
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    entity_files = {}
    processed_ids = set()
    
    # 3. Парсинг директории content/
    for root, dirs, files in os.walk(CONTENT_DIR):
        for file in files:
            if not file.endswith(".tex") or file in ("master.tex", "mathesis.sty", "TEMPLATE.tex"):
                continue
                
            filepath = Path(root) / file
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()
                
            # Идентификатор сущности
            id_match = re.search(r'% entity-id:\s*(.*)', content)
            if not id_match:
                fn_match = re.search(r'\[([^\]]+)\]\.tex$', file)
                entity_id = fn_match.group(1).strip() if fn_match else None
            else:
                entity_id = id_match.group(1).strip()
                
            if not entity_id or entity_id in processed_ids:
                continue
                
            # Тип сущности (def / prop)
            type_match = re.search(r'% entity-type:\s*(.*)', content)
            if type_match:
                entity_type = type_match.group(1).strip().lower()
                if entity_type not in ('def', 'prop'):
                    entity_type = 'def' if entity_id.startswith('def') else 'prop'
            else:
                entity_type = 'def' if entity_id.startswith('def') else 'prop'
                
            # Имя (предпочтительно русское name-ru, иначе из title)
            name_match = re.search(r'% name-ru:\s*(.*)', content)
            if name_match:
                name = name_match.group(1).strip()
            else:
                sec_match = re.search(r'\\section\{([^}]+)\}', content)
                if sec_match:
                    name = sec_match.group(1).strip()
                else:
                    env_match = re.search(r'\\begin\{(?:definition|proposition)\}\[([^\]]+)\]', content)
                    if env_match:
                        name = env_match.group(1).strip()
                    else:
                        name = entity_id
                        
            # Описание (Описание:)
            desc_match = re.search(r'\\textbf\{Описание:\}\s*(.*?)(?=\\begin\{|\Z)', content, re.DOTALL)
            nl_desc = clean_latex(desc_match.group(1).strip()) if desc_match else ""
            
            # Генерация векторного эмбеддинга для Shift-Left поиска
            print(f"  [{entity_type}] Чтение: {entity_id} ...", end="", flush=True)
            search_text = f"{name}\n{nl_desc}".strip()
            emb_blob = get_binary_embedding(search_text)
            
            rel_path = str(filepath.relative_to(PROJECT_ROOT))
            entity_files[entity_id] = (filepath, content)
            processed_ids.add(entity_id)
            
            # Вставка в БД
            cursor.execute(
                """
                INSERT INTO entities (entity_id, type, title, path, file_path, nl_desc, embedding)
                VALUES (?, ?, ?, ?, ?, ?, ?)
                """,
                (entity_id, entity_type, name, str(filepath.parent), rel_path, nl_desc, emb_blob)
            )
            print(" ОК (С эмбеддингом)" if emb_blob else " ОК (БЕЗ ЭМБЕДДИНГА)")
            
    # 4. Обновление графа зависимостей
    print("\n--- Построение графа зависимостей ---")
    for entity_id, (filepath, content) in entity_files.items():
        deps = extract_dependencies(content)
        for dep_id in deps:
            if dep_id == entity_id:
                continue
            if dep_id in processed_ids:
                try:
                    cursor.execute(
                        "INSERT INTO entity_dependency (source_id, target_id) VALUES (?, ?)",
                        (entity_id, dep_id)
                    )
                except sqlite3.IntegrityError:
                    pass
            else:
                print(f"  [WARN] Сущность {entity_id} ссылается на неизвестную/висячую {dep_id}")
                
    conn.commit()
    conn.close()
    print("\nАктуализация базы данных успешно завершена. Все висячие записи удалены, все существующие файлы проиндексированы.")

if __name__ == "__main__":
    main()
