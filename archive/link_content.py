import os
import re
import sys
import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(r"f:\Universe\Projects\Учебник по матанализу")
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.terminals import ALL_TERMINALS
CONTENT_DIR = PROJECT_ROOT / "content"
DB_PATH = PROJECT_ROOT / "mathesis_index.db"

# Standard LaTeX formatting/layout commands to ignore (the whitelist)
FORMATTING_COMMANDS = {
    'left', 'right', 'quad', 'qquad', 'colon', 'limits', 'text', 'mathrm', 'mathbb', 
    'mathcal', 'mathscr', 'begin', 'end', 'label', 'frac', 'sqrt', 'bar', 'tilde', 
    'hat', 'vec', 'overline', 'underline', 'textit', 'textbf', 'dots', 'cdots', 
    'vdots', 'ddots', 'square', 'hbar', 'prime', 'mathbf', 'sbox', 'hbox', 'vbox', 
    'textsf', 'texttt', 'cdot', 'ldots', 'section', 'subsection', 'subsubsection',
    'input', 'usepackage', 'documentclass', 'label', 'ref', 'cref', 'Cref', 'cite', 
    'hspace', 'vspace', 'noindent', 'newline', 'break', 'hfill', 'vfill', 'leftskip', 
    'rightskip', 'par', 'item', 'sub', 'limits', 'tag', 'nonumber', 'nonumbering', 
    'eqref', 'label', 'ref', 'label', 'begin', 'end', 'proof', 'theorem', 'object', 
    'property', 'operation', 'axiom', 'lemma', 'corollary', 'aligned', 'equation', 
    'split', 'cases', 'array', 'matrix', 'pmatrix', 'vmatrix', 'bmatrix', 'Bmatrix',
    'def', 'newcommand', 'renewcommand'
}

# Greek variables to ignore (usually used as local variables, NOT as independent entities)
GREEK_VARIABLES = {
    'alpha', 'beta', 'gamma', 'delta', 'epsilon', 'zeta', 'eta', 'theta', 'iota', 
    'kappa', 'lambda', 'mu', 'nu', 'xi', 'pi', 'rho', 'sigma', 'tau', 'upsilon', 
    'phi', 'chi', 'psi', 'omega', 'varepsilon', 'vartheta', 'varpi', 'varrho', 
    'varsigma', 'varphi'
}

# Map symbols/terms to (entity_id, display_text)
# TEXT REPLACEMENTS MUST BE ORDERED BY SPECIFICITY (Longer/More specific first)
DEFAULT_MACRO_DEPENDENCIES = {
    r'\mNorm': 'op-norm-abstract',
    r'\mAbs': 'op-abs-abstract',
    r'\mInner': 'op-inner-product-abstract',
    r'\mDist': 'op-dist-abstract',
    r'\mSup': 'op-supremum',
    r'\mInf': 'op-infimum',
    r'\mDeriv': 'op-derivative',
    r'\mIntegral': 'op-integral',
}

def extract_macro_dependencies(content: str) -> list[str]:
    deps = []
    for macro, default_id in DEFAULT_MACRO_DEPENDENCIES.items():
        escaped = re.escape(macro)
        concrete = re.findall(rf'{escaped}\[([^\]]+)\]', content)
        if concrete:
            deps.extend(concrete)
        elif re.search(rf'{escaped}(?!\[)\{{', content):
            deps.append(default_id)
    return deps

def extract_all_dependencies(content: str) -> list[str]:
    entityref_deps = re.findall(r'\\entityref\{([^}]+)\}', content)
    macro_deps = extract_macro_dependencies(content)
    return list(set(entityref_deps + macro_deps))

