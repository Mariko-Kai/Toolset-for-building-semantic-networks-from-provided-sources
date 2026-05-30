"""Тесты mathesis.proc (ТЗ 1.1): убийство дерева процессов и таймауты."""
from __future__ import annotations

import subprocess
import sys
import time

import psutil
import pytest

from mathesis import proc

# Программа: спавнит долгоживущего "внука", пишет его PID в файл из argv[1],
# затем сама засыпает. Так мы проверяем, что kill_process_tree убивает потомка.
_SPAWNER = (
    "import subprocess, sys, time\n"
    "child = subprocess.Popen([sys.executable, '-c', 'import time; time.sleep(60)'])\n"
    "open(sys.argv[1], 'w').write(str(child.pid))\n"
    "time.sleep(60)\n"
)


def test_managed_process_kills_grandchild(tmp_path):
    pidfile = tmp_path / "child.pid"
    grandchild_pid = None
    with proc.managed_process([sys.executable, "-c", _SPAWNER, str(pidfile)]) as p:
        # Ждём, пока внук родится и его PID будет записан.
        for _ in range(100):
            if pidfile.exists() and pidfile.read_text().strip():
                grandchild_pid = int(pidfile.read_text().strip())
                break
            time.sleep(0.05)
        assert grandchild_pid is not None, "внук не запустился"
        assert psutil.pid_exists(grandchild_pid)
        parent_pid = p.pid

    # После выхода из контекста и родитель, и внук должны быть мертвы.
    deadline = time.time() + 5
    while time.time() < deadline and (psutil.pid_exists(grandchild_pid) or psutil.pid_exists(parent_pid)):
        time.sleep(0.05)
    assert not _alive(grandchild_pid), "внук пережил kill_process_tree"
    assert not _alive(parent_pid), "родитель пережил kill_process_tree"


def _alive(pid: int) -> bool:
    """pid_exists, но зомби (уже завершившиеся, не reaped) считаем мёртвыми."""
    if not psutil.pid_exists(pid):
        return False
    try:
        return psutil.Process(pid).status() != psutil.STATUS_ZOMBIE
    except psutil.NoSuchProcess:
        return False


def test_kill_process_tree_idempotent_and_safe_on_none():
    proc.kill_process_tree(None)  # не должно падать
    p = subprocess.Popen([sys.executable, "-c", "import time; time.sleep(60)"])
    proc.kill_process_tree(p)
    proc.kill_process_tree(p)  # повторно — безопасно
    assert not _alive(p.pid)


def test_run_with_timeout_returns_value():
    assert proc.run_with_timeout(lambda: 21 * 2, timeout=5) == 42


def test_run_with_timeout_raises_on_slow():
    def slow():
        time.sleep(30)
        return "never"

    with pytest.raises(TimeoutError):
        proc.run_with_timeout(slow, timeout=0.5)


def test_run_with_timeout_propagates_error():
    def boom():
        raise ValueError("kaboom")

    with pytest.raises(ValueError, match="kaboom"):
        proc.run_with_timeout(boom, timeout=5)
