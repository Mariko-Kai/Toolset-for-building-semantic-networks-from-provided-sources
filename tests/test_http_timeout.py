"""Гарантия, что сетевые вызовы Ollama имеют таймаут (ТЗ 0.4c)."""
from __future__ import annotations

import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
MODEL_MANAGER = PROJECT_ROOT / "pipeline" / "model_manager.py"


def test_all_urlopen_calls_have_timeout():
    src = MODEL_MANAGER.read_text(encoding="utf-8")
    calls = re.findall(r"urlopen\([^)]*\)", src, flags=re.DOTALL)
    assert calls, "ожидались вызовы urlopen"
    offenders = [c for c in calls if "timeout=" not in c]
    assert not offenders, f"urlopen без timeout=: {offenders}"
