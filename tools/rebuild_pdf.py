#!/usr/bin/env python
"""Universal PDF Rebuilder Utility for Mathesis.

Walks through all entity LaTeX files in the 'content/' directory,
injects missing hypertarget anchors, sorts all entities topologically
by their mutual dependencies, rebuilds 'content/master.tex', and
compiles 'master.pdf' in the project root.
"""

import re
import subprocess
import sys
from pathlib import Path

# Setup paths relative to script location
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONTENT_DIR = PROJECT_ROOT / "content"

def inject_hypertargets():
    r"""Scan all entity .tex files and ensure they have a matching \hypertarget anchor."""
    print("1. Scanning content directory for entity files...")
    tex_files = []
    for filepath in CONTENT_DIR.rglob("*.tex"):
        if filepath.name in ("master.tex", "TEMPLATE.tex", "mathesis.sty"):
            continue
        tex_files.append(filepath)

    updated_count = 0
    for filepath in tex_files:
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                content = f.read()

            id_match = re.search(r'% entity-id:\s*(.*)', content)
            if not id_match:
                continue
            entity_id = id_match.group(1).strip()

            # If hypertarget is not in file, inject it right before \begin{
            target_str = f"\\hypertarget{{{entity_id}}}"
            if target_str not in content:
                begin_idx = content.find("\\begin{")
                if begin_idx != -1:
                    new_content = content[:begin_idx] + f"\\hypertarget{{{entity_id}}}{{}}\n" + content[begin_idx:]
                    with open(filepath, "w", encoding="utf-8") as f:
                        f.write(new_content)
                    updated_count += 1
        except Exception as e:
            print(f"   [WARN] Failed to process {filepath.name}: {e}")

    print(f"   Done! Verified {len(tex_files)} files. Injected missing targets into {updated_count} files.")

def rebuild_master_tex():
    """Build content/master.tex in topological order of dependencies."""
    print("2. Rebuilding content/master.tex...")
    master_path = CONTENT_DIR / "master.tex"

    tex_files = []
    for filepath in CONTENT_DIR.rglob("*.tex"):
        if filepath.name in ("master.tex", "TEMPLATE.tex", "mathesis.sty"):
            continue
        tex_files.append(filepath)

    nodes = {}
    file_by_id = {}

    for filepath in tex_files:
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                text = f.read()
            id_match = re.search(r'% entity-id:\s*(.*)', text)
            if not id_match:
                continue
            entity_id = id_match.group(1).strip()

            # Find dependencies
            deps = list(set(re.findall(r'\\entityref\{([^{}]+)\}', text)))

            # Find abstract macro dependencies
            macro_deps = {
                r'\mNorm': 'op-norm-abstract',
                r'\mAbs': 'op-abs-abstract',
                r'\mInner': 'op-inner-product-abstract',
                r'\mDist': 'op-dist-abstract',
                r'\mSup': 'op-supremum',
                r'\mInf': 'op-infimum',
                r'\mDeriv': 'op-derivative',
                r'\mIntegral': 'op-integral',
            }
            for macro, default_id in macro_deps.items():
                if macro in text:
                    deps.append(default_id)

            deps = list(set(deps))
            nodes[entity_id] = deps
            file_by_id[entity_id] = filepath
        except Exception as e:
            print(f"   [WARN] Failed to parse dependencies for {filepath.name}: {e}")

    # Topological Sort (DFS)
    visited = set()
    temp_visited = set()
    order = []

    def visit(node):
        if node in temp_visited:
            return
        if node not in visited:
            temp_visited.add(node)
            if node in nodes:
                for dep in nodes[node]:
                    if dep in nodes:
                        visit(dep)
            temp_visited.remove(node)
            visited.add(node)
            order.append(node)

    for node in nodes:
        visit(node)

    input_lines = []
    for entity_id in order:
        filepath = file_by_id[entity_id]
        rel_path = filepath.relative_to(PROJECT_ROOT).as_posix()
        input_lines.append(f"\\input{{{rel_path}}}")

    master_template = r"""\documentclass{report}
\usepackage{mathesis}
\usepackage[utf8]{inputenc}
\usepackage[russian]{babel}

\begin{document}

%(inputs)s

\end{document}
"""
    inputs_content = "\n".join(input_lines)
    with open(master_path, "w", encoding="utf-8") as f:
        f.write(master_template % {"inputs": inputs_content})
    print(f"   Success! Generated master.tex with {len(order)} topologically sorted entities.")

def compile_pdf():
    """Compile content/master.tex to master.pdf using pdflatex."""
    print("3. Compiling PDF using pdflatex...")
    import shutil
    sty_src = CONTENT_DIR / "mathesis.sty"
    macros_src = CONTENT_DIR / "mathesis_macros.sty"
    sty_dest = PROJECT_ROOT / "mathesis.sty"
    macros_dest = PROJECT_ROOT / "mathesis_macros.sty"

    shutil.copy2(sty_src, sty_dest)
    shutil.copy2(macros_src, macros_dest)

    cmd = ["pdflatex", "-interaction=nonstopmode", "content/master.tex"]
    try:
        process = subprocess.run(
            cmd,
            stdout=subprocess.PIPE,
            stderr=subprocess.STDOUT,
            cwd=str(PROJECT_ROOT),
            text=True
        )
        if sty_dest.exists():
            sty_dest.unlink()
        if macros_dest.exists():
            macros_dest.unlink()

        if process.returncode == 0 or (PROJECT_ROOT / "master.pdf").exists():
            print("   Success! Generated master.pdf in the project root.")
            shutil.copy2(PROJECT_ROOT / "master.pdf", CONTENT_DIR / "master.pdf")
            print("   Synced master.pdf to content/master.pdf.")
        else:
            print("   [ERROR] pdflatex compilation failed!")
            print(process.stdout)
            sys.exit(1)
    except Exception as e:
        if sty_dest.exists():
            sty_dest.unlink()
        if macros_dest.exists():
            macros_dest.unlink()
        print(f"   [ERROR] Failed to run pdflatex: {e}")
        sys.exit(1)

def main():
    print("==================================================")
    print("Mathesis PDF Rebuilder Utility")
    print("==================================================")
    inject_hypertargets()
    rebuild_master_tex()
    compile_pdf()
    print("==================================================")
    print("Rebuild complete! PDF is up to date.")
    print("==================================================")

if __name__ == "__main__":
    main()
