"""Внешние версионируемые промпты (ТЗ Этап 4.3).

Промпты живут в файлах `pipeline/prompts/templates/<name>.txt`, а не в коде.
Подстановка переменных — синтаксис `{{name}}` (НЕ конфликтует с `$...$` и `{...}`
из LaTeX, в отличие от str.format/string.Template). Менять промпт = править файл.

Крупные промпты синтезатора/Lean мигрируют на эту инфраструктуру постепенно.
"""
from __future__ import annotations

import re
from pathlib import Path

TEMPLATES_DIR = Path(__file__).resolve().parent / "templates"
_PLACEHOLDER = re.compile(r"\{\{\s*(\w+)\s*\}\}")


def render(text: str, **variables) -> str:
    """Подставляет {{name}} -> str(variables[name]); неизвестные оставляет как есть."""
    def _sub(m: re.Match) -> str:
        key = m.group(1)
        return str(variables[key]) if key in variables else m.group(0)
    return _PLACEHOLDER.sub(_sub, text)


def load_prompt(name: str, **variables) -> str:
    """Загружает шаблон `<name>.txt` и подставляет переменные."""
    path = TEMPLATES_DIR / f"{name}.txt"
    if not path.exists():
        raise FileNotFoundError(f"Промпт '{name}' не найден: {path}")
    return render(path.read_text(encoding="utf-8"), **variables)


def available_prompts() -> list[str]:
    if not TEMPLATES_DIR.exists():
        return []
    return sorted(p.stem for p in TEMPLATES_DIR.glob("*.txt"))
