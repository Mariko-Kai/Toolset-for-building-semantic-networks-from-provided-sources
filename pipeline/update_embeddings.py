"""Пересчёт эмбеддингов сущностей (ТЗ Этап 3.1).

Улучшения против прежней версии:
  * путь к БД из единого источника (pipeline.config), без хардкода;
  * инкрементальность: по умолчанию пропускаем сущности, у которых эмбеддинг уже
    есть (--force пересчитывает все);
  * чекпойнты: периодический commit, чтобы прогресс не терялся при сбое.
"""
from __future__ import annotations

import argparse
import sqlite3
import struct
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.config import get_db_path  # noqa: E402

MODEL = "nomic-embed-text:latest"
CHECKPOINT_EVERY = 25


def main():
    parser = argparse.ArgumentParser(description="Recompute entity embeddings (BLOB).")
    parser.add_argument("--force", action="store_true", help="Пересчитать даже уже посчитанные эмбеддинги.")
    parser.add_argument("--model", default=MODEL)
    args = parser.parse_args()

    import ollama  # тяжёлая зависимость — импорт по месту

    db_path = get_db_path()
    print(f"=== Обновление эмбеддингов (BLOB) === {db_path}")
    conn = sqlite3.connect(db_path)
    cursor = conn.cursor()

    if args.force:
        cursor.execute("SELECT entity_id, title, nl_desc FROM entities")
    else:
        cursor.execute("SELECT entity_id, title, nl_desc FROM entities WHERE embedding IS NULL")
    rows = cursor.fetchall()
    print(f"К обработке: {len(rows)} сущностей{' (только без эмбеддинга)' if not args.force else ''}.")

    done = 0
    for i, (entity_id, title, nl_desc) in enumerate(rows, 1):
        text = f"{title}\n{nl_desc or ''}".strip()
        try:
            emb = ollama.embeddings(model=args.model, prompt=text)["embedding"]
            blob = struct.pack(f"{len(emb)}f", *emb)
            cursor.execute("UPDATE entities SET embedding = ? WHERE entity_id = ?", (blob, entity_id))
            done += 1
            print(f"  [+] {entity_id}")
        except Exception as e:
            print(f"  [-] {entity_id}: {e}")
        if i % CHECKPOINT_EVERY == 0:
            conn.commit()  # чекпойнт: прогресс сохранён
            print(f"  ...checkpoint ({i}/{len(rows)})")

    conn.commit()
    conn.close()
    print(f"Готово! Обновлено {done}/{len(rows)}.")


if __name__ == "__main__":
    main()
