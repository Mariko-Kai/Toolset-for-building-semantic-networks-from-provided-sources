import os
import sys
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(PROJECT_ROOT))

from tools.canonical_synthesizer import sanitize_terminal_entityrefs

CONTENT_DIR = PROJECT_ROOT / "content"

def main():
    print("Starting batch migration: sanitizing terminal entityrefs...")
    
    modified_files = []
    
    for root, dirs, files in os.walk(CONTENT_DIR):
        # Skip the terminals directory itself
        if 'terminals' in Path(root).parts:
            continue
            
        for file in files:
            if file.endswith('.tex'):
                file_path = Path(root) / file
                
                with open(file_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                    
                sanitized_content = sanitize_terminal_entityrefs(content)
                
                if sanitized_content != content:
                    with open(file_path, 'w', encoding='utf-8') as f:
                        f.write(sanitized_content)
                    modified_files.append(file_path)
                    print(f"[MODIFIED] {file_path.relative_to(PROJECT_ROOT)}")
                    
    print(f"\nMigration complete. {len(modified_files)} files modified.")

if __name__ == "__main__":
    main()
