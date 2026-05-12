import subprocess
import sys

start_page = 96
end_page = 149
chunk_size = 2

for i in range(start_page, end_page + 1, chunk_size):
    chunk_end = min(i + chunk_size - 1, end_page)
    pages_arg = f"{i}-{chunk_end}"
    print(f"\n--- Running agent for pages {pages_arg} ---")
    result = subprocess.run(
        ["python", "tools/agent/agent.py", "--pages", pages_arg],
        cwd="f:/Universe/Projects/Учебник по матанализу",
        capture_output=False
    )
    if result.returncode != 0:
        print(f"Agent failed on chunk {pages_arg}")
        sys.exit(1)

print("Batch processing complete.")
