import subprocess
import json
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LEAN_DIR = PROJECT_ROOT / "lean_validator"

def log(msg):
    print(f"  [lean-validator] {msg}")

def validate_semantics_with_lean(lean_file_path: str) -> dict:
    """
    Запускает Lean 4 для проверки сгенерированного файла.
    Ожидает формат вывода JSON для машиночитаемости.
    """
    
    lake_cmd = "lake"
    elan_bin = Path(os.path.expanduser("~")) / ".elan" / "bin" / "lake.exe"
    if elan_bin.exists():
        lake_cmd = str(elan_bin)
        
    cmd = [
        lake_cmd, "env", "lean",
        "--json",   # Заставляет Lean выдавать ошибки в JSON
        lean_file_path
    ]
    
    log(f"Running: {' '.join(cmd[-3:])}")
    
    try:
        env = os.environ.copy()
        env['PYTHONIOENCODING'] = 'utf-8'
        result = subprocess.run(cmd, capture_output=True, text=True, cwd=str(LEAN_DIR), encoding='utf-8', errors='replace', env=env)
    except FileNotFoundError:
        log("ERROR: Lean/Lake executable not found!")
        return {"status": "failed", "errors": [{"line": 0, "message": "Lean executable not found."}]}
    
    # Если returncode == 0, граф семантически безупречен!
    if result.returncode == 0:
        log("[OK] Lean returned exit code 0 -- no errors.")
        return {"status": "success", "errors": []}
    
    # Парсинг ошибок для возврата в систему Mathesis
    errors = []
    # Lean 4 outputs JSON on stdout, with one JSON object per line
    output = result.stdout if result.stdout.strip() else result.stderr
    
    for line in output.strip().split('\n'):
        try:
            err_data = json.loads(line)
            if err_data.get('severity') == 'error':
                # Lean 4 uses "data" field for error message text, not "message"
                message = err_data.get('data') or err_data.get('message') or '(no message)'
                errors.append({
                    "line": err_data.get('pos', {}).get('line'),
                    "message": message
                })
        except json.JSONDecodeError:
            continue
            
    if not errors and result.returncode != 0:
        errors.append({"line": 0, "message": f"Lean failed but no JSON errors found. Output: {output[:500]}"})
    
    log(f"[FAIL] Found {len(errors)} error(s). First: {errors[0]['message'][:100] if errors else 'N/A'}")
    return {"status": "failed", "errors": errors}

if __name__ == "__main__":
    import sys
    if len(sys.argv) > 1:
        res = validate_semantics_with_lean(sys.argv[1])
        print(json.dumps(res, indent=2, ensure_ascii=False))
    else:
        print("Usage: python lean_validator.py <path_to_lean_file>")
