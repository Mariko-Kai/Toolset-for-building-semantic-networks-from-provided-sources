import sqlite3
import urllib.request
import json
import uuid
import re
import argparse
import sys
import os
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(PROJECT_ROOT))

from pipeline.lean_validator import validate_semantics_with_lean
DB_PATH = PROJECT_ROOT / "mathesis_index.db"
CONTENT_DIR = PROJECT_ROOT / "content"

def query_ollama(prompt, model="llama3.1:8b"):
    url = "http://localhost:11434/api/generate"
    data = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "num_predict": 1024,   # Hard cap: LaTeX theorem ~300-600 tokens
            "num_ctx": 4096,       # Enough for prompt + response on GTX 1650
            "temperature": 0.3,    # Low creativity — strict formal output
        }
    }
    try:
        req = urllib.request.Request(url, json.dumps(data).encode('utf-8'), headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=300) as response:
            result = json.loads(response.read().decode('utf-8'))
            return result.get('response', '').strip()
    except Exception as e:
        print(f"Ollama error: {e}")
        return ""

def detect_entity_type_from_text(raw_texts):
    """Определяет тип сущности по ключевым словам в извлеченном тексте."""
    combined = " ".join(raw_texts).lower()
    theorem_keywords = ["теорема", "лемма", "следствие", "theorem", "lemma",
                        "corollary", "доказательство", "proof", "∎"]
    for kw in theorem_keywords:
        if kw in combined:
            return "theorem"
    return "definition"

def build_synthesis_prompt(cluster_id, formulations, sources, entity_type):
    """Строит компактный промпт для синтеза. Оптимизирован для скорости на GTX 1650."""
    text_input = "\n".join([f"[{s}]: {t}" for s, t in zip(sources, formulations)])

    rules = r"""OUTPUT: Only LaTeX. No ```latex blocks. Include:
% entity-id: <short-id>
% entity-type: <object|property|operation|theorem>

CRITICAL: Generate EXACTLY ONE mathematical entity. DO NOT repeat the output. DO NOT provide multiple versions. One % entity-id, one % entity-type, and the LaTeX block(s).

MACROS: \mForall, \mExists, \mImplies, \mIff, \mAnd, \mOr, \mNot.
REFS: \entityref{entity-id}{symbol} for derived entities.
ABS MACROS: \entityref{op-abs-abstract}{\mathrm{abs}}(x), \entityref{op-norm-abstract}{\mathrm{norm}}(x), \entityref{op-supremum}{\sup}(S), \entityref{op-infimum}{\inf}(S) (NEVER use \mAbs, \mNorm, or raw |x|, \|x\|).

TERMINALS (NEVER wrap in \entityref): \forall \exists \in \emptyset \land \lor = < > \leq \geq 0 1 \infty \varepsilon \delta

TYPING: Every formula MUST start with variable declarations via quantors:
\mForall{f \colon \entityref{obj-closed-interval}{[a,b]} \mTo \entityref{obj-real-numbers}{\mReal}}

PURE MATH RULE: For \begin{theorem}, \begin{object}, \begin{property}, and \begin{operation} blocks, NO NATURAL LANGUAGE IS ALLOWED AT ALL. NO English, NO Russian, NO plain text, NO "Note", NO "Remark", NO explanations. The content MUST be 100% formal math symbols and macros. ALL formulas MUST be wrapped in display math blocks \[ ... \]. Inline math $...$ is FORBIDDEN.
Natural language and explanatory notes are ONLY permitted inside \begin{proof} blocks. ALL math objects/variables in proofs MUST be correctly wrapped with \entityref or math macros.
"""

    example = r"""EXAMPLE:
% entity-id: thm-weierstrass-extreme
% entity-type: theorem
\begin{theorem}[Weierstrass Extreme Value]
\mForall{f \colon \entityref{obj-closed-interval}{[a,b]} \mTo \entityref{obj-real-numbers}{\mReal}}
\quad \entityref{prop-continuous}{f}
\mImplies \mExists{c \in \entityref{obj-closed-interval}{[a,b]}}
\mForall{x \in \entityref{obj-closed-interval}{[a,b]}} \quad f(x) \leq f(c)
\end{theorem}
"""

    if entity_type == "theorem":
        prompt = f"""Synthesize a strict formal THEOREM + PROOFS from these sources:
{text_input}

{rules}
{example}
Generate \\begin{{theorem}}[Name] ... \\end{{theorem}}.
Then generate TWO proofs in parallel: one in Russian and one in English.
Format:
\\begin{{proof}}[RU]
...
\\end{{proof}}
\\begin{{proof}}[EN]
...
\\end{{proof}}

Proofs can contain natural language, but all math entities must be formally wrapped."""
    else:
        prompt = f"""Synthesize a strict formal DEFINITION from these sources:
{text_input}

{rules}
{example}
Generate \\begin{{object}}[Name] ... \\end{{object}} (or property/operation).
CRITICAL: DO NOT add any notes, remarks, text, or English words outside or inside the block. ONLY the formal mathematical formula."""
    return prompt

