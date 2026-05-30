"""Актуализация БД из content/*.tex (ТЗ Этап 2.3).

Пересобирает каноническую БД из файлов контента (источник истины). Пишет через
типизированный слой `mathesis.repo`, поэтому автоматически наполняются FTS-индекс,
алиасы и таймстемпы. `reseed_db.py` переиспользует `rebuild(compute_embeddings=False)`.
"""
from __future__ import annotations

import os
import re
import struct
import sys
from pathlib import Path

# Попробуем импортировать ollama для генерации эмбеддингов
try:
    import ollama
    HAS_OLLAMA = True
except ImportError:
    HAS_OLLAMA = False

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from mathesis import db as _db          # noqa: E402
from mathesis import repo               # noqa: E402
from mathesis.models import Dependency, Entity  # noqa: E402
from pipeline.config import get_db_path  # noqa: E402

CONTENT_DIR = PROJECT_ROOT / "content"
EMBED_MODEL = "nomic-embed-text:latest"
_SKIP_FILES = {"master.tex", "mathesis.sty", "mathesis_macros.sty", "TEMPLATE.tex"}


def clean_latex(text: str) -> str:
    """Удаляет служебные теги/комментарии из LaTeX для чистого nl_desc."""
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


def extract_dependencies(content: str) -> list[str]:
    """Ищет макросы macro{entity-id} для построения графа зависимостей."""
    return list({m for m in re.findall(r'macro\{([^}]+)\}', content)})


def get_binary_embedding(text: str):
    """Генерирует эмбеддинг и упаковывает в бинарный BLOB (struct)."""
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


def _parse_entity(filepath: Path, content: str):
    """Разбирает один .tex файл -> (entity_id, type, name, nl_desc) или None."""
    id_match = re.search(r'% entity-id:\s*(.*)', content)
    if id_match:
        entity_id = id_match.group(1).strip()
    else:
        fn_match = re.search(r'\[([^\]]+)\]\.tex$', filepath.name)
        entity_id = fn_match.group(1).strip() if fn_match else None
    if not entity_id:
        return None

    type_match = re.search(r'% entity-type:\s*(.*)', content)
    if type_match and type_match.group(1).strip().lower() in ('def', 'prop'):
        entity_type = type_match.group(1).strip().lower()
    else:
        entity_type = 'def' if entity_id.startswith('def') else 'prop'

    name_match = re.search(r'% name-ru:\s*(.*)', content)
    if name_match:
        name = name_match.group(1).strip()
    else:
        sec_match = re.search(r'\\section\{([^}]+)\}', content)
        env_match = re.search(r'\\begin\{(?:definition|proposition)\}\[([^\]]+)\]', content)
        if sec_match:
            name = sec_match.group(1).strip()
        elif env_match:
            name = env_match.group(1).strip()
        else:
            name = entity_id

    desc_match = re.search(r'\\textbf\{Описание:\}\s*(.*?)(?=\\begin\{|\Z)', content, re.DOTALL)
    nl_desc = clean_latex(desc_match.group(1).strip()) if desc_match else ""
    return entity_id, entity_type, name, nl_desc


def rebuild(compute_embeddings: bool = True, db_path: str | None = None) -> dict:
    """Полностью пересобирает каноническую БД из content/. Возвращает статистику."""
    path = db_path or get_db_path()
    Path(path).parent.mkdir(parents=True, exist_ok=True)
    print("=== Пересборка БД Mathesis ===")
    print(f"Путь БД: {path}")

    conn = _db.connect(path)
    try:
        _db.reset_db(conn)  # дроп всех таблиц + каноническая схема

        entity_files: dict[str, tuple] = {}
        processed: set[str] = set()
        stats = {"entities": 0, "deps": 0, "embeddings": 0, "dangling": 0}

        # 1) Сущности
        for root, _dirs, files in os.walk(CONTENT_DIR):
            for file in files:
                if not file.endswith(".tex") or file in _SKIP_FILES:
                    continue
                filepath = Path(root) / file
                content = filepath.read_text(encoding="utf-8")
                parsed = _parse_entity(filepath, content)
                if not parsed:
                    continue
                entity_id, entity_type, name, nl_desc = parsed
                if entity_id in processed:
                    continue
                processed.add(entity_id)
                entity_files[entity_id] = (filepath, content)

                try:
                    rel_path = str(filepath.relative_to(PROJECT_ROOT))
                except ValueError:
                    rel_path = str(filepath)  # content вне корня (напр. в тестах)
                entity = Entity(
                    id=entity_id, kind=entity_type, title=name,
                    nl_desc=nl_desc, path=str(filepath.parent), tex_path=rel_path,
                )
                repo.upsert_entity(conn, entity, commit=False)
                stats["entities"] += 1

                if compute_embeddings:
                    blob = get_binary_embedding(f"{name}\n{nl_desc}".strip())
                    if blob:
                        repo.set_embedding(conn, entity_id, blob, commit=False)
                        stats["embeddings"] += 1
                print(f"  [{entity_type}] {entity_id}")

        # 2) Граф зависимостей (только на существующие сущности)
        print("\n--- Построение графа зависимостей ---")
        for entity_id, (_fp, content) in entity_files.items():
            for dep_id in extract_dependencies(content):
                if dep_id == entity_id:
                    continue
                if dep_id in processed:
                    repo.add_dependency(conn, Dependency(entity_id, dep_id), commit=False)
                    stats["deps"] += 1
                else:
                    stats["dangling"] += 1
                    print(f"  [WARN] {entity_id} ссылается на неизвестную {dep_id}")

        conn.commit()
        print(f"\nГотово: {stats}")
        return stats
    finally:
        conn.close()


def main():
    rebuild(compute_embeddings=True)


if __name__ == "__main__":
    main()
