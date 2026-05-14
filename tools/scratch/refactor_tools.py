import os
import re
from pathlib import Path

def refactor():
    root = Path(r"f:\Universe\Projects\Учебник по матанализу")
    for p in root.rglob('*'):
        # Skip hidden and venv directories
        if any(part.startswith('.') for part in p.parts) or 'venv' in p.parts or 'node_modules' in p.parts:
            continue
            
        if p.is_file() and p.suffix in ['.py', '.tex', '.sh', '.ps1', '.json', '.md']:
            if "pipeline" in str(p): # skip __pycache__ etc if they exist
                if "__pycache__" in str(p): continue
            
            try:
                content = p.read_text(encoding='utf-8')
                if 'pipeline' in content:
                    # Replace imports
                    new_content = content.replace('from pipeline.', 'from pipeline.')
                    new_content = new_content.replace('import pipeline.', 'import pipeline.')
                    
                    # Replace path joins
                    new_content = new_content.replace('/pipeline/', '/pipeline/')
                    new_content = new_content.replace('\\pipeline\\', '\\pipeline\\')
                    new_content = new_content.replace('\"tools\"', '\"pipeline\"')
                    new_content = new_content.replace('\'tools\'', '\'pipeline\'')
                    
                    # Replace manual path joins in strings
                    new_content = new_content.replace('pipeline/', 'pipeline/')
                    
                    if content != new_content:
                        p.write_text(new_content, encoding='utf-8')
                        print(f"Updated: {p.relative_to(root)}")
            except Exception as e:
                print(f"Error processing {p}: {e}")

if __name__ == "__main__":
    refactor()
