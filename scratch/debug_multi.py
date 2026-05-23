import subprocess
import json

p = subprocess.Popen(['lake', 'exe', 'repl'], stdin=subprocess.PIPE, stdout=subprocess.PIPE, text=True)

print("Started")
p.stdin.write('{"cmd": "import Mathlib\\n"}\n\n')
p.stdin.flush()
print("Sent import")
line1 = p.stdout.readline()
print(f"Read 1: {line1!r}")

print("Sending multiple checks")
p.stdin.write('{"cmd": "#check Nat.add\\n#check Real.cos", "env": 0}\n\n')
p.stdin.flush()
line2 = p.stdout.readline()
print(f"Read 2: {line2!r}")

p.kill()
