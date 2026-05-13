import os
import re
import sqlite3
from pathlib import Path

PROJECT_ROOT = Path(r"f:\Universe\Projects\Учебник по матанализу")
CONTENT_DIR = PROJECT_ROOT / "content"
DB_PATH = PROJECT_ROOT / "mathesis_index.db"

# Map symbols/terms to (entity_id, display_text)
# TEXT REPLACEMENTS MUST BE ORDERED BY SPECIFICITY (Longer/More specific first)
REPLACEMENTS = [
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
    (r"\\neg(?![a-zA-Z])", "def-logical-connectives", None),
    (r"\\land(?![a-zA-Z])", "def-logical-connectives", None),
    (r"\\lor(?![a-zA-Z])", "def-logical-connectives", None),
    (r"\\Rightarrow(?![a-zA-Z])", "def-logical-connectives", None),
    (r"\\Longrightarrow(?![a-zA-Z])", "def-logical-connectives", None),
    (r"\\Leftrightarrow(?![a-zA-Z])", "def-logical-connectives", None),
    (r"\\Longleftrightarrow(?![a-zA-Z])", "def-logical-connectives", None),
    (r"\\iff(?![a-zA-Z])", "def-logical-connectives", None),
    (r"\\implies(?![a-zA-Z])", "def-logical-connectives", None),
    
    # Quantifiers
    (r"\\forall(?![a-zA-Z])", "def-logical-quantifiers", None),
    (r"\\exists(?![a-zA-Z])", "def-logical-quantifiers", None),
    
    # Operations
    (r"\\cup(?![a-zA-Z])", "op-union", None),
    (r"\\cap(?![a-zA-Z])", "op-intersection", None),
    (r"\\setminus(?![a-zA-Z])", "op-set-difference", None),
    (r"\\times(?![a-zA-Z])", "obj-cartesian-product", None),
    (r"\\circ(?![a-zA-Z])", "obj-composition", None),
    
    # Relations
    (r"\\subset(?![a-zA-Z])", "obj-subset", None),
    (r"\\in(?![a-zA-Z])", "obj-set", None),
    (r"\\notin(?![a-zA-Z])", "obj-set", None),
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

    # We will process replacements sequentially
    for pattern, entity_id, replacement_text in REPLACEMENTS:
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
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    for root, dirs, files in os.walk(CONTENT_DIR):
        for file in files:
            if file.endswith(".tex") and file != "master.tex" and file != "mathesis.sty":
                filepath = os.path.join(root, file)
                content, entity_id, entity_type, defined_in = process_file(filepath)
                
                # Update DB
                if entity_id:
                    # Parse title from filename
                    match_title = re.search(r'^(.*?) \[', file)
                    title = match_title.group(1).strip() if match_title else entity_id
                    rel_path = str(Path(filepath).relative_to(PROJECT_ROOT))
                    
                    cursor.execute("INSERT OR REPLACE INTO entities (entity_id, type, title, path) VALUES (?, ?, ?, ?)",
                                   (entity_id, entity_type, title, rel_path))
                    
                    cursor.execute("DELETE FROM formulation_sources WHERE entity_id = ?", (entity_id,))
                    for src in defined_in:
                        cursor.execute("INSERT INTO formulation_sources (entity_id, source_book) VALUES (?, ?)", (entity_id, src))
    
    conn.commit()
    conn.close()
    print("Database indexing complete.")

if __name__ == "__main__":
    main()
