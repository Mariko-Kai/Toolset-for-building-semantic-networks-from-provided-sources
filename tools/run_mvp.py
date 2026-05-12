import os
import subprocess
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONTENT_DIR = PROJECT_ROOT / "content"

TEMPLATE = r"""\documentclass{report}
\usepackage{mathesis}
\usepackage[utf8]{inputenc}
\usepackage[russian]{babel}

\begin{document}
%(content)s
\end{document}
"""

ENTITIES = {
    "analytic_function": {
        "title": "Аналитическая функция",
        "tex": r"""% defined-in: zorich-2
% entity-type: definition
% entity-id: analytic_function

\begin{object}[Аналитическая функция]
Функция $f: D \to \mathbb{R}$ (где $D \subset \mathbb{R}$) называется аналитической в точке $x_0 \in D$, если существует \entityref{neighborhood}{окрестность} $U(x_0)$ этой точки, в которой функция $f$ может быть представлена сходящимся к ней \entityref{taylor_series}{рядом Тейлора}:
\[
\mForall x \in U(x_0): f(x) = \sum_{k=0}^{\infty} \frac{f^{(k)}(x_0)}{k!} (x - x_0)^k
\]
\end{object}
"""
    },
    "taylor_series": {
        "title": "Ряд Тейлора",
        "tex": r"""% defined-in: zorich-1
% entity-type: definition
% entity-id: taylor_series

\begin{object}[Ряд Тейлора]
Пусть функция $f$ имеет производные всех порядков в точке $x_0$. Степенной ряд вида
\[
\sum_{k=0}^{\infty} \frac{f^{(k)}(x_0)}{k!} (x - x_0)^k
\]
называется рядом Тейлора функции $f$ в точке $x_0$.
\end{object}
"""
    },
    "neighborhood": {
        "title": "Окрестность точки",
        "tex": r"""% defined-in: zorich-1
% entity-type: definition
% entity-id: neighborhood

\begin{object}[Окрестность точки]
Окрестностью $U(x_0)$ точки $x_0 \in \mathbb{R}$ называется любой интервал $(a, b)$, содержащий точку $x_0$. 
Часто рассматривают $\varepsilon$-окрестность:
\[
U_\varepsilon(x_0) = \{x \in \mathbb{R} \mid |x - x_0| < \varepsilon\}
\]
\end{object}
"""
    }
}

def main():
    print("=== QUERY AGENT MVP TEST RUN ===")
    print("1. Searching registry for 'аналитическая функция'...")
    print("   [Simulation] Found in: zorich-2 (page 340).")
    
    print("2. Extracting and formalizing definition...")
    
    # Save entities to content directory
    CONTENT_DIR.mkdir(exist_ok=True)
    master_content = ""
    
    for entity_id, data in ENTITIES.items():
        print(f"   Generating formal LaTeX for: {data['title']}")
        file_path = CONTENT_DIR / f"{data['title']} [{entity_id}].tex"
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(data["tex"])
        master_content += data["tex"] + "\n\n"
        
    # Create master doc
    master_tex = TEMPLATE % {"content": master_content}
    master_path = CONTENT_DIR / "master.tex"
    with open(master_path, "w", encoding="utf-8") as f:
        f.write(master_tex)
        
    print("3. Compiling PDF...")
    # Run pdflatex from CONTENT_DIR so it finds mathesis.sty
    os.chdir(CONTENT_DIR)
    result = subprocess.run(["pdflatex", "-interaction=nonstopmode", "master.tex"], capture_output=True, text=True)
    
    if result.returncode == 0:
        print("PDF compilation successful! -> master.pdf")
    else:
        print("PDF compilation failed!")
        print(result.stdout)
        
    print("=== MVP TEST RUN COMPLETE ===")

if __name__ == "__main__":
    main()
