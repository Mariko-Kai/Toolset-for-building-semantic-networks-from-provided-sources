"""
generate_full_book.py — Полная компиляция учебника по математическому анализу
=============================================================================
Собирает все сущности из базы данных mathesis_index.db и вызывает
generate_answer.py со всеми ID сразу, создавая полный PDF-учебник в output/.

Поддерживает те же аргументы --provider / --model / --api-key / --force-refresh,
что и остальные скрипты конвейера.

Пример:
    python pipeline/generate_full_book.py
    python pipeline/generate_full_book.py --force-refresh
    python pipeline/generate_full_book.py --provider gemini --api-key $KEY
"""
import sys
import os
import sqlite3
import subprocess
import argparse
import io
from pathlib import Path

# Fix Windows console encoding
if sys.platform == 'win32' and getattr(sys.stdout, 'encoding', '').lower() != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.config import get_db_path
GENERATE_SCRIPT = PROJECT_ROOT / "pipeline" / "generate_answer.py"
DB_PATH = Path(get_db_path())  # единый путь к БД из конфига (env MATHESIS_DB_PATH)
OUTPUT_DIR = PROJECT_ROOT / "output"


def collect_all_entity_ids() -> list[str]:
    """Returns all entity IDs from mathesis_index.db, sorted by type then ID."""
    if not DB_PATH.exists():
        print(f"[-] База данных не найдена: {DB_PATH}")
        return []

    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    cursor = conn.cursor()
    try:
        cursor.execute("SELECT entity_id FROM entities ORDER BY entity_id")
        rows = cursor.fetchall()
        return [r[0] for r in rows if r[0]]
    except sqlite3.OperationalError as e:
        print(f"[-] Ошибка чтения БД: {e}")
        return []
    finally:
        conn.close()


def main():
    parser = argparse.ArgumentParser(
        description="Mathesis Full Book Compiler — компилирует полный учебник из всех сущностей в БД"
    )

    # ── Global provider overrides ─────────────────────────────────────────────
    parser.add_argument("--provider",  type=str, default=None, help="Глобальный провайдер LLM")
    parser.add_argument("--model",     type=str, default=None, help="Глобальная LLM модель")
    parser.add_argument("--api-key",   type=str, default=None, help="Глобальный API ключ")

    # ── Per-module overrides (forwarded to generate_answer.py) ───────────────
    parser.add_argument("--synth-provider",  type=str, default=None)
    parser.add_argument("--synth-model",     type=str, default=None)
    parser.add_argument("--synth-api-key",   type=str, default=None)

    parser.add_argument("--extract-provider",  type=str, default=None)
    parser.add_argument("--extract-model",     type=str, default=None)
    parser.add_argument("--extract-api-key",   type=str, default=None)

    parser.add_argument("--lean-provider",  type=str, default=None)
    parser.add_argument("--lean-model",     type=str, default=None)
    parser.add_argument("--lean-api-key",   type=str, default=None)

    parser.add_argument("--embed-provider",  type=str, default="ollama")
    parser.add_argument("--embed-model",     type=str, default="nomic-embed-text:latest")
    parser.add_argument("--embed-api-key",   type=str, default=None)

    parser.add_argument("--cv-model",  type=str, default="glm-ocr")
    parser.add_argument("--no-validate",  action='store_true', help='Пропустить Lean валидацию')
    parser.add_argument("--no-enrich",    action='store_true', help='Пропустить обогащение отсутствующих сущностей')
    parser.add_argument("--force-refresh", action='store_true',
                        help='Принудительно перегенерировать NL-описания из кэша')

    args = parser.parse_args()

    # ── Collect all entity IDs ─────────────────────────────────────────────
    entity_ids = collect_all_entity_ids()

    if not entity_ids:
        print("[-] В базе данных нет сущностей. Сначала запустите конвейер обогащения.")
        return

    # 1. Regenerate macros
    print("[main] Regenerating mathesis_macros.sty...")
    try:
        subprocess.run([sys.executable, str(PROJECT_ROOT / "pipeline" / "generate_macros.py")], check=True)
    except subprocess.CalledProcessError as e:
        print(f"[!] Warning: generate_macros.py failed: {e}")

    # 2. Setup inputs
    print("[main] Reading DB and topological sorting...")
    print(f"    Найдено сущностей в БД: {len(entity_ids)}")
    print(f"    Первые 10: {entity_ids[:10]}")
    roots_arg = ",".join(entity_ids)

    # ── Build the generate_answer.py command ───────────────────────────────
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    cmd = [sys.executable, str(GENERATE_SCRIPT), "--roots", roots_arg]

    # Forward all provider/model flags
    def _add(flag: str, val):
        if val is True:
            cmd.append(flag)
        elif val and val is not False:
            cmd.extend([flag, str(val)])

    _add("--provider",          args.provider)
    _add("--model",             args.model)
    _add("--api-key",           args.api_key)
    _add("--synth-provider",    args.synth_provider)
    _add("--synth-model",       args.synth_model)
    _add("--synth-api-key",     args.synth_api_key)
    _add("--extract-provider",  args.extract_provider)
    _add("--extract-model",     args.extract_model)
    _add("--extract-api-key",   args.extract_api_key)
    _add("--lean-provider",     args.lean_provider)
    _add("--lean-model",        args.lean_model)
    _add("--lean-api-key",      args.lean_api_key)
    _add("--embed-provider",    args.embed_provider)
    _add("--embed-model",       args.embed_model)
    _add("--embed-api-key",     args.embed_api_key)
    _add("--cv-model",          args.cv_model)
    if args.no_validate:
        cmd.append("--no-validate")
    if args.no_enrich:
        cmd.append("--no-enrich")
    if args.force_refresh:
        cmd.append("--force-refresh")

    print(f"\n[*] Запускаю компиляцию полного учебника ({len(entity_ids)} сущностей)...")
    print(f"    Вывод: {OUTPUT_DIR / 'result.pdf'}\n")

    env = os.environ.copy()
    env['PYTHONIOENCODING'] = 'utf-8'
    env['PYTHONUNBUFFERED'] = '1'

    try:
        process = subprocess.Popen(
            cmd, env=env,
            stdout=subprocess.PIPE, stderr=subprocess.STDOUT,
            text=True, encoding='utf-8'
        )
        for line in iter(process.stdout.readline, ''):
            print(line, end='', flush=True)
        process.wait()

        result_pdf = OUTPUT_DIR / "result.pdf"
        if result_pdf.exists():
            print(f"\n[+] Полный учебник успешно скомпилирован: {result_pdf}")
        else:
            print("\n[-] PDF не создан. Проверьте логи выше.")
            sys.exit(1)

    except subprocess.CalledProcessError as e:
        print(f"[-] Ошибка при компиляции: {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n[!] Прервано пользователем.")


if __name__ == "__main__":
    main()