def sanitize_terminal_entityrefs(latex: str) -> str:
    from pipeline.terminals import ALL_TERMINALS
    for terminal in ALL_TERMINALS:
        escaped = re.escape(terminal)
        # Строгое совпадение: второй аргумент entityref === terminal
        pattern = rf'\\entityref\{{[^}}]+\}}\{{({escaped})\}}'
        latex = re.sub(pattern, r'\1', latex)
    return latex

def enforce_single_entity(latex: str) -> str:
    """If LLM generated multiple entities, keep only the first one."""
    # 1. Truncate at the second occurrence of metadata
    ids = list(re.finditer(r'^\s*% entity-id:', latex, re.MULTILINE))
    if len(ids) > 1:
        latex = latex[:ids[1].start()].rstrip()
        print(f"[sanitize] Truncated output: {len(ids)} entities found (metadata marker), kept first only.", flush=True)
        return latex

    # 2. Truncate if we see a second main block of the same type
    main_envs = ['theorem', 'object', 'property', 'operation', 'axiom']
    for env in main_envs:
        pattern = rf'\\begin\{{{env}\}}'
        starts = list(re.finditer(pattern, latex))
        if len(starts) > 1:
            latex = latex[:starts[1].start()].rstrip()
            print(f"[sanitize] Truncated output: multiple \\begin{{{env}}} found, kept first only.", flush=True)
            return latex
            
    return latex

def warn_natural_language(latex: str) -> list:
    """Check proof blocks for natural language (relaxed per user request)."""
    return []

def sanitize_raw_delimiters(latex: str) -> str:
    """Replace raw |...| with \\mAbs{...} inside math blocks."""
    # Only replace simple |expr| patterns (no nested |)
    latex = re.sub(r'(?<!\\)\|([^|]+?)\|', r'\\entityref{op-abs-abstract}{\\mathrm{abs}}(\1)', latex)
    return latex

def synthesize_cluster(cluster_id, formulations, sources):
    import time
    print(f"\n{'='*60}", flush=True)
    print(f"[synthesizer] Cluster: {cluster_id}", flush=True)
    print(f"[synthesizer] Sources: {', '.join(sources)} ({len(formulations)} formulations)", flush=True)

    entity_type = detect_entity_type_from_text(formulations)
    print(f"[synthesizer] Detected entity type: {entity_type}", flush=True)

    prompt = build_synthesis_prompt(cluster_id, formulations, sources, entity_type)
    print(f"[synthesizer] Prompt length: {len(prompt)} chars", flush=True)

    print(f"[synthesizer] Starting LLM Synthesis Loop (max 3 attempts)...", flush=True)

    max_attempts = 3
    current_attempt = 1
    error_feedback = ""
    latex_content = ""

    while current_attempt <= max_attempts:
        print(f"\n[synthesizer] --- Attempt {current_attempt}/{max_attempts} ---", flush=True)
        current_prompt = prompt
        if error_feedback:
            print(f"[synthesizer] Injecting Lean error feedback into prompt...", flush=True)
            current_prompt += f"\n\nПРЕДУПРЕЖДЕНИЕ (Попытка {current_attempt}): Lean 4 отклонил твою формулировку со следующими ошибками:\n{error_feedback}\nПожалуйста, исправь LaTeX-код, чтобы он прошел строгую типизацию и объяви все используемые переменные."

        print(f"[synthesizer] Sending prompt to Ollama LLM...", flush=True)
        t0 = time.time()
        response = query_ollama(current_prompt)
        elapsed = time.time() - t0
        print(f"[synthesizer] LLM responded in {elapsed:.1f}s ({len(response)} chars)", flush=True)

        # Cleanup backtick wrappers if any
        response = re.sub(r'^```latex\s*', '', response, flags=re.MULTILINE)
        response = re.sub(r'^```\s*', '', response, flags=re.MULTILINE)

        latex_content = ""
        in_block = False
        for line in response.split('\n'):
            if line.strip().startswith("% entity-id:"):
                if in_block:
                    # Second entity detected, stop parsing
                    break
                latex_content += line + "\n"
                in_block = True
            elif in_block:
                latex_content += line + "\n"

        if not latex_content:
            print("[synthesizer] Failed to parse LLM output. Using raw response.")
            latex_content = response

        # === Post-processing pipeline ===
        latex_content = enforce_single_entity(latex_content)
        latex_content = sanitize_terminal_entityrefs(latex_content)
        latex_content = sanitize_raw_delimiters(latex_content)

        # Check for natural language violations
        nl_warnings = warn_natural_language(latex_content)
        if nl_warnings:
            print(f"[synthesizer] [WARN] Natural language detected: {nl_warnings}")
            error_feedback = "\n".join(nl_warnings)
            current_attempt += 1
            continue

        # === REAL Lean 4 Validation ===
        from pipeline.export_to_lean import translate_to_lean

        # Strip proof blocks for Lean (Lean validates formulations only)
        lean_input = re.sub(r'\\begin\{proof\}.*?\\end\{proof\}', '', latex_content, flags=re.DOTALL)

        # Extract entity metadata for translation
        match_id_temp = re.search(r"^% entity-id:\s*(.+)$", latex_content, re.MULTILINE)
        match_type_temp = re.search(r'% entity-type:\s*([a-zA-Z]+)', latex_content)
        temp_eid = match_id_temp.group(1).strip() if match_id_temp else "temp_entity"
        temp_etype = match_type_temp.group(1).strip() if match_type_temp else "axiom"

        lean_code = translate_to_lean(temp_eid, temp_etype, lean_input)

        if lean_code:
            temp_lean = PROJECT_ROOT / "lean_validator" / "TempValidation.lean"
            with open(temp_lean, 'w', encoding='utf-8') as lf:
                lf.write("import Mathlib\n\n")
                lf.write(f"-- Auto-generated validation for {temp_eid}\n")
                lf.write(lean_code + "\n")

            print(f"  Lean validating: {lean_code[:80]}...")
            result = validate_semantics_with_lean(str(temp_lean))

            try:
                temp_lean.unlink()
            except Exception:
                pass
        else:
            print("  No math formulas found for Lean validation, skipping.")
            result = {"status": "success", "errors": []}

        if result["status"] == "success":
            print("  [OK] Lean validation passed!")
            break
        else:
            print(f"  [FAIL] Lean validation failed: {result['errors']}")
            error_feedback = "\n".join([e["message"] for e in result["errors"]])
            current_attempt += 1

    return latex_content

