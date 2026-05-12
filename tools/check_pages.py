import fitz
from pathlib import Path
import re

PROJECT_ROOT = Path(__file__).resolve().parent.parent
pdf_path = PROJECT_ROOT / "Books" / "Zorich, V.A. - Mathematical Analysis Vol 2 - (RU) - [9th ed].pdf"
doc = fitz.open(str(pdf_path))
f = open(PROJECT_ROOT / "tools" / "matches.txt", "w", encoding="utf-8")

for p in range(1, len(doc) + 1):
    text = doc[p - 1].get_text("text")
    text = re.sub(r'\s+', ' ', text)
    
    matches = list(re.finditer(r'(.{0,60}аналитическ.{0,20}функци.{0,60})', text, re.IGNORECASE))
    if not matches:
        matches = list(re.finditer(r'(.{0,60}функци.{0,20}аналитическ.{0,60})', text, re.IGNORECASE))
        
    if matches:
        f.write(f"--- PAGE {p} ---\n")
    if matches:
        for m in matches:
            f.write(f"  Match: ...{m.group(1)}...\n")
    else:
        f.write("  Roots found, but not close enough to each other.\n")
    f.write("\n")

doc.close()
f.close()
