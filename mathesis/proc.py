"""Кроссплатформенное управление подпроцессами (ТЗ Этап 1.1).

Главные проблемы, которые решает модуль:
  * `Popen.terminate()` убивает только сам процесс, но не его потомков —
    на Windows (а часто и на Linux) остаются осиротевшие дочерние процессы
    (lake/repl, llama.cpp server). Здесь убиваем всё дерево через psutil.
  * Блокирующее чтение из pipe может зависнуть навсегда. `run_with_timeout`
    выполняет операцию в отдельном потоке и накладывает таймаут.

Модуль не зависит от остального кода Mathesis и пригоден для переиспользования.
"""
from __future__ import annotations

import contextlib
import subprocess
import threading
from typing import Callable, Iterator, TypeVar

try:
    import psutil
    _HAS_PSUTIL = True
except ImportError:  # pragma: no cover - psutil объявлен в зависимостях
    _HAS_PSUTIL = False

T = TypeVar("T")


def kill_process_tree(proc=None, timeout: float = 5.0) -> None:
    """Завершает процесс и всех его потомков.

    Сначала мягко (`terminate`/SIGTERM), затем жёстко (`kill`/SIGKILL) для тех,
    кто не завершился за `timeout`. Безопасно вызывать повторно и на уже
    завершённом процессе. Принимает `Popen`, PID (int) или любой объект с
    методами `terminate()`/`kill()` (например, тестовый дубль).
    """
    if proc is None:
        return

    pid = getattr(proc, "pid", None)
    if pid is None:
        try:
            pid = int(proc)
        except (TypeError, ValueError):
            pid = None

    # Нет psutil или нет валидного pid → деградация на сам объект.
    if not _HAS_PSUTIL or pid is None:
        _terminate_then_kill_obj(proc, timeout)
        return

    try:
        parent = psutil.Process(pid)
    except (psutil.NoSuchProcess, ValueError):
        # pid уже не существует (или это «фейковый» pid) — пробуем объект напрямую.
        _terminate_then_kill_obj(proc, timeout)
        return

    try:
        targets = parent.children(recursive=True)
    except psutil.NoSuchProcess:
        targets = []
    targets.append(parent)

    for p in targets:
        try:
            p.terminate()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass

    _, alive = psutil.wait_procs(targets, timeout=timeout)
    for p in alive:
        try:
            p.kill()
        except (psutil.NoSuchProcess, psutil.AccessDenied):
            pass
    psutil.wait_procs(alive, timeout=timeout)

    # Reap Popen, чтобы не оставлять зомби на POSIX.
    if isinstance(proc, subprocess.Popen):
        try:
            proc.wait(timeout=timeout)
        except Exception:
            pass


def _terminate_then_kill_obj(proc, timeout: float) -> None:
    """Завершение объекта с интерфейсом Popen-like (terminate/kill/wait)."""
    try:
        poll = getattr(proc, "poll", None)
        if callable(poll) and poll() is not None:
            return  # уже завершён
        terminate = getattr(proc, "terminate", None)
        if callable(terminate):
            terminate()
        wait = getattr(proc, "wait", None)
        if callable(wait):
            try:
                wait(timeout=timeout)
            except TypeError:
                wait()
            except subprocess.TimeoutExpired:
                kill = getattr(proc, "kill", None)
                if callable(kill):
                    kill()
    except Exception:
        pass


def run_with_timeout(fn: Callable[[], T], timeout: float) -> T:
    """Выполняет `fn()` в отдельном потоке с таймаутом.

    Возвращает результат `fn`. Бросает `TimeoutError`, если `fn` не успела за
    `timeout` секунд (поток остаётся daemon и не блокирует завершение процесса).
    Любое исключение из `fn` пробрасывается наружу.
    """
    box: dict = {}

    def _runner() -> None:
        try:
            box["value"] = fn()
        except BaseException as exc:  # noqa: BLE001 - пробрасываем как есть
            box["error"] = exc

    t = threading.Thread(target=_runner, daemon=True)
    t.start()
    t.join(timeout)
    if t.is_alive():
        raise TimeoutError(f"operation exceeded timeout of {timeout}s")
    if "error" in box:
        raise box["error"]
    return box["value"]


@contextlib.contextmanager
def managed_process(cmd, **popen_kwargs) -> Iterator[subprocess.Popen]:
    """Контекст-менеджер: запускает процесс и гарантированно убивает всё его
    дерево при выходе (в том числе при исключении)."""
    proc = subprocess.Popen(cmd, **popen_kwargs)
    try:
        yield proc
    finally:
        kill_process_tree(proc)
