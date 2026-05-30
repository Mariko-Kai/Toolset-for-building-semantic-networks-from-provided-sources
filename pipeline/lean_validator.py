"""
Lean Validator v3 — REPL-based Fast Validation
=============================================
Validates generated Lean 4 files using repl.exe for persistent Mathlib loading.
"""
import subprocess
import json
import os
import queue
import sys
import threading
from pathlib import Path
import atexit

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LEAN_DIR = PROJECT_ROOT / "lean_validator"

if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))
from mathesis.proc import kill_process_tree  # noqa: E402  (импорт после настройки sys.path)

# Таймаут одной REPL-валидации (сек). Холодный старт грузит Mathlib (десятки секунд),
# поэтому дефолт с запасом; настраивается через env MATHESIS_LEAN_TIMEOUT.
VALIDATION_TIMEOUT = int(os.environ.get("MATHESIS_LEAN_TIMEOUT", "300"))

def log(msg):
    try:
        print(f"  [lean-validator] {msg}")
    except UnicodeEncodeError:
        safe = str(msg).encode('ascii', errors='replace').decode('ascii')
        print(f"  [lean-validator] {safe}")

def _get_lake_cmd() -> str:
    home_candidates = [
        os.environ.get("USERPROFILE", ""),
        os.environ.get("HOME", ""),
        os.path.expanduser("~"),
    ]
    for home in home_candidates:
        if home:
            elan_bin = Path(home) / ".elan" / "bin" / "lake.exe"
            if elan_bin.exists():
                return str(elan_bin)
            elan_bin_nix = Path(home) / ".elan" / "bin" / "lake"
            if elan_bin_nix.exists():
                return str(elan_bin_nix)
    return "lake"

class LeanREPL:
    _instance = None

    @classmethod
    def get(cls):
        if cls._instance is None or cls._instance.p.poll() is not None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        lake_cmd = _get_lake_cmd()
        repl_path = LEAN_DIR / ".lake" / "packages" / "repl" / ".lake" / "build" / "bin" / "repl.exe"
        if not repl_path.exists():
            log(f"ERROR: repl.exe not found at {repl_path}. Run lake build in lean_validator")
            raise FileNotFoundError("repl.exe not found")

        env = os.environ.copy()
        env['PYTHONIOENCODING'] = 'utf-8'

        self.p = subprocess.Popen(
            [lake_cmd, "env", str(repl_path)],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT, # Merge stderr to stdout
            text=True,
            cwd=str(LEAN_DIR),
            encoding='utf-8',
            errors='replace',
            env=env,
            bufsize=1
        )
        atexit.register(self.shutdown)
        log("Started Lean REPL process.")

    def shutdown(self):
        # Убиваем всё дерево процессов (lake → repl), а не только корневой Popen,
        # иначе на Windows/Linux остаются осиротевшие процессы.
        kill_process_tree(self.p)

    def _poison(self):
        """Помечает REPL непригодным: убивает дерево процессов и сбрасывает
        singleton, чтобы следующий get() создал свежий инстанс."""
        kill_process_tree(self.p)
        type(self)._instance = None

    def _read_response(self, result_q: "queue.Queue") -> None:
        """Читает ответ REPL до полного JSON. Выполняется в отдельном потоке,
        чтобы основной поток мог наложить таймаут."""
        buffer = ""
        decoder = json.JSONDecoder()
        try:
            while True:
                line = self.p.stdout.readline()
                if not line:
                    result_q.put({"status": "crashed", "errors": [{"line": 0, "message": "REPL crashed or returned empty response"}]})
                    return

                buffer += line
                start_idx = buffer.find('{')
                if start_idx != -1:
                    try:
                        resp, _ = decoder.raw_decode(buffer[start_idx:])
                        result_q.put(self._parse_repl_response(resp))
                        return
                    except json.JSONDecodeError:
                        # Продолжаем читать строки, пока JSON-объект не станет полным.
                        pass

                # Защита от бесконечного цикла при неожиданно большом выводе.
                if len(buffer) > 5 * 1024 * 1024:  # 5MB limit
                    result_q.put({"status": "failed", "errors": [{"line": 0, "message": "REPL output too large without valid JSON"}]})
                    return
        except Exception as e:
            result_q.put({"status": "crashed", "errors": [{"line": 0, "message": f"Exception reading REPL: {str(e)}"}]})

    def validate_file(self, path: str) -> dict:
        req = json.dumps({"path": path, "allTactics": False})
        try:
            self.p.stdin.write(req + '\n\n')
            self.p.stdin.flush()
        except Exception as e:
            self._poison()
            return {"status": "crashed", "errors": [{"line": 0, "message": f"REPL stdin write failed: {str(e)}"}]}

        result_q: "queue.Queue" = queue.Queue(maxsize=1)
        reader = threading.Thread(target=self._read_response, args=(result_q,), daemon=True)
        reader.start()

        try:
            return result_q.get(timeout=VALIDATION_TIMEOUT)
        except queue.Empty:
            # REPL завис — убиваем и помечаем непригодным, чтобы следующий вызов
            # получил свежий инстанс вместо зависшего.
            self._poison()
            return {"status": "timeout", "errors": [{"line": 0, "message": f"Lean REPL timed out after {VALIDATION_TIMEOUT}s"}]}

    def _parse_repl_response(self, resp: dict) -> dict:
        errors = []
        for msg in resp.get("messages", []):
            severity = msg.get("severity")
            data = msg.get("data", "")

            if severity == "error" or (severity == "warning" and "uses `sorry`" not in data and "uses 'sorry'" not in data):
                errors.append({
                    "line": msg.get("pos", {}).get("line", 0),
                    "column": msg.get("pos", {}).get("column", 0),
                    "message": data[:500]
                })

        if not errors and "env" in resp:
            return {"status": "success", "errors": []}
        else:
            return {"status": "failed", "errors": errors}

