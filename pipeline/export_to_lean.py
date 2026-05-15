"""
Export to Lean v2 — LLM-Assisted Translation
=============================================
Translates LaTeX entities to valid Lean 4 code using local Ollama LLM.
Falls back to regex-based translation if LLM is unavailable.
Supports incremental validation (saves validated files individually).
"""
import sqlite3
import re
import json
import urllib.request
from pathlib import Path
from collections import defaultdict, deque

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "mathesis_index.db"
CONTENT_DIR = PROJECT_ROOT / "content"
LEAN_DIR = PROJECT_ROOT / "lean_validator"
VALIDATED_DIR = LEAN_DIR / "Validated"
OUT_FILE = LEAN_DIR / "MathesisGraph.lean"


# ── Ollama Interface ─────────────────────────────────────────────────────────

def query_ollama(prompt, model="llama3.1:8b"):
    url = "http://localhost:11434/api/generate"
    data = {
        "model": model, "prompt": prompt, "stream": False,
        "options": {
            "num_ctx": 8192, "num_predict": 512,
            "temperature": 0.1,  # Very low — we need precise formal output
        }
    }
    try:
        req = urllib.request.Request(url, json.dumps(data).encode('utf-8'),
                                     headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=120) as response:
            result = json.loads(response.read().decode('utf-8'))
            resp_text = result.get('response', '').strip()
            # Extract and log thinking
            think_match = re.search(r'<think>(.*?)</think>', resp_text, flags=re.DOTALL)
            if think_match:
                think_content = think_match.group(1).strip()
                print(f"  [LLM Think]: {think_content}")
            resp_text = re.sub(r'<think>.*?</think>', '', resp_text, flags=re.DOTALL).strip()
            return resp_text
    except Exception as e:
        print(f"  [lean-export] LLM error: {e}")
        return ""


# ── Graph Discovery ──────────────────────────────────────────────────────────

def get_graph_from_files():
    """Scans content/ for entities and their dependencies."""
    nodes = {}
    edges = []

    for filepath in CONTENT_DIR.rglob("*.tex"):
        if filepath.name in ("master.tex", "TEMPLATE.tex", "mathesis.sty"):
            continue
        match = re.search(r'\[([^\]]+)\]\.tex$', filepath.name)
        if not match:
            continue

        entity_id = match.group(1)
        try:
            content = filepath.read_text(encoding='utf-8')
        except Exception:
            continue

        # Detect type from comment or environment
        type_match = re.search(r'% entity-type:\s*(\w+)', content)
        entity_type = type_match.group(1) if type_match else "object"

        nodes[entity_id] = {"type": entity_type, "path": filepath}

        # Extract dependencies
        deps = set(re.findall(r'\\entityref\{([^}]+)\}', content))
        for dep in deps:
            if dep != entity_id:
                edges.append((entity_id, dep))

    return nodes, edges


def topological_sort(nodes, edges):
    graph = defaultdict(list)
    in_degree = {n: 0 for n in nodes}

    for u, v in edges:
        if u in nodes and v in nodes:
            graph[v].append(u)
            in_degree[u] += 1

    queue = deque([n for n in nodes if in_degree[n] == 0])
    sorted_nodes = []

    while queue:
        curr = queue.popleft()
        sorted_nodes.append(curr)
        for neighbor in graph[curr]:
            in_degree[neighbor] -= 1
            if in_degree[neighbor] == 0:
                queue.append(neighbor)

    # Catch cycles
    for n in nodes:
        if n not in sorted_nodes:
            sorted_nodes.append(n)

    return sorted_nodes


# ── LLM Translation ─────────────────────────────────────────────────────────

