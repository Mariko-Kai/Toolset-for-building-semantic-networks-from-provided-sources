import re

with open("test_regex.txt", "r", encoding="utf-8") as f:
    text = f.read()

print("Original length:", len(text))
m = re.search(r'\\textbf\{Описание:\}\s*.*?(?=\\begin\{(?:object|axiom|theorem|operation|property)\}|\\textbf\{(?!Описание)\}|\\section|$)', text, flags=re.DOTALL)
print("Match length:", len(m.group(0)) if m else 0)
print("Match:", repr(m.group(0)) if m else None)
