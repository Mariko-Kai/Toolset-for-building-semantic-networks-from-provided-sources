"""Пересев БД из content/*.tex без вычисления эмбеддингов (ТЗ Этап 2.3).

Тонкая обёртка над `actualize_db.rebuild` — единая логика построения канонической
БД, без дублирования парсинга. Эмбеддинги пропускаются (быстрый прогон).
"""
from __future__ import annotations

import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.actualize_db import rebuild  # noqa: E402


def main():
    print("=== Reseed (без эмбеддингов) ===")
    rebuild(compute_embeddings=False)
    print("Reseed complete!")


if __name__ == "__main__":
    main()