def translate_to_lean_via_llm(entity_id, entity_type, tex_content, model="qwen3:8b", mathlib_hints=""):
    """
    Uses local Ollama LLM to translate LaTeX to valid Lean 4.
    Returns Lean 4 code string or empty string on failure.
    """
    # Strip proof blocks — validate formulations only
    tex_clean = re.sub(r'\\begin\{proof\}.*?\\end\{proof\}', '', tex_content, flags=re.DOTALL)
    # Strip comments
    tex_clean = re.sub(r'^%.*$', '', tex_clean, flags=re.MULTILINE)
    tex_clean = tex_clean.strip()

    if not tex_clean:
        return ""

    lean_name = entity_id.replace('-', '_')

    prompt = f"""Translate this LaTeX mathematical entity to valid Lean 4 code.
Use Mathlib library types and notation.

Entity ID: {entity_id}
Entity type: {entity_type}
Lean name: {lean_name}

LaTeX source:
{tex_clean}

RULES (CRITICAL):
- Output ONLY valid Lean 4 code. No explanations, no markdown blocks.
- Use Unicode: ∀ ∃ → ↔ ∧ ∨ ¬ ∈ ⊆ ≤ ≥
- Use Mathlib types: ℝ ℕ ℤ Set Prop Type
- If you don't know the exact Mathlib type for an abstract operation (like Partition, Measure, TopologicalSpace), use the Lean placeholder `_`. Lean will infer it or give us a type error!
- For axioms: `axiom {lean_name} : <statement>`
- For theorems: `theorem {lean_name} : <statement> := by sorry`
- For objects/definitions: `def {lean_name} : Type := sorry` or appropriate definition
- ALL variables must be explicitly bound with ∀ or ∃
- Do NOT include `import` statements
- Do NOT use any LaTeX commands (\\forall, \\in, \\mathbb, etc.)
- If the formula is too complex, write a simpler type-correct stub using `_`.

MATHLIB DISCOVERY HINTS:
{mathlib_hints}

Lean 4 code:"""

    response = query_ollama(prompt, model=model)

    if not response:
        return ""

    # Clean up any markdown artifacts
    response = re.sub(r'^```\w*\s*', '', response, flags=re.MULTILINE)
    response = re.sub(r'^```\s*$', '', response, flags=re.MULTILINE)
    response = response.strip()

    # Validate: must not contain LaTeX commands
    if '\\' in response and ('\\mathcal' in response or '\\mForall' in response or '\\in' in response):
        print(f"  [lean-export] LLM output still contains LaTeX. Rejecting.")
        return ""

    return response


# ── Regex Fallback Translation ───────────────────────────────────────────────

def translate_to_lean_regex(entity_id, entity_type, tex_content):
    """Legacy regex-based translation. Used as fallback when LLM fails."""
    formulas = re.findall(r'\\\[(.*?)\\\]', tex_content, re.DOTALL)
    if not formulas:
        return ""

    math = " ".join(formulas)
    lean_name = entity_id.replace('-', '_')

    replacements = [
        (r'\\mForall\{([^}]+)\}', r'∀ \1, '),
        (r'\\mExists\{([^}]+)\}', r'∃ \1, '),
        (r'\\mImplies', '→'),
        (r'\\mIff', '↔'),
        (r'\\mDefIff', ':='),
        (r'\\mAnd', '∧'), (r'\\land', '∧'),
        (r'\\mOr', '∨'), (r'\\lor', '∨'),
        (r'\\mNot', '¬'), (r'\\lnot', '¬'),
        (r'\\mIn', '∈'), (r'\\in', '∈'),
        (r'\\mSubset', '⊆'), (r'\\subset', '⊆'),
        (r'\\entityref\{[^}]+\}\{(.*?)\}', r'\1'),
        (r'\\quad', ' '), (r'\\;', ' '),
        (r'\\text\{([^}]+)\}', r'\1'),
        (r'\\left', ''), (r'\\right', ''),
        (r'\\mathbb\{R\}', 'ℝ'), (r'\\mReal', 'ℝ'),
        (r'\\mathbb\{N\}', 'ℕ'), (r'\\mNat', 'ℕ'),
        (r'\\mathbb\{Z\}', 'ℤ'), (r'\\mInt', 'ℤ'),
        (r'\\colon', ':'),
        (r'\\to', '→'),
        (r'\\neq', '≠'),
        (r'\\leq', '≤'), (r'\\le', '≤'),
        (r'\\geq', '≥'), (r'\\ge', '≥'),
        (r'\\forall', '∀'), (r'\\exists', '∃'),
        (r'\\Rightarrow', '→'), (r'\\Leftrightarrow', '↔'),
        (r'\\varepsilon', 'ε'), (r'\\delta', 'δ'),
        (r'\\infty', '∞'),
        (r'\\mathcal\{([^}]+)\}', r'\1'),
        (r'\n', ' '),
    ]

    lean_math = math
    for pattern, repl in replacements:
        lean_math = re.sub(pattern, repl, lean_math)
    lean_math = re.sub(r'\s+', ' ', lean_math).strip()

    # Format by type
    if entity_type == "axiom":
        return f"axiom {lean_name} : {lean_math}"
    elif entity_type == "object":
        return f"axiom {lean_name} : Type"
    elif entity_type == "property":
        return f"def {lean_name} : Prop := sorry"
    elif entity_type in ("theorem", "operation"):
        return f"axiom {lean_name} : {lean_math}"

    return f"-- Unrecognized type: {lean_name}"