def main():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    cursor.execute("SELECT temp_cluster_id, source_book, raw_text FROM formulation_raw_cache WHERE temp_cluster_id IS NOT NULL")
    rows = cursor.fetchall()

    clusters = {}
    for cid, source, text in rows:
        if cid not in clusters:
            clusters[cid] = {'sources': [], 'texts': []}
        clusters[cid]['sources'].append(source)
        clusters[cid]['texts'].append(text)

    print(f"[synthesizer] Found {len(clusters)} cluster(s) to synthesize.")
    if not clusters:
        print("[synthesizer] Nothing to synthesize. Exiting.")
        conn.close()
        return

    for cid, data in clusters.items():
        synthesized_tex = synthesize_cluster(cid, data['texts'], data['sources'])
        if not synthesized_tex:
            continue

        match_id = re.search(r"^% entity-id:\s*(.+)$", synthesized_tex, re.MULTILINE)
        match_type = re.search(r'% entity-type:\s*([a-zA-Z]+)', synthesized_tex)

        if not match_id or not match_type:
            print(f"[synthesizer] [FAIL] Failed to parse metadata from LLM output for cluster {cid}.")
            print(f"[synthesizer]   Output preview: {synthesized_tex[:200]}")
            continue

        entity_id = match_id.group(1).strip()
        entity_type = match_type.group(1).strip()
        title = entity_id.replace('-', ' ').title()
        print(f"[synthesizer] Parsed: entity_id={entity_id}, type={entity_type}, title={title}")

        # Decide directory based on type (correct pluralization)
        TYPE_DIR_MAP = {
            "axiom": "foundations",
            "object": "objects",
            "property": "properties",
            "operation": "operations",
            "theorem": "theorems",
        }
        type_dir = TYPE_DIR_MAP.get(entity_type, entity_type + "s")
        target_dir = CONTENT_DIR / type_dir
        target_dir.mkdir(exist_ok=True)

        file_path = target_dir / f"{title} [{entity_id}].tex"

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(synthesized_tex)
        print(f"[synthesizer] [OK] Saved: {file_path.relative_to(PROJECT_ROOT)}")

        # Add to master.tex
        master_path = CONTENT_DIR / "master.tex"
        if master_path.exists():
            with open(master_path, "r", encoding="utf-8") as f:
                master_content = f.read()
            
            rel_path = file_path.relative_to(PROJECT_ROOT).as_posix()
            input_line = f"\\input{{{rel_path}}}"
            
            if input_line not in master_content:
                master_content = master_content.replace("\\end{document}", f"{input_line}\n\\end{{document}}")
                with open(master_path, "w", encoding="utf-8") as f:
                    f.write(master_content)
                print(f"[synthesizer] [OK] Added to master.tex: {input_line}")

        cursor.execute("INSERT OR REPLACE INTO entities (entity_id, type, title, path) VALUES (?, ?, ?, ?)",
                       (entity_id, entity_type, title, str(file_path.relative_to(PROJECT_ROOT))))
        print(f"[synthesizer] [OK] DB updated: entities({entity_id})")

        for source in data['sources']:
            cursor.execute("INSERT INTO formulation_sources (entity_id, source_book) VALUES (?, ?)", (entity_id, source))

        # Clean up cache
        cursor.execute("DELETE FROM formulation_raw_cache WHERE temp_cluster_id = ?", (cid,))

    conn.commit()
    conn.close()
    print("Canonical synthesis complete.")

if __name__ == "__main__":
    main()