REPLACEMENTS = [
    # --- MANUAL OBJECT MACRO CLEARING ---
    (r"\\mReal(?![a-zA-Z])", "obj-real-numbers", r"\mathbb{R}"),
    (r"\\mR\b", "obj-real-numbers", r"\mathbb{R}"),
    (r"\\mNat(?![a-zA-Z])", "obj-natural-numbers", r"\mathbb{N}"),
    (r"\\mN\b", "obj-natural-numbers", r"\mathbb{N}"),
    (r"\\mInt(?![a-zA-Z])", "obj-integer-numbers", r"\mathbb{Z}"),
    (r"\\mZ\b", "obj-integer-numbers", r"\mathbb{Z}"),
    (r"\\mRat(?![a-zA-Z])", "obj-rational-numbers", r"\mathbb{Q}"),
    (r"\\mQ\b", "obj-rational-numbers", r"\mathbb{Q}"),

    # --- MATH SYMBOLS (Case-sensitive usually, handled by regex) ---
    
    # COMPLEX PATTERNS (Priority 0 - Must match before single symbols)
    
    # Preimage: f^{-1}(B) - Matches f^{-1}( [A-Z] )
    # MUST BE BEFORE f^{-1} pattern!
    (r"(?<![\\])\b[fghuv]\^\{-1\}\([A-Z]\)", "obj-preimage", None),

    # Inverse function: f^{-1}, g^{-1}, \phi^{-1}
    (r"(?<![\\])\b[fghuv]\^\{-1\}", "obj-inverse-mapping", None),
    (r"(?<![a-zA-Z])\\phi\^\{-1\}", "obj-inverse-mapping", None),
    (r"(?<![a-zA-Z])\\psi\^\{-1\}", "obj-inverse-mapping", None),
    
    # Image: f(A) - Matches f( [A-Z] )
    # Avoid P(x) or P(X) if P is predicate? P is capital. 
    # Logic predicates P(x).
    # Function names: f, g, h, u, v, \phi, \psi
    (r"(?<![\\])\b[fghuv]\([A-Z]\)", "obj-image", None),
    (r"(?<![a-zA-Z])\\phi\([A-Z]\)", "obj-image", None),
    (r"(?<![a-zA-Z])\\psi\([A-Z]\)", "obj-image", None),

    # Functions (Single symbols) - Priority Low (handled after composites)
    # But regex order matters. Logic: Composites are listed FIRST.
    # So f(A) matches. f matches later.
    
    # Logic
    # Logic
    (r"\\neg(?![a-zA-Z])", "term-negation", None),
    (r"\\land(?![a-zA-Z])", "term-conjunction", None),
    (r"\\lor(?![a-zA-Z])", "term-disjunction", None),
    (r"\\Rightarrow(?![a-zA-Z])", "term-implication", None),
    (r"\\Longrightarrow(?![a-zA-Z])", "term-implication", None),
    (r"\\implies(?![a-zA-Z])", "term-implication", None),
    (r"\\Leftrightarrow(?![a-zA-Z])", "term-equivalence", None),
    (r"\\Longleftrightarrow(?![a-zA-Z])", "term-equivalence", None),
    (r"\\iff(?![a-zA-Z])", "term-equivalence", None),
    
    # Quantifiers
    (r"\\forall(?![a-zA-Z])", "term-forall", None),
    (r"\\exists!(?![a-zA-Z])", "term-exists-unique", None),
    (r"\\exists(?![a-zA-Z])", "term-exists", None),
    
    # Operations
    (r"\\cup(?![a-zA-Z])", "op-union", None),
    (r"\\cap(?![a-zA-Z])", "op-intersection", None),
    (r"\\setminus(?![a-zA-Z])", "op-set-difference", None),
    (r"\\times(?![a-zA-Z])", "obj-cartesian-product", None),
    (r"\\circ(?![a-zA-Z])", "obj-composition", None),
    
    # Relations — NOTE: \in, \notin, \subset are ZFC PRIMITIVES per architecture.md
    # They must NOT be auto-wrapped with \entityref. Only non-primitive relations:
    (r"\\sim(?![a-zA-Z])", "prop-equipotent", None),
    (r"\\le(?![a-zA-Z])", "prop-partial-order", None),
    (r"\\leqslant(?![a-zA-Z])", "prop-partial-order", None),
    
    # Objects
    (r"x\^\+(?![a-zA-Z])", "obj-successor-set", None),
    (r"\\mathscr\{F\}\(x, y\)", "def-functional-predicate", None),
    (r"\\varnothing(?![a-zA-Z])", "obj-empty-set", None),
    (r"\\emptyset(?![a-zA-Z])", "obj-empty-set", r"\\varnothing"),
    (r"\\mathscr\{P\}", "obj-powerset", None),
    (r"\\mathbb\{N\}", "obj-natural-numbers", None),
    (r"\\mathbb\{R\}", "obj-real-numbers", None),
    (r"\\operatorname\{card\}", "obj-cardinality", None),

    # --- TEXT TERMS (Regex covers capitalization [А-Яа-я]) ---
    
    # Specific Compound Terms (Priority 1)
    (r"[Пп]уст[а-я]* множеств[а-я]*", "obj-empty-set", None),
    (r"[Мм]ножеств[а-я]* подмножеств[а-я]*", "obj-powerset", None),
    (r"[Уу]порядоченн[а-я]* пар[а-я]*", "obj-ordered-pair", None),
    (r"[Дд]екартов[а-я]* произведени[а-я]*", "obj-cartesian-product", None),
    (r"[Оо]бласт[а-я]* определени[а-я]*", "obj-domain", None),
    (r"[Мм]ножеств[а-я]* значени[а-я]*", "obj-image", None), # or codomain context dependent
    (r"[Гг]рафик[а-я]* функци[а-я]*", "obj-graph", None),
    (r"[Тт]ождественн[а-я]* отображени[а-я]*", "obj-identity", None),
    (r"[Оо]братн[а-я]* отображени[а-я]*", "obj-inverse-mapping", None),
    (r"[Хх]арактеристическ[а-я]* функци[а-я]*", "obj-char-function", None),
    (r"[Оо]тношени[а-я]* эквивалентност[а-я]*", "prop-equiv-relation", None),
    (r"[Чч]астичн[а-я]* поряд[а-я]*", "prop-partial-order", None),
    (r"[Оо]бъединени[а-я]* множеств[а-я]*", "op-union", None),
    (r"[Пп]ересечени[а-я]* множеств[а-я]*", "op-intersection", None),
    (r"[Рр]азност[а-я]* множеств[а-я]*", "op-set-difference", None),
    
    # Single Word Terms (Priority 2)
    (r"[Фф]ункциональн[а-я]* услови[а-я]*", "def-functional-predicate", None),
    (r"[Фф]ункциональн[а-я]* предикат[а-я]*", "def-functional-predicate", None),
    (r"последовател[а-я]*", "obj-successor-set", None),
    (r"[Бб]инарн[а-я]* операци[а-я]*", "obj-binary-operation", None),
    (r"[Уу]нарн[а-я]* операци[а-я]*", "obj-unary-operation", None),
    (r"[Пп]одмножеств[а-я]*", "obj-subset", None),
    (r"[Мм]ножеств[а-я]*", "obj-set", None), # Catch-all for Set
    (r"[Фф]ункци[а-я]*", "obj-function", None),
    (r"[Оо]тображени[а-я]*", "obj-function", None),
    (r"[Кк]ообласт[а-я]*", "obj-codomain", None),
    (r"[Пп]рообраз[а-я]*", "obj-preimage", None),
    (r"[Оо]браз[а-я]*", "obj-image", None),
    (r"[Кк]омпозици[а-я]*", "obj-composition", None),
    (r"[Сс]ужени[а-я]*", "obj-restriction", None),
    (r"[Мм]ощност[а-я]*", "obj-cardinality", None),
    (r"[Кк]ардинальн[а-я]* числ[а-я]*", "obj-cardinality", None),
    
    # Properties (Adjectives) - use root match
    (r"[Сс]юръективн[а-я]*", "prop-surjective", None),
    (r"[Сс]юръекци[а-я]*", "prop-surjective", None),
    (r"[Ии]нъективн[а-я]*", "prop-injective", None),
    (r"[Ии]нъекци[а-я]*", "prop-injective", None),
    (r"[Бб]иективн[а-я]*", "prop-bijective", None),
    (r"[Бб]иекци[а-я]*", "prop-bijective", None),
    (r"[Рр]авномощн[а-я]*", "prop-equipotent", None),
    (r"[Кк]онечн[а-я]*", "prop-finite", None),
    # (r"[Бб]есконечн[а-я]*", "prop-infinite", None), # If exists
    
    # Functions (Single) - Fallback
    (r"(?<![\\])\b[fgh]\b(?![\(\^])", "obj-function", None),
    (r"(?<![a-zA-Z])\\phi(?![\(\^])", "obj-function", None),
    (r"(?<![a-zA-Z])\\psi(?![\(\^])", "obj-function", None),
]

