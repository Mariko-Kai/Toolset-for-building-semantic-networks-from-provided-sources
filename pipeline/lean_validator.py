"""
Lean Validator v2 — Robust Lean 4 Validation
=============================================
Validates generated Lean 4 files using Lake/Lean.
Handles Mathlib-heavy timeouts and JSON error parsing.
"""
import subprocess
import json
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
LEAN_DIR = PROJECT_ROOT / "lean_validator"

VALIDATION_TIMEOUT = 300  # seconds — Mathlib imports are slow


def log(msg):
    try:
        print(f"  [lean-validator] {msg}")
    except UnicodeEncodeError:
        safe = str(msg).encode('ascii', errors='replace').decode('ascii')
        print(f"  [lean-validator] {safe}")


def check_lean_environment() -> bool:
    """Verifies that Lean/Lake toolchain is available."""
    lake_cmd = _get_lake_cmd()
    try:
        result = subprocess.run(
            [lake_cmd, "--version"],
            capture_output=True, text=True, timeout=10
        )
        if result.returncode == 0:
            log(f"Toolchain: {result.stdout.strip()}")
            return True
    except (FileNotFoundError, subprocess.TimeoutExpired):
        pass

    log("ERROR: Lean/Lake toolchain not found!")
    return False


def _get_lake_cmd() -> str:
    """Resolves lake executable path."""
    # Try multiple home directory resolution strategies (Windows compatibility)
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
            # Also try without .exe (Linux/macOS)
            elan_bin_nix = Path(home) / ".elan" / "bin" / "lake"
            if elan_bin_nix.exists():
                return str(elan_bin_nix)
    return "lake"


def validate_semantics_with_lean(lean_file_path: str) -> dict:
    """
    Runs Lean 4 on the given file and returns validation result.
    
    Returns:
        {"status": "success"|"failed"|"timeout", "errors": [...]}
    """
    lean_file = Path(lean_file_path)
    if not lean_file.exists():
        return {"status": "failed", "errors": [{"line": 0, "message": f"File not found: {lean_file}"}]}

    # Verify toolchain files exist
    toolchain_file = LEAN_DIR / "lean-toolchain"
    if not toolchain_file.exists():
        log("WARNING: lean-toolchain not found in lean_validator/")
        return {"status": "failed", "errors": [{"line": 0, "message": "Missing lean-toolchain"}]}

    lake_cmd = _get_lake_cmd()
    cmd = [lake_cmd, "env", "lean", "--json", str(lean_file)]

    log(f"Validating: {lean_file.name}")

    try:
        env = os.environ.copy()
        env['PYTHONIOENCODING'] = 'utf-8'

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(LEAN_DIR),
            encoding='utf-8',
            errors='replace',
            env=env,
            timeout=VALIDATION_TIMEOUT
        )
    except subprocess.TimeoutExpired:
        log(f"TIMEOUT after {VALIDATION_TIMEOUT}s")
        return {"status": "timeout", "errors": [{"line": 0, "message": f"Lean validation timed out after {VALIDATION_TIMEOUT}s"}]}
    except FileNotFoundError:
        log("ERROR: Lean/Lake executable not found!")
        return {"status": "failed", "errors": [{"line": 0, "message": "Lean executable not found."}]}

    # Success
    if result.returncode == 0:
        log("[OK] No errors.")
        return {"status": "success", "errors": []}

    # Parse errors and info from JSON output
    errors, info = _parse_lean_output(result.stdout, result.stderr)

    if not errors and result.returncode != 0:
        # Lean failed but produced no parseable JSON errors
        output = (result.stdout + result.stderr)[:500]
        errors = [{"line": 0, "message": f"Lean exited with code {result.returncode}. Output: {output}"}]

    log(f"[FAIL] {len(errors)} error(s). First: {errors[0]['message'][:120] if errors else 'N/A'}")
    return {"status": "failed", "errors": errors}


def _parse_lean_output(stdout: str, stderr: str) -> tuple[list, list]:
    """Parses Lean 4 JSON error and info output."""
    errors = []
    infos = []
    output = stdout if stdout.strip() else stderr

    for line in output.strip().split('\n'):
        line = line.strip()
        if not line:
            continue
        try:
            err_data = json.loads(line)
            severity = err_data.get('severity')
            message = err_data.get('data') or err_data.get('message') or '(no message)'
            
            entry = {
                "line": err_data.get('pos', {}).get('line', 0),
                "column": err_data.get('pos', {}).get('column', 0),
                "message": str(message)[:500]  # Truncate long messages
            }
            
            if severity == 'error':
                errors.append(entry)
            elif severity == 'information':
                infos.append(entry)
        except json.JSONDecodeError:
            continue

    return errors, infos


def validate_entity(entity_id: str, lean_code: str) -> dict:
    """
    Convenience function: writes lean_code to a temp file, validates, cleans up.
    """
    temp_file = LEAN_DIR / "TempValidation.lean"
    try:
        with open(temp_file, 'w', encoding='utf-8') as f:
            f.write("import Mathlib\n\n")
            f.write(f"-- Validation for {entity_id}\n")
            f.write(lean_code + "\n")

        return validate_semantics_with_lean(str(temp_file))
    finally:
        try:
            temp_file.unlink()
        except Exception:
            pass

def discover_mathlib_signatures(terms: list[str]) -> list[str]:
    """
    Writes a temp file with `#check` for each term and returns the signatures found.
    """
    if not terms:
        return []
        
    temp_file = LEAN_DIR / "TempDiscovery.lean"
    try:
        with open(temp_file, 'w', encoding='utf-8') as f:
            f.write("import Mathlib\n\n")
            for term in terms:
                f.write(f"#check {term}\n")

        lake_cmd = _get_lake_cmd()
        cmd = [lake_cmd, "env", "lean", "--json", str(temp_file)]
        
        env = os.environ.copy()
        env['PYTHONIOENCODING'] = 'utf-8'

        result = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            cwd=str(LEAN_DIR),
            encoding='utf-8',
            errors='replace',
            env=env,
            timeout=180
        )
        
        _, infos = _parse_lean_output(result.stdout, result.stderr)
        signatures = [info['message'] for info in infos if ':' in info['message']]
        return signatures
    except Exception as e:
        log(f"Discovery error: {e}")
        return []
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
        if check_lean_environment():
            print("Lean toolchain: OK")
        else:
            print("Lean toolchain: NOT FOUND")
