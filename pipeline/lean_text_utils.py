"""Shared, pure helpers for parsing Lean declarations out of `.lean` sources.

These were duplicated verbatim in `postprocess_equivalence.py` and
`lean_equivalence_checker.py` (ТЗ C.5 dedup). They take no instance state, so they
live here as module-level functions; both modules delegate to them.
"""
from __future__ import annotations

import os
import re


def extract_lean_statement(lean_filepath: str) -> str:
    """Извлекает строгую формулировку сущности, соответствующей имени файла."""
    basename = os.path.splitext(os.path.basename(lean_filepath))[0]
    target_name = basename.replace('-', '_')

    with open(lean_filepath, 'r', encoding='utf-8') as f:
        lean_content = f.read()

    # Убираем комментарии и импорты
    lines = []
    for line in lean_content.splitlines():
        if line.strip().startswith(('import ', 'open ', 'set_option ')):
            continue
        lines.append(line)
    content_clean = "\n".join(lines).strip()

    # Ищем блок, который начинается с объявления нашей target_name.
    pattern = rf'\b(def|theorem|lemma|abbrev|structure|class)\s+{re.escape(target_name)}\b'
    match = re.search(pattern, content_clean)

    if match:
        start_idx = match.start()
        rest = content_clean[start_idx:]
        next_decl = re.search(r'\n\s*\b(def|theorem|lemma|abbrev|structure|class)\b', rest[1:])
        if next_decl:
            statement_block = rest[:next_decl.start() + 1].strip()
        else:
            statement_block = rest.strip()

        # Для теоремы/леммы отрезаем доказательство (после := или := by).
        keyword = match.group(1)
        if keyword in ('theorem', 'lemma'):
            match_proof = re.search(r'(.*?)(?::=|:= by)', statement_block, re.DOTALL)
            if match_proof:
                statement = match_proof.group(1).strip()
                if statement.endswith('by'):
                    statement = statement[:-2].strip()
                if statement.endswith(':='):
                    statement = statement[:-2].strip()
                return statement
        return statement_block

    # Резервный вариант: старая логика.
    if re.search(r'\b(def|abbrev|structure|class)\b', content_clean):
        return content_clean

    match_proof = re.search(r'((?:theorem|lemma)\s+.*?(?::=|:= by))', content_clean, re.DOTALL)
    if match_proof:
        statement = match_proof.group(1).strip()
        if statement.endswith('by'):
            statement = statement[:-2].strip()
        if statement.endswith(':='):
            statement = statement[:-2].strip()
        return statement

    return content_clean


def get_lean_name(statement: str) -> str:
    """Извлекает имя теоремы/определения из Lean-формулировки."""
    match = re.search(r'(?:theorem|lemma|def|abbrev|structure|class)\s+([a-zA-Z0-9_’\']+)', statement)
    return match.group(1).strip() if match else "Name"


def determine_operator(entity_id: str) -> str:
    """Эвристика оператора эквивалентности по префиксу ID."""
    if entity_id.startswith(('thm-', 'lem-', 'prop-')):
        return "↔"
    return "="
