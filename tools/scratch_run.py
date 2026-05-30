import subprocess

command = [
    ".\\.venv\\Scripts\\python.exe",
    "tools\\ollama_wrapper.py",
    "определение интеграла Римана",
    "--model",
    "llava-phi3:latest"
]

print("Running command:", " ".join(command))
result = subprocess.run(command, capture_output=True, text=True, encoding='utf-8')
print("STDOUT:")
print(result.stdout)
print("STDERR:")
print(result.stderr)
print("Return code:", result.returncode)
