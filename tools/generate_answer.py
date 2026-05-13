import os
import re
from pathlib import Path
import subprocess
import shutil

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONTENT_DIR = PROJECT_ROOT / "content"

BOOK_CITATIONS = {
    "zorich-1": "Зорич В.А., Математический анализ, Том I",
    "zorich-2": "Зорич В.А., Математический анализ, Том II",
}

NL_DESCRIPTIONS = {
    "op-riemann-integral": r"Определенным интегралом Римана от функции $f(x)$ на отрезке $[a,b]$ называется предел интегральных сумм $\sum f(\xi_i) \Delta x_i$ при стремлении максимальной длины частичного отрезка $\lambda(P)$ к нулю, независимо от выбора разбиения $P$ и промежуточных точек $\xi_i$.",
    "op-darboux-integral": r"Функция $f$ называется интегрируемой по Дарбу на отрезке $[a,b]$, если нижний интеграл Дарбу $\underline{I}$ равен верхнему интегралу Дарбу $\overline{I}$. Их общее значение называется интегралом Дарбу функции $f$ по отрезку $[a,b]$.",
    "op-lower-darboux-sum": r"Нижней суммой Дарбу называется сумма произведений инфимумов функции $f$ на каждом отрезке разбиения $[x_{i-1}, x_i]$ на длину этого отрезка $\Delta x_i$.",
    "op-upper-darboux-sum": r"Верхней суммой Дарбу называется сумма произведений супремумов функции $f$ на каждом отрезке разбиения $[x_{i-1}, x_i]$ на длину этого отрезка $\Delta x_i$.",
    "obj-partition": r"Разбиением отрезка $[a,b]$ называется конечное множество точек $P = \{x_0, x_1, \ldots, x_n\}$, таких что $a = x_0 < x_1 < \cdots < x_n = b$.",
    "obj-function": r"Функция $f$ из множества $X$ в множество $Y$ — это правило (или бинарное отношение), по которому каждому элементу $x \in X$ ставится в соответствие ровно один элемент $y \in Y$. Формально, это подмножество декартова произведения $X \times Y$, обладающее свойством однозначности.",
    "obj-real-numbers": r"Множество вещественных чисел $\mathbb{R}$ — это непрерывная числовая прямая. Формально $\mathbb{R}$ задается как полное (непрерывное) архимедово упорядоченное поле. В нем можно складывать, умножать, сравнивать элементы, и в нем нет «дырок» (каждое ограниченное сверху подмножество имеет точную верхнюю грань).",
    "obj-set": r"Множество — базовое, неопределяемое напрямую понятие математики. Множество представляет собой совокупность объектов произвольной природы, называемых его элементами. Все свойства множеств строго выводятся из аксиом системы Цермело-Френкеля (ZFC).",
}

TEMPLATE = r"""\documentclass{report}
\usepackage{mathesis}
\usepackage[utf8]{inputenc}
\usepackage[russian]{babel}

\begin{document}

%(content)s

\end{document}
"""

def parse_canonical(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        text = f.read()
    
    source_match = re.search(r'% defined-in: (.*)', text)
    source = source_match.group(1).strip() if source_match else "Unknown"
    
    id_match = re.search(r'% entity-id: (.*)', text)
    entity_id = id_match.group(1).strip() if id_match else "unknown"
    
    type_match = re.search(r'% entity-type: (.*)', text)
    entity_type = type_match.group(1).strip() if type_match else "unknown"
    
    section_match = re.search(r'\\section\{(.*?)\}', text)
    title = section_match.group(1).strip() if section_match else entity_id
    
    formulas = re.findall(r'\\\[(.*?)\\\]', text, re.DOTALL)
    
    deps = list(set(re.findall(r'\\entityref\{([^}]+)\}', text)))
    
    return {
        "id": entity_id,
        "type": entity_type,
        "title": title,
        "source": source,
        "formulas": formulas,
        "deps": deps,
        "path": filepath
    }

def find_entity_file(entity_id):
    pattern = f"[{entity_id}].tex"
    for dirpath, _, filenames in os.walk(CONTENT_DIR):
        for fn in filenames:
            if pattern in fn:
                return Path(dirpath) / fn
    return None

def bfs_collect(root_id):
    visited = []
    queue = [root_id]
    seen = set()
    
    while queue:
        eid = queue.pop(0)
        if eid in seen:
            continue
        seen.add(eid)
        
        fpath = find_entity_file(eid)
        if fpath is None:
            print(f"  [SKIP] {eid} — file not found in content/")
            continue
        
        data = parse_canonical(fpath)
        visited.append(data)
        print(f"  [BFS] {eid} -> deps: {data['deps']}")
        
        for dep in data['deps']:
            if dep not in seen:
                queue.append(dep)
    
    return visited

import argparse

def main():
    parser = argparse.ArgumentParser(description="Dynamic LaTeX Compiler via BFS")
    parser.add_argument('--root', type=str, default='thm-newton-leibniz', help='The root entity ID to start BFS from')
    args = parser.parse_args()
    
    root_id = args.root
    
    print(f"=== DYNAMIC COMPILER: Сборка графа для {root_id} (BFS) ===\n")
    
    entities = bfs_collect(root_id)
    
    print(f"\nCollected {len(entities)} entities. Generating result.tex...\n")
    
    content = ""
    for data in entities:
        book_key = data["source"].split(",")[0].strip()
        citation = BOOK_CITATIONS.get(book_key, data["source"])
        page_info = data["source"]
        
        nl = NL_DESCRIPTIONS.get(data["id"], "")
        
        block = f"\\section{{{data['title']}}}\\label{{entity:{data['id']}}}\n"
        block += f"\\textbf{{Тип:}} {data['type']} \\quad "
        block += f"\\textbf{{Источник:}} {citation} ({page_info})\n\n"
        
        block += "\\textbf{Каноническая запись:}\n"
        for formula in data["formulas"]:
            block += f"\\[\n{formula}\n\\]\n"
        
        if nl:
            block += f"\n\\textbf{{Естественный язык:}}\n{nl}\n"
        
        block += "\n\\vspace{1em}\n\\hrule\n\\vspace{1em}\n\n"
        content += block
    
    result_tex = PROJECT_ROOT / "result.tex"
    with open(result_tex, "w", encoding="utf-8") as f:
        f.write(TEMPLATE % {"content": content})
    
    print(f"Generated {result_tex}")
    
    if not (PROJECT_ROOT / "mathesis.sty").exists():
        shutil.copy(CONTENT_DIR / "mathesis.sty", PROJECT_ROOT / "mathesis.sty")
    
    print("Compiling result.pdf (pass 1)...")
    os.chdir(PROJECT_ROOT)
    subprocess.run(
        ["pdflatex", "-interaction=nonstopmode", "result.tex"],
        capture_output=True, text=True
    )
    
    print("Compiling result.pdf (pass 2 for references)...")
    result = subprocess.run(
        ["pdflatex", "-interaction=nonstopmode", "result.tex"],
        capture_output=True, text=True
    )
    
    if "Output written on result.pdf" in result.stdout:
        print("PDF compilation successful! -> result.pdf")
    else:
        print("PDF compilation issue. Last 500 chars of log:")
        print(result.stdout[-500:])

if __name__ == "__main__":
    main()
