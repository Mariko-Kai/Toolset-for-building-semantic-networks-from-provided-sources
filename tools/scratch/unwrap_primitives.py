"""
Removes incorrect entityref wrappers around ZFC primitives (\in, \notin, \subset)
that were introduced by link_content.py before the fix.
"""
import re
import os
from pathlib import Path

CONTENT_DIR = Path("f:/Universe/Projects/Учебник по матанализу/content")

# These are ZFC primitives that should NEVER be wrapped
PRIMITIVES_TO_UNWRAP = [
    # Pattern: \entityref{obj-set}{\in}  ->  \in
    (r'\\entityref\{obj-set\}\{(\\in|\\notin)\}', r'\1'),
    # Pattern: \entityref{obj-subset}{\subset}  ->  \subset
    (r'\\entityref\{obj-subset\}\{(\\subset)\}', r'\1'),
]

changed = 0
for tex_file in CONTENT_DIR.rglob("*.tex"):
    text = tex_file.read_text(encoding="utf-8")
    original = text
    for pattern, replacement in PRIMITIVES_TO_UNWRAP:
        text = re.sub(pattern, replacement, text)
    if text != original:
        tex_file.write_text(text, encoding="utf-8")
        print(f"Fixed: {tex_file.relative_to(CONTENT_DIR.parent)}")
        changed += 1

print(f"\nTotal files fixed: {changed}")
