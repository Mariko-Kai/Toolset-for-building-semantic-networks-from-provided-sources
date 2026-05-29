"""Тест таймаута Lean REPL (ТЗ 0.4b): зависший процесс не вешает конвейер."""
from __future__ import annotations

import time

from pipeline import lean_validator
from pipeline.lean_validator import LeanREPL


class _HangingStdout:
    def readline(self):
        time.sleep(30)  # дольше любого тестового таймаута
        return ""


class _FakeStdin:
    def write(self, *a, **k):
        return None

    def flush(self):
        return None


class _FakeProc:
    """Имитация процесса REPL, который принимает запрос, но никогда не отвечает."""

    def __init__(self):
        self.stdin = _FakeStdin()
        self.stdout = _HangingStdout()
        self.terminated = False

    def poll(self):
        return None  # «жив»

    def terminate(self):
        self.terminated = True


def _make_repl_with_proc(proc):
    repl = object.__new__(LeanREPL)  # минуем __init__ (он требует repl.exe)
    repl.p = proc
    return repl


def test_validate_file_times_out(monkeypatch):
    monkeypatch.setattr(lean_validator, "VALIDATION_TIMEOUT", 1)
    LeanREPL._instance = "sentinel"  # будет сброшен в None при «отравлении»

    proc = _FakeProc()
    repl = _make_repl_with_proc(proc)

    start = time.monotonic()
    result = repl.validate_file("dummy.lean")
    elapsed = time.monotonic() - start

    assert result["status"] == "timeout"
    assert elapsed < 5, "таймаут не сработал — вызов завис"
    assert proc.terminated, "зависший процесс должен быть убит"
    assert LeanREPL._instance is None, "REPL должен быть помечен непригодным"


def test_validate_file_stdin_failure_is_structured():
    class _BrokenStdin:
        def write(self, *a, **k):
            raise OSError("broken pipe")

        def flush(self):
            return None

    proc = _FakeProc()
    proc.stdin = _BrokenStdin()
    repl = _make_repl_with_proc(proc)

    result = repl.validate_file("dummy.lean")
    assert result["status"] == "crashed"
    assert "stdin" in result["errors"][0]["message"].lower()
