import sys
from pathlib import Path

PROJECT_ROOT = Path("f:/Universe/Projects/Учебник по матанализу")
sys.path.append(str(PROJECT_ROOT / "tools"))

import autonomous_bfs

print("Testing Ollama via autonomous_bfs...")
try:
    keywords = autonomous_bfs.generate_search_keywords("obj-test-entity")
    print("Success! Response:")
    print(keywords)
except Exception as e:
    print(f"Failed: {e}")
