"""Адаптеры реальных шагов конвейера в узлы (ТЗ Этап 5.2).

`SubprocessNode` оборачивает подпроцесс (extract/align/synth) в узел с типизированным
`NodeResult`. Ключевое: разбор stdout (раньше — магические строки в теле
`run_enrichment_pipeline`) инкапсулирован в узле через `parse_line`; оркестратор
видит только структурный `output`/`status`. «Синтез не дал сущностей» становится
явным `DEVIATION` — пример отклонения, на которое реагирует оркестратор.
"""
from __future__ import annotations

import json
import re
import subprocess
import time
from typing import Callable, Optional

from pipeline.nodes.base import NodeContext, NodeResult, NodeStatus


def _default_runner(cmd, env, on_line: Callable[[str], None], timeout: Optional[float]) -> int:
    """Поток stdout построчно; при сбое/таймауте убивает дерево процессов."""
    from mathesis.proc import kill_process_tree
    proc = subprocess.Popen(
        cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
        text=True, encoding="utf-8", errors="replace",
    )
    try:
        if proc.stdout is not None:
            for line in iter(proc.stdout.readline, ""):
                on_line(line.rstrip("\n"))
        proc.wait(timeout=timeout)
        return proc.returncode
    except Exception:
        kill_process_tree(proc)
        raise


class SubprocessNode:
    """Узел-обёртка над подпроцессом."""

    def __init__(self, name: str, cmd: list, *, env: dict | None = None,
                 timeout: float | None = None,
                 parse_line: Callable[[str, dict], None] | None = None,
                 deviation_check: Callable[[dict], str | None] | None = None,
                 runner: Callable | None = None,
                 max_events: int = 30):
        self.name = name
        self.cmd = cmd
        self.env = env
        self.timeout = timeout
        self.parse_line = parse_line
        self.deviation_check = deviation_check
        self._runner = runner or _default_runner
        self.max_events = max_events

    def run(self, ctx: NodeContext) -> NodeResult:
        captured: dict = {}
        events: list[str] = []

        def on_line(line: str) -> None:
            if line:
                events.append(line)
            if self.parse_line:
                try:
                    self.parse_line(line, captured)
                except Exception:
                    pass

        t0 = time.monotonic()
        try:
            rc = self._runner(self.cmd, self.env, on_line, self.timeout)
        except Exception as e:  # noqa: BLE001
            return NodeResult(
                NodeStatus.FAILED, output=captured, events=events[-self.max_events:],
                metrics={"duration_s": time.monotonic() - t0},
                message=f"{type(e).__name__}: {e}",
            )
        duration = time.monotonic() - t0
        metrics = {"returncode": float(rc), "duration_s": duration}

        if rc != 0:
            status = NodeStatus.FAILED
            message = f"подпроцесс завершился с кодом {rc}"
        else:
            reason = self.deviation_check(captured) if self.deviation_check else None
            if reason:
                status, message = NodeStatus.DEVIATION, reason
            else:
                status, message = NodeStatus.OK, ""

        return NodeResult(status, output=captured, metrics=metrics,
                          events=events[-self.max_events:], message=message)


# --- Парсеры/проверки для конкретных шагов конвейера ------------------------
def parse_synth_line(line: str, out: dict) -> None:
    """Извлекает структурный handoff синтезатора (entity_id, ParsedDeps)."""
    if "[synthesizer] Parsed: entity_id=" in line:
        m = re.search(r"entity_id=([^,\s]+)", line)
        if m:
            out.setdefault("entities", []).append(m.group(1).strip())
    if "[synthesizer] ParsedDeps:" in line:
        try:
            payload = json.loads(line.split("ParsedDeps: ", 1)[1])
            eid = payload.get("entity_id")
            if eid:
                out.setdefault("deps", {})[eid] = payload.get("deps", [])
        except Exception:
            pass


def _synth_deviation(out: dict) -> str | None:
    """Норма синтеза: ≥1 сущность. Иначе — отклонение."""
    if not out.get("entities"):
        return "синтез не произвёл ни одной сущности"
    return None


def build_enrichment_flow(extract_cmd: list, align_cmd: list, synth_cmd: list,
                          *, env: dict | None = None, runner: Callable | None = None,
                          synth_timeout: float | None = None) -> list:
    """Собирает поток узлов extract → align → synth (замена жёсткого списка steps)."""
    return [
        SubprocessNode("extract", extract_cmd, env=env, runner=runner),
        SubprocessNode("align", align_cmd, env=env, runner=runner),
        SubprocessNode("synth", synth_cmd, env=env, runner=runner,
                       parse_line=parse_synth_line, deviation_check=_synth_deviation,
                       timeout=synth_timeout),
    ]