# Regex to match existing entityrefs to skip them
ENTITYREF_PATTERN = re.compile(r"\\entityref\{[^}]+\}\{[^}]+\}")

def process_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()
        
    original_content = content
    
    # Extract current entity-id to avoid self-linking
    current_entity_id = None
    entity_type = "unknown"
    defined_in = []
    
    match_id = re.search(r"^% entity-id:\s*(.+)$", content, re.MULTILINE)
    if match_id:
        current_entity_id = match_id.group(1).strip()
        
    match_type = re.search(r"^% entity-type:\s*(.+)$", content, re.MULTILINE)
    if match_type:
        entity_type = match_type.group(1).strip()
        
    match_def = re.search(r"^% defined-in:\s*(.+)$", content, re.MULTILINE)
    if match_def:
        sources_str = match_def.group(1).strip()
        defined_in = [s.strip() for s in sources_str.split(",")]
        
    if current_entity_id:
        # Remove existing self-links
        # Pattern: \entityref{current_id}{text} -> text
        # Only matches if braces are balanced (simple case)
        escaped_id = re.escape(current_entity_id)
        # We use a simple regex assuming no nested braces in the text part for now, 
        # or use a loop to handle nesting if necessary. 
        # But our script generates simple links.
        content = re.sub(r"\\entityref\{" + escaped_id + r"\}\{([^}]+)\}", r"\1", content)

    # Preprocess custom abstract parametric macros to standard LaTeX wrapped in \entityref
    PARAMETRIC_MACRO_REPLACEMENTS = [
        (r"\\mSup\{([^}]+)\}", "op-supremum", r"\\sup\\limits_{\1}"),
        (r"\\mInf\{([^}]+)\}", "op-infimum", r"\\inf\\limits_{\1}"),
        (r"\\mAbs\{([^}]+)\}", "op-abs-abstract", r"\\mathrm{abs}(\1)"),
        (r"\\mNorm\{([^}]+)\}", "op-norm-abstract", r"\\mathrm{norm}(\1)"),
        (r"\\mDist\{([^}]+)\}\{([^}]+)\}", "op-dist-abstract", r"\\mathrm{d}(\1, \2)"),
        (r"\\mDeriv\{([^}]+)\}\{([^}]+)\}", "op-derivative", r"\\frac{d \1}{d \2}"),
        (r"\\mIntegral\{([^}]+)\}\{([^}]+)\}\{([^}]+)\}", "op-integral", r"\\int_{\1}^{\2} \3"),
    ]
    
    for pat, entity_id, repl_tmpl in PARAMETRIC_MACRO_REPLACEMENTS:
        if current_entity_id and entity_id == current_entity_id:
            content = re.sub(pat, repl_tmpl, content)
        else:
            repl_str = f"\\\\entityref{{{entity_id}}}{{{repl_tmpl}}}"
            content = re.sub(pat, repl_str, content)

    # We will dynamically discover mathematical entities in the content
    active_replacements = list(REPLACEMENTS)
    commands = set(re.findall(r"\\([a-zA-Z]+)", content))
    
    KNOWN_COMMAND_MAPPINGS = {
        'sup': 'op-supremum',
        'inf': 'op-infimum',
        'lim': 'op-limit',
        'sum': 'op-sum',
        'int': 'op-integral',
        'max': 'op-maximum',
        'min': 'op-minimum',
    }
    
    existing_patterns = set()
    for pattern, _, _ in REPLACEMENTS:
        match = re.match(r"^\\\\([a-zA-Z]+)(?:\(\?!\[a-zA-Z\]\))?$", pattern)
        if match:
            existing_patterns.add(match.group(1))
            
    for cmd in sorted(commands):
        backslash_cmd = "\\" + cmd
        if backslash_cmd in ALL_TERMINALS or backslash_cmd == r"\in" or backslash_cmd == r"\subset":
            continue
        if cmd.lower() in FORMATTING_COMMANDS or cmd in GREEK_VARIABLES:
            continue
        if cmd in existing_patterns:
            continue
            
        if cmd in KNOWN_COMMAND_MAPPINGS:
            entity_id = KNOWN_COMMAND_MAPPINGS[cmd]
        else:
            entity_id = f"op-{cmd.lower()}"
            
        pattern = rf"\\{cmd}(?![a-zA-Z])"
        active_replacements.insert(0, (pattern, entity_id, None))

    # We will process replacements sequentially
    for pattern, entity_id, replacement_text in active_replacements:
        # SKIP SELF-LINKING
        if current_entity_id and entity_id == current_entity_id:
            continue

        # Construct a combined regex: (existing_ref) | (target_pattern)
        combined_regex = f"(\\\\entityref\\{{[^}}]+\\}}\\{{[^}}]+\\}})|({pattern})"
        
        def callback(match):
            if match.group(1): # It's an existing entityref, return as is
                return match.group(1)
            else: # It's our target
                text = match.group(2)
                final_text = replacement_text if replacement_text else text
                return f"\\entityref{{{entity_id}}}{{{final_text}}}"
                
        # Applying regex line by line
        new_lines = []
        for line in content.splitlines():
            # Skip comments
            if line.strip().startswith('%'):
                new_lines.append(line)
                continue
            
            # Skip \section, \subsection, \subsubsection, \label
            sline = line.strip()
            if sline.startswith('\\section') or sline.startswith('\\sub') or sline.startswith('\\label'):
                new_lines.append(line)
                continue
                
            # Apply replacement
            new_line = re.sub(combined_regex, callback, line)
            new_lines.append(new_line)
            
        content = "\n".join(new_lines)

    if content != original_content:
        print(f"Updating {filepath}")
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(content)

    return content, current_entity_id, entity_type, defined_in

