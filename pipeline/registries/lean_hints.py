"""Data-driven подсказки по ошибкам Lean (ТЗ Этап 4.2).

Заменяет разбросанные `if "..." in error: feedback += "..."` единой таблицей
правил. Новая подсказка = добавить HintRule (или, позже, строку в YAML), без
правки кода формализатора.
"""
from __future__ import annotations

import re
from dataclasses import dataclass


@dataclass
class HintRule:
    pattern: str            # подстрока или regex
    hint: str               # текст подсказки; для regex может содержать {0},{1}…
    is_regex: bool = False


# Базовые правила (консолидируют прежние захардкоженные подсказки).
DEFAULT_RULES: list[HintRule] = [
    HintRule(
        "unexpected token 'in'",
        "HINT: You used the word `in` as a token (e.g., `∑ x in s`). In Lean 4 use `∈` "
        "for set membership in binders: `∑ x ∈ s, f x`. The word `in` is invalid here.",
    ),
    HintRule(
        r"unknown identifier '([^']+)'",
        "HINT: Lean does not know identifier '{0}'. Declare it via a quantifier/binder, "
        "or replace the raw macro with an allowed semantic one.",
        is_regex=True,
    ),
    HintRule(
        "don't know how to synthesize placeholder",
        "HINT: A placeholder `_` could not be inferred. Provide the exact type explicitly.",
    ),
    HintRule(
        "function expected",
        "HINT: You applied something that is not a function. Check arities and parentheses.",
    ),
]


def hints_for_error(error_text: str, rules: list[HintRule] | None = None) -> list[str]:
    """Возвращает применимые подсказки для текста ошибки (по таблице правил)."""
    if not error_text:
        return []
    rules = rules if rules is not None else DEFAULT_RULES
    out: list[str] = []
    for r in rules:
        if r.is_regex:
            m = re.search(r.pattern, error_text)
            if m:
                out.append(r.hint.format(*m.groups()))
        elif r.pattern in error_text:
            out.append(r.hint)
    return out
