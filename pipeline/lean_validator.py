"""
Lean Validator v3 — REPL-based Fast Validation
=============================================
Validates generated Lean 4 files using repl.exe for persistent Mathlib loading.
"""
import subprocess
import json
import os
from pathlib import Path
import time
import atexit

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LEAN_DIR = PROJECT_ROOT / "lean_validator"

VALIDATION_TIMEOUT = 150  # seconds

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
            raise FileNotFoundError(f"repl.exe not found")
            
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
        if self.p and self.p.poll() is None:
            self.p.terminate()

    def validate_file(self, path: str) -> dict:
        req = json.dumps({"path": path, "allTactics": False})
        try:
            self.p.stdin.write(req + '\n\n')
            self.p.stdin.flush()
            
            # Read lines until a complete JSON object is parsed
            buffer = ""
            decoder = json.JSONDecoder()
            while True:
                line = self.p.stdout.readline()
                if not line:
                    return {"status": "failed", "errors": [{"line": 0, "message": "REPL crashed or returned empty response"}]}
                
                buffer += line
                start_idx = buffer.find('{')
                if start_idx != -1:
                    json_str = buffer[start_idx:]
                    try:
                        resp, _ = decoder.raw_decode(json_str)
                        return self._parse_repl_response(resp)
                    except json.JSONDecodeError:
                        # Continue reading lines until the JSON object is complete
                        pass
                
                # Prevent infinite loops in case of massive unexpected output
                if len(buffer) > 5 * 1024 * 1024: # 5MB limit
                    return {"status": "failed", "errors": [{"line": 0, "message": "REPL output too large without valid JSON"}]}
                    
        except Exception as e:
            return {"status": "failed", "errors": [{"line": 0, "message": f"Exception communicating with REPL: {str(e)}"}]}

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

def validate_entity(entity_id: str, lean_code: str) -> dict:
    temp_file = LEAN_DIR / "TempValidation.lean"
    try:
        imports = {"import Mathlib"}
        body_lines = []
        
        for line in lean_code.splitlines():
            trimmed = line.strip()
            if trimmed.startswith("import "):
                imports.add(trimmed)
            elif "set_option maxHeartbeats" in trimmed:
                # STRIP maxHeartbeats to prevent infinite loops causing OOM
                continue
            else:
                body_lines.append(line)
                
        with open(temp_file, 'w', encoding='utf-8') as f:
            for imp in sorted(imports):
                f.write(imp + "\n")
            f.write("\n")
            f.write(f"-- Validation for {entity_id}\n\n")
            f.write("\n".join(body_lines) + "\n")

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