def check_lean_environment() -> bool:
    try:
        LeanREPL.get()
        return True
    except Exception as e:
        log(f"Lean environment check failed: {e}")
        return False

def validate_semantics_with_lean(lean_file_path: str) -> dict:
    lean_file = Path(lean_file_path)
    if not lean_file.exists():
        return {"status": "failed", "errors": [{"line": 0, "message": f"File not found: {lean_file}"}]}

    try:
        repl = LeanREPL.get()
        log(f"Validating (via REPL): {lean_file.name}")
        result = repl.validate_file(str(lean_file.absolute()))

        if result["status"] == "success":
            log("[OK] No errors.")
        else:
            errors = result.get("errors", [])
            log(f"[FAIL] {len(errors)} error(s). First: {errors[0]['message'][:120] if errors else 'N/A'}")

        return result
    except Exception as e:
        log(f"Failed to validate with REPL: {e}")
        return {"status": "failed", "errors": [{"line": 0, "message": str(e)}]}

def validate_entity(entity_id: str, lean_code: str, deps: list = None) -> dict:
    temp_file = LEAN_DIR / "TempValidation.lean"
    try:
        import sys
        if str(PROJECT_ROOT) not in sys.path:
            sys.path.insert(0, str(PROJECT_ROOT))
        from tools.lean_tree_builder import LeanTreeBuilder

        builder = LeanTreeBuilder()
        success = builder.generate_lean_tree_file(
            target_id=entity_id,
            output_path=str(temp_file),
            target_code=lean_code,
            target_deps=deps
        )

        if not success:
            return {"status": "failed", "errors": [{"line": 0, "message": "LeanTreeBuilder failed to generate environment."}]}

        return validate_semantics_with_lean(str(temp_file))
    finally:
        try:
            temp_file.unlink()
        except Exception:
            pass

def discover_mathlib_signatures(terms: list[str]) -> list[str]:
    # Placeholder for discovery if needed.
    return []

def validate_tree(entities: list[dict]) -> dict:
    temp_file = LEAN_DIR / "TempTreeValidation.lean"
    try:
        imports = {"import Mathlib"}
        all_body_lines = []

        for ent in entities:
            eid = ent["id"]
            lean_code = ent["lean_code"]
            body_lines = []

            for line in lean_code.splitlines():
                trimmed = line.strip()
                if trimmed.startswith("import "):
                    imports.add(trimmed)
                elif "set_option maxHeartbeats" in trimmed:
                    continue
                else:
                    body_lines.append(line)

            all_body_lines.append(f"-- Validation for {eid}")
            all_body_lines.extend(body_lines)
            all_body_lines.append("")

        with open(temp_file, 'w', encoding='utf-8') as f:
            for imp in sorted(imports):
                f.write(imp + "\n")
            f.write("\n")
            f.write("\n".join(all_body_lines) + "\n")

        return validate_semantics_with_lean(str(temp_file))
    finally:
        try:
            temp_file.unlink()
        except Exception:
            pass

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        if not check_lean_environment():
            sys.exit(1)
        res = validate_semantics_with_lean(sys.argv[1])
        print(json.dumps(res, indent=2, ensure_ascii=False))
    else:
        print("Usage: python lean_validator.py <path_to_lean_file>")