# ── Main Export Pipeline ─────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Export Mathesis graph to Lean 4")
    parser.add_argument("--model", type=str, default="llama3.1:8b", help="Ollama model")
    parser.add_argument("--force", action="store_true", help="Re-translate all entities")
    args = parser.parse_args()

    print("=== Exporting Mathesis graph to Lean 4 ===")

    nodes, edges = get_graph_from_files()
    sorted_ids = topological_sort(nodes, edges)

    if not sorted_ids:
        print("No entities found.")
        return

    VALIDATED_DIR.mkdir(parents=True, exist_ok=True)

    lean_fragments = []
    stats = {"llm_ok": 0, "regex_ok": 0, "failed": 0, "cached": 0}

    for eid in sorted_ids:
        node = nodes[eid]
        validated_file = VALIDATED_DIR / f"{eid}.lean"

        # Skip if already validated (unless --force)
        if validated_file.exists() and not args.force:
            lean_code = validated_file.read_text(encoding='utf-8')
            lean_fragments.append((eid, lean_code))
            stats["cached"] += 1
            continue

        try:
            content = node["path"].read_text(encoding='utf-8')
        except Exception as e:
            print(f"  [SKIP] {eid}: {e}")
            stats["failed"] += 1
            continue

        # Strip proof blocks for translation
        content_no_proofs = re.sub(r'\\begin\{proof\}.*?\\end\{proof\}', '', content, flags=re.DOTALL)

        # Try LLM first
        lean_code = translate_to_lean_via_llm(eid, node["type"], content_no_proofs, model=args.model)

        if lean_code:
            print(f"  [LLM] {eid} → OK ({len(lean_code)} chars)")
            stats["llm_ok"] += 1
        else:
            # Fallback to regex
            lean_code = translate_to_lean_regex(eid, node["type"], content_no_proofs)
            if lean_code:
                print(f"  [REGEX] {eid} → fallback ({len(lean_code)} chars)")
                stats["regex_ok"] += 1
            else:
                print(f"  [SKIP] {eid} → no translatable content")
                stats["failed"] += 1
                continue

        # Save validated fragment
        validated_file.write_text(lean_code, encoding='utf-8')
        lean_fragments.append((eid, lean_code))

    # Assemble MathesisGraph.lean
    with open(OUT_FILE, 'w', encoding='utf-8') as f:
        f.write("import Mathlib\n\n")
        f.write("-- Auto-generated by pipeline/export_to_lean.py\n")
        f.write(f"-- Entities: {len(lean_fragments)}\n\n")

        for eid, code in lean_fragments:
            f.write(f"-- {eid}\n")
            f.write(f"{code}\n\n")

    print(f"\n=== Export complete ===")
    print(f"  LLM translations: {stats['llm_ok']}")
    print(f"  Regex fallbacks:  {stats['regex_ok']}")
    print(f"  Cached:           {stats['cached']}")
    print(f"  Failed/skipped:   {stats['failed']}")
    print(f"  Output: {OUT_FILE}")


if __name__ == "__main__":
    main()
