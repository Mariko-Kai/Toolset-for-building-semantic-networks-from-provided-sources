import fitz, re
from pathlib import Path

PROJECT_ROOT = Path(r'f:\Universe\Projects\Учебник по матанализу')
pdf_path = PROJECT_ROOT / 'Books' / 'Zorich, V.A. - Mathematical Analysis Vol 1 - (RU) - [10th ed].pdf'

pages = [325, 326, 332, 360, 525, 566, 567, 571, 572]

doc = fitz.open(str(pdf_path))
with open(PROJECT_ROOT / 'tools' / 'darboux_context.txt', 'w', encoding='utf-8') as f:
    for p in pages:
        text = doc[p - 1].get_text('text')
        text_clean = re.sub(r'\s+', ' ', text)
        # Find matches near "дарбу" and "интеграл"
        matches = list(re.finditer(r'(.{0,120}[Дд]арбу.{0,120})', text_clean))
        f.write(f"=== PAGE {p} ===\n")
        if matches:
            for m in matches:
                f.write(f"  ...{m.group(1)}...\n")
        else:
            f.write("  (roots found but not in same context)\n")
        f.write("\n")

doc.close()
print("Done. See tools/darboux_context.txt")
