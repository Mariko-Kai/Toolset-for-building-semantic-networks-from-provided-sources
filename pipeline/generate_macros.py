import os
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONTENT_DIR = PROJECT_ROOT / "content"
OUTPUT_FILE = CONTENT_DIR / "mathesis_macros.sty"

# Standard LaTeX/TeX commands that must NEVER be redefined by auto-generated macros.
# If a .tex entity file has `% macro: \mathrm{...}` the regex will extract "mathrm",
# which would catastrophically overwrite the real \mathrm and break compilation.
RESERVED_LATEX_COMMANDS = {
    # Font-switching commands
    "mathrm", "mathbf", "mathit", "mathsf", "mathtt", "mathcal", "mathbb",
    "mathfrak", "mathscr", "mathnormal",
    "textbf", "textit", "texttt", "textrm", "textsf", "textsc",
    "emph", "bfseries", "itshape",
    # Core structural commands
    "begin", "end", "left", "right", "bigl", "bigr", "Bigl", "Bigr",
    "biggl", "biggr", "Biggl", "Biggr",
    "newcommand", "renewcommand", "providecommand", "def", "let",
    "usepackage", "documentclass", "input", "include",
    # Math operators & symbols
    "frac", "sqrt", "sum", "prod", "int", "lim", "inf", "sup",
    "sin", "cos", "tan", "log", "exp", "min", "max",
    "forall", "exists", "in", "subset", "subseteq", "cup", "cap",
    "to", "rightarrow", "Rightarrow", "implies", "iff",
    "land", "lor", "lnot", "neg",
    "cdot", "times", "circ", "oplus", "otimes",
    "leq", "geq", "neq", "equiv", "approx", "sim",
    "alpha", "beta", "gamma", "delta", "epsilon", "varepsilon",
    "zeta", "eta", "theta", "iota", "kappa", "lambda", "mu",
    "nu", "xi", "pi", "rho", "sigma", "tau", "upsilon",
    "phi", "varphi", "chi", "psi", "omega",
    "Gamma", "Delta", "Theta", "Lambda", "Xi", "Pi", "Sigma",
    "Upsilon", "Phi", "Psi", "Omega",
    # Formatting & spacing
    "quad", "qquad", "hspace", "vspace", "par", "item",
    "section", "subsection", "chapter", "label", "ref", "cite",
    "text", "operatorname", "stackrel", "underset", "overset",
    "overline", "underline", "hat", "tilde", "bar", "vec", "dot",
    "coloneqq",
}

PAIRED_DELIMITERS = [
    (r'^\|#1\|$', r'\lvert', r'\rvert'),
    (r'^\\\|#1\\\|$', r'\|', r'\|'),
    (r'^\(#1\)$', r'(', r')'),
    (r'^\[#1\]$', r'[', r']'),
    (r'^\\\{#1\\\}$', r'\{', r'\}'),
    (r'^<#1>$', r'\langle', r'\rangle'),
]

def generate_macros():
    macros = []
    skipped = []

    macros.append(r"\NeedsTeXFormat{LaTeX2e}")
    macros.append(r"\ProvidesPackage{mathesis_macros}[Auto-generated semantic macros]")
    macros.append("")
    macros.append(r"% --- Auto-generated Semantic Entity Macros ---")
    macros.append("")

    for root, _, files in os.walk(CONTENT_DIR):
        for file in files:
            if not file.endswith('.tex'):
                continue
            filepath = Path(root) / file
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
            except Exception:
                continue

            match_id = re.search(r"^%\s*entity-id:\s*(.+)$", content, re.MULTILINE)
            match_macro = re.search(r"^%\s*macro:\s*\\([a-zA-Z]+)", content, re.MULTILINE)

            if not match_id or not match_macro:
                continue

            entity_id = match_id.group(1).strip()
            macro_name = match_macro.group(1).strip()

            # --- Guard: skip reserved LaTeX commands ---
            if macro_name in RESERVED_LATEX_COMMANDS:
                skipped.append((file, macro_name, "reserved LaTeX command"))
                print(f"  [SKIP] {file}: macro \\{macro_name} is a reserved LaTeX command, skipping")
                continue

            # --- Guard: skip compound macro expressions like \mathrm{Name} ---
            # If the full macro line has braces after the command name, it's not
            # a simple macro name but an expression that was incorrectly placed
            # in the metadata.
            macro_line_end = content.index('\n', match_macro.start()) if '\n' in content[match_macro.start():] else len(content)
            macro_line_tail = content[match_macro.end():macro_line_end]
            if '{' in macro_line_tail:
                skipped.append((file, macro_name, "embedded braces in macro line"))
                print(f"  [SKIP] {file}: macro line contains embedded braces (\\{macro_name}{{...}}), skipping")
                continue

            match_args = re.search(r"^%\s*args:\s*(\d+)", content, re.MULTILINE)
            args_count = int(match_args.group(1)) if match_args else 0

            match_notation = re.search(r"^%\s*notation:\s*(.+)$", content, re.MULTILINE)
            notation = match_notation.group(1).strip() if match_notation else ""

            if args_count == 0:
                if notation:
                    macros.append(rf"\newcommand{{\{macro_name}}}{{\mathrel{{}}\hyperlink{{{entity_id}}}{{{notation}}}\mathrel{{}}}}")
                else:
                    macros.append(rf"\newcommand{{\{macro_name}}}{{\hyperlink{{{entity_id}}}{{?}}}}")
            elif args_count == 1:
                # Check for paired notation
                is_paired = False
                for pattern, left_delim, right_delim in PAIRED_DELIMITERS:
                    if re.match(pattern, notation):
                        is_paired = True
                        macros.append(rf"\newcommand{{\{macro_name}}}[1]{{\mathopen{{\hyperlink{{{entity_id}}}{{\left{left_delim}\vphantom{{#1}}\right.}}}}#1\mathclose{{\hyperlink{{{entity_id}}}{{\left.\vphantom{{#1}}\right{right_delim}}}}}}}")
                        break

                if not is_paired:
                    if notation:
                        # Standard #1 replacement, but make sure the hyperlink wraps it all
                        macros.append(rf"\newcommand{{\{macro_name}}}[1]{{\hyperlink{{{entity_id}}}{{{notation}}}}}")
                    else:
                        macros.append(rf"\newcommand{{\{macro_name}}}[1]{{\hyperlink{{{entity_id}}}{{#1}}}}")
            else:
                # Fallback for >1 args, just wrap the first arg or notation
                if notation:
                    macros.append(rf"\newcommand{{\{macro_name}}}[{args_count}]{{\hyperlink{{{entity_id}}}{{{notation}}}}}")
                else:
                    macros.append(rf"\newcommand{{\{macro_name}}}[{args_count}]{{\hyperlink{{{entity_id}}}{{#1}}}}")

    with open(OUTPUT_FILE, 'w', encoding='utf-8') as f:
        f.write("\n".join(macros) + "\n")

    print(f"[generate_macros] Generated mathesis_macros.sty with {len(macros)-5} macros.")
    if skipped:
        print(f"[generate_macros] Skipped {len(skipped)} invalid macro entries:")
        for fname, mname, reason in skipped:
            print(f"  - {fname}: \\{mname} ({reason})")

if __name__ == "__main__":
    generate_macros()