def main():
    db_available = False
    try:
        conn = sqlite3.connect(DB_PATH, timeout=5.0)
        cursor = conn.cursor()
        db_available = True
    except sqlite3.OperationalError:
        print("[WARNING] SQLite database is locked. DB indexing will be skipped, but content linking will proceed.")

    for root, dirs, files in os.walk(CONTENT_DIR):
        for file in files:
            if file.endswith(".tex") and file != "master.tex" and file != "mathesis.sty" and file != "TEMPLATE.tex":
                filepath = os.path.join(root, file)
                content, entity_id, entity_type, defined_in = process_file(filepath)
                
                # Update DB
                if db_available and entity_id:
                    try:
                        # Parse title from filename
                        match_title = re.search(r'^(.*?) \[', file)
                        title = match_title.group(1).strip() if match_title else entity_id
                        rel_path = str(Path(filepath).relative_to(PROJECT_ROOT))
                        
                        cursor.execute("INSERT OR REPLACE INTO entities (entity_id, type, title, path) VALUES (?, ?, ?, ?)",
                                       (entity_id, entity_type, title, rel_path))
                        
                        cursor.execute("DELETE FROM formulation_sources WHERE entity_id = ?", (entity_id,))
                        for src in defined_in:
                            cursor.execute("INSERT INTO formulation_sources (entity_id, source_book) VALUES (?, ?)", (entity_id, src))
                            
                        # Extract dependencies and insert into entity_dependency table
                        deps = extract_all_dependencies(content)
                        cursor.execute("DELETE FROM entity_dependency WHERE source_id = ?", (entity_id,))
                        for target_id in deps:
                            if target_id != entity_id: # Avoid self-linking
                                cursor.execute("INSERT INTO entity_dependency (source_id, target_id) VALUES (?, ?)", (entity_id, target_id))
                        
                        conn.commit()
                    except sqlite3.OperationalError:
                        print("[WARNING] Database locked during update. Disabling SQLite indexing for the rest of this run.")
                        db_available = False
    
    if db_available:
        conn.close()
    print("Content linking and processing complete.")

if __name__ == "__main__":
    main()
