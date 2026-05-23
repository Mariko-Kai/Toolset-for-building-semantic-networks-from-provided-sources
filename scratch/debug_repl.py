import subprocess

p = subprocess.Popen(["lake", "exe", "repl"], cwd="f:/Universe/Projects/Учебник по матанализу/lean_validator", stdin=subprocess.PIPE, stdout=subprocess.PIPE, stderr=subprocess.PIPE, text=True)

p.stdin.write('{"cmd": "import Mathlib\n"}\n\n')
p.stdin.flush()
p.stdout.readline()

p.stdin.write('{"cmd": "def foo : Nat := \\"hello\\"", "env": 0}\n\n')
p.stdin.flush()

for i in range(5):
    line = p.stdout.readline()
    print(f"Read: {line!r}")
    if line.strip() == "" or line.startswith('{"env"'): break

p.kill()
