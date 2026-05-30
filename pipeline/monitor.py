"""CLI-мониторинг прогонов оркестратора (ТЗ: мониторинг в CLI).

Использование:
  python -m pipeline.monitor                 # список последних прогонов
  python -m pipeline.monitor <run_id>        # детали: health, события, инциденты
  python -m pipeline.monitor --incidents     # открытые инциденты (ждут решения)
  python -m pipeline.monitor --resolve <id> --as confirmed|rejected

Формирование текста вынесено в чистые функции (тестируются без БД/сети).
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from mathesis import db as _db
from pipeline.config import get_db_path
from pipeline.orchestration import (
    list_runs,
    load_run,
    open_incidents,
    set_incident_resolution,
)

_STATUS_ICON = {"completed": "✓", "paused": "⏸", "failed": "✗", "running": "…"}


def format_run_list(runs: list[dict]) -> str:
    if not runs:
        return "Прогонов не найдено."
    lines = ["RUN_ID                          STATUS      NODES  DEV  FAIL  UPDATED"]
    for r in runs:
        h = r.get("health", {})
        icon = _STATUS_ICON.get(r["status"], " ")
        lines.append(
            f"{r['run_id'][:30]:<30}  {icon} {r['status']:<8}  "
            f"{h.get('nodes_total', 0):>4}  {h.get('deviations', 0):>3}  "
            f"{h.get('failures', 0):>4}  {(r.get('updated_at') or '')[:19]}"
        )
    return "\n".join(lines)


def format_run_detail(run: dict | None) -> str:
    if run is None:
        return "Прогон не найден."
    out = [f"Прогон: {run['run_id']}  [{run['status']}]",
           f"  обновлён: {run.get('updated_at')}",
           f"  health: {run.get('health')}",
           "  События:"]
    for e in run.get("events", []):
        suffix = f" — {e['message']}" if e.get("message") else ""
        out.append(f"    #{e['seq']:>2} {e['node']:<12} {e['kind']:<12} {e['status']}{suffix}")
    incs = run.get("incidents", [])
    if incs:
        out.append("  Инциденты:")
        for i in incs:
            out.append(f"    [{i['id']}] {i['node']} {i['status']} ({i['severity']}) -> {i['resolution']}")
    return "\n".join(out)


def format_incident_list(incidents: list[dict]) -> str:
    if not incidents:
        return "Открытых инцидентов нет."
    lines = ["ID   RUN_ID                     NODE          STATUS      SEVERITY"]
    for i in incidents:
        lines.append(f"{i['id']:<4} {i['run_id'][:25]:<25}  {i['node']:<12}  {i['status']:<10}  {i['severity']}")
    return "\n".join(lines)


def main(argv=None):
    parser = argparse.ArgumentParser(description="Монитор прогонов Mathesis-оркестратора.")
    parser.add_argument("run_id", nargs="?", help="ID прогона для детального просмотра")
    parser.add_argument("--incidents", action="store_true", help="Показать открытые инциденты")
    parser.add_argument("--resolve", type=int, metavar="ID", help="Пометить инцидент решённым")
    parser.add_argument("--as", dest="resolution", default="confirmed",
                        choices=["confirmed", "rejected", "applied"], help="Резолюция для --resolve")
    parser.add_argument("--limit", type=int, default=50)
    args = parser.parse_args(argv)

    conn = _db.connect(get_db_path())
    try:
        if args.resolve is not None:
            set_incident_resolution(conn, args.resolve, args.resolution)
            print(f"Инцидент {args.resolve} -> {args.resolution}")
        elif args.incidents:
            print(format_incident_list(open_incidents(conn)))
        elif args.run_id:
            print(format_run_detail(load_run(conn, args.run_id)))
        else:
            print(format_run_list(list_runs(conn, args.limit)))
    finally:
        conn.close()


if __name__ == "__main__":
    main()
