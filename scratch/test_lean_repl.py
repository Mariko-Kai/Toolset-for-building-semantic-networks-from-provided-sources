import subprocess
import json
import os
from pathlib import Path
import threading

LEAN_DIR = Path("f:/Universe/Projects/Учебник по матанализу/lean_validator")

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

class LeanReplManager:
    _instance = None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = cls()
        return cls._instance

    def __init__(self):
        self.process = None
        self.base_env = None
        self.lake_cmd = _get_lake_cmd()
        self._start_repl()

    def _start_repl(self):
        env = os.environ.copy()
        env['PYTHONIOENCODING'] = 'utf-8'
        self.process = subprocess.Popen(
            [self.lake_cmd, "exe", "repl"],
            cwd=str(LEAN_DIR),
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            encoding='utf-8',
            env=env,
            bufsize=1
        )
        print("[LeanReplManager] Started repl process")
        
        # Initialize Mathlib environment
        resp = self.send({"cmd": "import Mathlib\n"})
        print(f"[LeanReplManager] Import Mathlib response: {resp}")
        if "env" in resp:
            self.base_env = resp["env"]
            print(f"[LeanReplManager] Base env acquired: {self.base_env}")
        else:
            print("[LeanReplManager] Failed to get base env for Mathlib")

    def _read_json(self):
        """Reads JSON from stdout which might be pretty-printed or single-line."""
        # Simple JSON parser that counts braces.
        braces = 0
        in_string = False
        escape = False
        content = ""
        while True:
            char = self.process.stdout.read(1)
            if not char:
                raise EOFError("Lean REPL closed stdout")
            content += char
            
            if not in_string:
                if char == '{':
                    braces += 1
                elif char == '}':
                    braces -= 1
                    if braces == 0:
                        break
                elif char == '"':
                    in_string = True
            else:
                if escape:
                    escape = False
                elif char == '\\':
                    escape = True
                elif char == '"':
                    in_string = False
                    
        return json.loads(content)

    def send(self, req: dict):
        # The API states "Commands should be separated by blank lines."
        # Actually it means we send JSON, then two newlines? Or just \n\n?
        self.process.stdin.write(json.dumps(req) + "\n\n")
        self.process.stdin.flush()
        return self._read_json()

    def restart(self):
        if self.process:
            self.process.kill()
        self._start_repl()

if __name__ == "__main__":
    repl = LeanReplManager.get_instance()
    res = repl.send({"cmd": "def f (x : Nat) := x + 1", "env": repl.base_env})
    print(res)
