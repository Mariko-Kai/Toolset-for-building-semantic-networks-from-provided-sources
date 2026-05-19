import sqlite3
import urllib.request
import json
import uuid
import re
import argparse
import sys
import io
import os
import time
from pathlib import Path

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.export_to_lean import query_llm, setup_provider, setup_lean_provider, _LLM_PROVIDER
from pipeline.config import PROVIDERS, resolve_module_config

DB_PATH = PROJECT_ROOT / "mathesis_index.db"
CONTENT_DIR = PROJECT_ROOT / "content"



def detect_entity_type_from_text(raw_texts, has_proof=False):
    """Определяет тип сущности. Согласно архитектуре, всё, что имеет доказательство — теорема."""
    if has_proof:
        return "theorem"
        
    combined = " ".join(raw_texts).lower()
    theorem_keywords = ["теорема", "лемма", "следствие", "theorem", "lemma", "corollary"]
    def_keywords = ["определение", "называется", "определим", "definition", "defined as"]
    
    # 1. Strong theorem check
    for kw in theorem_keywords:
        if kw in combined:
            return "theorem"
            
    # 2. Strong definition check
    for kw in def_keywords:
        if kw in combined:
            return "definition"
            
    # Default fallback
    return "definition"

def build_synthesis_prompt(cluster_id, formulations, sources, entity_type, implicit_assumptions="", canonical_term=""):
    """Строит компактный промпт для синтеза. Оптимизирован для скорости на GTX 1650."""
    text_input = "\n".join([f"[{s}]: {t}" for s, t in zip(sources, formulations)])

    target_requirement = ""
    if canonical_term:
        target_requirement = f"\nCRITICAL: Your goal is to synthesize the definition for: '{canonical_term}'. DO NOT drift into other topics (e.g. if the term is about real numbers, DO NOT use complex numbers unless explicitly mentioned in the sources)."

    rules = r"""OUTPUT FORMAT:
Before writing the final LaTeX code, you MUST output a `<semantic_mapping>` block where you explicitly map the informal textbook concepts to their strict Type Theory equivalents:

<semantic_mapping>
1. Variables & Types: [List all variables and state whether they are Types (:) or Sets (∈)]
2. Data Structures: [Explain how you will represent complex objects like partitions or sequences]
3. Implicit Bounds: [List any hidden variables, like `n : ℕ`, needed to make the definition strict]
</semantic_mapping>

[Your final canonical LaTeX output follows here...]

OUTPUT: Only LaTeX. No ```latex blocks. Include:
% entity-id: <prefix-short-id>
% entity-type: <object|property|operation|theorem>"""
    
    if target_requirement:
        rules += target_requirement

    rules += r"""

CRITICAL HEURISTICS & ANTI-PATTERNS TO AVOID:
1. Types vs. Sets (The \colon vs \in rule): 
   Never confuse belonging to a fundamental type with belonging to a subset. 
   - BAD: "x \in \mathbb{R}" when declaring a variable. 
   - GOOD: "x \colon \mathbb{R}" (in LaTeX) or "(x : ℝ)" (in Lean). Use "\in" ONLY for subsets, e.g., "x \in [a, b]".

2. Analytical vs. Computational Structures (The List rule):
   Never use computational data structures like `List` or `Array` to represent continuous mathematical concepts (partitions, sequences, covers).
   - BAD: Representing a partition as `P : List ℝ`.
   - GOOD: Representing a partition as a function `(n : ℕ) (t : ℕ → ℝ)` bounded by `Finset.range n`.

3. Unpacking Informal Notation (The Ellipsis rule):
   Textbooks use informal ellipses like "{t_0, ..., t_n}". You must explicitly unpack these into rigorous functions and index bounds. Identify implicit dependencies (e.g., if a sequence is finite, you must introduce its length `n : ℕ` as a separate variable).

4. Tautology & Complexity Check:
   If you find yourself writing repetitive logical tautologies (e.g., `x ≠ y → x ≠ y`) or overly complex index bounds, your underlying type choice is wrong. Stop and re-evaluate your data structures.

5. Strict Semantic Identifiers (The Self-Describing ID Rule):
   When generating \entityref{id}{text} or defining a new entity-id, the `id` MUST be globally unambiguous, self-documenting, and resistant to namespace collisions. 
   
   NEVER use bare, generic nouns or adjectives. You MUST include the domain or the parent mathematical object in the ID.
   
   Format: {type}-{domain_or_parent}-{concept}
   
   - BAD: `op-mesh` (Mesh of what? A graph? A 3D model? A partition?)
   - GOOD: `op-partition-mesh` (Clearly states this is the mesh of a partition)
   
   - BAD: `prop-bounded` (Is a function bounded? A set? A sequence?)
   - GOOD: `prop-function-bounded` or `prop-set-bounded`
   
   - BAD: `op-addition` 
   - GOOD: `op-real-addition` or `op-matrix-addition` (Unless using the Late Binding abstract pattern like `op-add-abstract`)

   If a concept belongs to a specific mathematical domain, prefix it explicitly to help the Lean 4 translator map it to the correct Mathlib namespace.

CRITICAL NAMING RULE: The entity-id MUST follow the Mathesis architecture standard:
- if type is object: prefix MUST be `obj-` (e.g. obj-real-numbers)
- if type is property: prefix MUST be `prop-` (e.g. prop-continuous)
- if type is operation: prefix MUST be `op-` (e.g. op-riemann-integral)
- if type is theorem: prefix MUST be `thm-` (e.g. thm-weierstrass)
- if type is axiom: prefix MUST be `axm-`(e.g. axm-zfc-axiom-of-pairing)
DO NOT use `def-` as a prefix.

CRITICAL: Generate EXACTLY ONE mathematical entity. DO NOT repeat the output. DO NOT provide multiple versions. One % entity-id, one % entity-type, and the LaTeX block(s).

MACROS: \mForall, \mExists, \mImplies, \mIff, \mAnd, \mOr, \mNot, \mDefinedAs, \mathrm.
REFS: \entityref{entity-id}{symbol} for derived entities.
ABS MACROS: \entityref{op-abs-abstract}{\mathrm{abs}}(x), \entityref{op-norm-abstract}{\mathrm{norm}}(x), \entityref{op-supremum}{\sup}_{x \in A} f(x) or \entityref{op-supremum}{\sup}(S), \entityref{op-infimum}{\inf}_{x \in A} f(x) or \entityref{op-infimum}{\inf}(S) (NEVER use \mAbs, \mNorm, \mSup, \mInf, or raw |x|, \|x\|).

TERMINALS (NEVER wrap in \entityref): \emptyset = < > \leq \geq 0 1 \infty \varepsilon \delta \mathrm

CRITICAL WRAPPING RULE: By default, ALL mathematical entities/concepts/operators in your formulas MUST be wrapped in \entityref{entity-id}{symbol}, unless they are explicitly listed as terminals to NEVER wrap. If you encounter an entity that is unknown or not explicitly provided in the context, you MUST still wrap it and construct a logical, type-prefixed entity-id for it per the documented naming rules above (e.g. \entityref{op-supremum}{\sup}, \entityref{op-infimum}{\inf}, \entityref{op-limit}{\lim}).

TYPING: Every formula MUST start with variable declarations via quantors:
\mForall{f \colon \entityref{obj-closed-interval}{[a,b]} \mTo \entityref{obj-real-numbers}{\mathbb{R}}}

PURE MATH RULE: For \begin{theorem}, \begin{object}, \begin{property}, and \begin{operation} blocks, NO NATURAL LANGUAGE IS ALLOWED AT ALL. NO English, NO Russian, NO plain text, NO "Note", NO "Remark", NO explanations. The content MUST be 100% formal math symbols and macros. ALL formulas MUST be wrapped in display math blocks \[ ... \]. Inline math $...$ is FORBIDDEN.
Natural language and explanatory notes are ONLY permitted inside \begin{proof} blocks. ALL math objects/variables in proofs MUST be correctly wrapped with \entityref or math macros.
"""

    if implicit_assumptions:
        rules += f"\nIMPLICIT ASSUMPTIONS DETECTED IN TEXTBOOK (Apply these to your variable declarations!):\n{implicit_assumptions}\n"

    example = r"""EXAMPLE:
% entity-id: thm-weierstrass-extreme
% entity-type: theorem
\begin{theorem}[Weierstrass Extreme Value]
\mForall{f \colon \entityref{obj-closed-interval}{[a,b]} \mTo \entityref{obj-real-numbers}{\mathbb{R}}}
\quad \entityref{prop-continuous}{f}
\mImplies \mExists{c \in \entityref{obj-closed-interval}{[a,b]}}
\mForall{x \in \entityref{obj-closed-interval}{[a,b]}} \quad f(x) \leq f(c)
\end{theorem}
"""

    if entity_type == "theorem":
        prompt = rf"""Synthesize a strict formal THEOREM + PROOFS from these sources:
{text_input}

{rules}
{example}
Generate \begin{{theorem}}[Name] ... \end{{theorem}}.
Then generate TWO proofs in parallel: one in Russian and one in English.
Format:
\begin{{proof}}[RU]
...
\end{{proof}}
\begin{{proof}}[EN]
...
\end{{proof}}

Proofs can contain natural language, but all math entities must be formally wrapped."""
    else:
        prompt = rf"""Synthesize a strict formal DEFINITION from these sources:
{text_input}

{rules}
{example}

CRITICAL DEFINITION RULES:
1. NO EQUIVALENCE: You are STRICTLY FORBIDDEN from using `\mIff` (\iff) or `=` at the root level to connect the term to its definition.
2. USE PREDICATES: You MUST define the concept as a named predicate (e.g., `\mathrm{{IsDerivative}}(f, x, L)`).
3. USE \mDefinedAs: Use the `\mDefinedAs` macro to assign the logical condition to your predicate.

BAD EXAMPLE:
\left( f'(x) = L \right) \mIff \left( L = \entityref{{op-limit}}{{\lim}}_{{h \to 0}} \frac{{f(x + h) - f(x)}}{{h}} \right)

GOOD EXAMPLE:
\mathrm{{IsDerivative}}(f, x, L) \mDefinedAs \left( L = \entityref{{op-limit}}{{\lim}}_{{h \to 0}} \frac{{f(x + h) - f(x)}}{{h}} \right)

Generate \begin{{object}}[Name] ... \end{{object}} (or property/operation).
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

def check_forbidden_macros(latex: str, entity_type: str) -> list:
    """Checks if definitions use forbidden macros like \\mIff."""
    errors = []
    if entity_type != "theorem" and r"\mIff" in latex:
        errors.append("ОШИБКА: Использование \\mIff в определениях/операциях строго запрещено. Используйте предикат и макрос \\mDefinedAs.")
    return errors

def synthesize_cluster(cluster_id, formulations, sources, page_refs, has_proof=False, model="qwen3:8b", skip_validation=False, canonical_term=""):
    import time
    print(f"\n{'='*60}", flush=True)
    print(f"[synthesizer] Cluster: {cluster_id}", flush=True)
    print(f"[synthesizer] Sources: {', '.join(sources)} ({len(formulations)} formulations)", flush=True)

    entity_type = detect_entity_type_from_text(formulations, has_proof=has_proof)
    print(f"[synthesizer] Detected entity type: {entity_type}", flush=True)

    max_attempts = 3
    print(f"[synthesizer] Starting LLM Synthesis Loop (max {max_attempts} attempts)...", flush=True)

    current_attempt = 1
    semantic_error_feedback = ""
    syntax_error_feedback = ""
    implicit_assumptions = ""
    semantic_map = ""
    
    latex_content = ""
    lean_code = ""
    valid_lean_code = None

    from pipeline.export_to_lean import translate_to_lean_via_llm, translate_to_lean_regex, is_semantic_error
    from pipeline.lean_validator import validate_entity, discover_mathlib_signatures
    from pipeline.ensemble_extractor import gather_implicit_assumptions
    from pipeline.export_to_lean import _LLM_PROVIDER
    active_provider_name = (_LLM_PROVIDER or "OLLAMA").upper()

    while current_attempt <= max_attempts:
        print(f"\n[synthesizer] --- Attempt {current_attempt}/{max_attempts} ---", flush=True)
        
        # 1. Regenerate LaTeX if missing or if semantic error occurred
        if not latex_content or semantic_error_feedback:
            prompt = build_synthesis_prompt(cluster_id, formulations, sources, entity_type, implicit_assumptions, canonical_term=canonical_term)
            current_prompt = prompt
            
            if semantic_error_feedback:
                print(f"[synthesizer] Injecting semantic/type error feedback into LaTeX prompt...", flush=True)
                current_prompt += f"\n\nПРЕДУПРЕЖДЕНИЕ: Твоя предыдущая формулировка семантически неполна или отклонена формализатором Lean.\nОбратная связь от Lean:\n{semantic_error_feedback}\n\nОБЯЗАТЕЛЬНО явно укажи все неявные типы, кванторы (∀, ∃) и домены."

            # 1a. Internal LLM Retry Loop for LaTeX Generation
            response = ""
            for inner_attempt in range(1, 4):
                print(f"[synthesizer] Sending prompt to {active_provider_name} LLM to generate LaTeX (Inner Attempt {inner_attempt}/3)...", flush=True)
                t0 = time.time()
                response = query_llm(current_prompt, model=model)
                elapsed = time.time() - t0
                
                if response and len(response.strip()) >= 10:
                    print(f"[synthesizer] LLM responded in {elapsed:.1f}s ({len(response)} chars)", flush=True)
                    from pipeline.export_to_lean import log_to_file
                    synth_log = f"=== PROMPT ===\n{current_prompt}\n\n=== RESPONSE ===\n{response}\n"
                    log_to_file("synthesis/latex", synth_log, entity_id=cluster_id, attempt=current_attempt)
                    break
                
                print(f"[synthesizer] [WARN] LLM returned empty/short response. Inner retry {inner_attempt}/3 in 2s...")
                time.sleep(2)

            if not response or len(response.strip()) < 10:
                print("[synthesizer] [ERROR] LaTeX generation failed after 3 internal retries. Failing main attempt.")
                current_attempt += 1
                semantic_error_feedback = "LLM response was empty or API error occurred."
                continue

            response = re.sub(r'^```latex\s*', '', response, flags=re.MULTILINE)
            response = re.sub(r'^```\s*', '', response, flags=re.MULTILINE)

            # Parse semantic mapping
            map_match = re.search(r'<semantic_mapping>(.*?)</semantic_mapping>', response, re.DOTALL)
            if map_match:
                lines = [f"% {line}" for line in map_match.group(1).strip().splitlines()]
                semantic_map = "% === SEMANTIC MAPPING ===\n" + "\n".join(lines) + "\n% ========================\n\n"
            else:
                semantic_map = ""

            # Parse LaTeX block
            header_match = re.search(r'(% entity-id:.*)', response, re.DOTALL)
            if header_match:
                latex_content = header_match.group(1).strip()
                second_header = re.search(r'\n% entity-id:', latex_content[1:])
                if second_header:
                    latex_content = latex_content[:second_header.start() + 1].strip()
            else:
                env_match = re.search(r'(\\begin\{[a-z]+\}.*?\\end\{[a-z]+\})', response, re.DOTALL)
                if env_match:
                    latex_content = env_match.group(1).strip()
                else:
                    latex_content = response

            latex_content = enforce_single_entity(latex_content)
            latex_content = sanitize_terminal_entityrefs(latex_content)
            latex_content = sanitize_raw_delimiters(latex_content)
            
            # Check for natural language violations
            nl_warnings = warn_natural_language(latex_content)
            # Check for forbidden macros (mIff in definitions)
            macro_warnings = check_forbidden_macros(latex_content, entity_type)
            
            all_warnings = nl_warnings + macro_warnings
            if all_warnings:
                print(f"[synthesizer] [WARN] Rule violations detected: {all_warnings}")
                semantic_error_feedback = "\n".join(all_warnings)
                current_attempt += 1
                continue
                
            semantic_error_feedback = ""
            syntax_error_feedback = ""
            lean_code = ""

        # 2. Extract metadata for Lean Translation
        match_id_temp = re.search(r"^% entity-id:\s*(.+)$", latex_content, re.MULTILINE)
        match_type_temp = re.search(r'% entity-type:\s*([a-zA-Z]+)', latex_content)
        temp_eid = match_id_temp.group(1).strip() if match_id_temp else "temp_entity"
        temp_etype = match_type_temp.group(1).strip() if match_type_temp else "axiom"

        # Mathlib discovery
        import string
        clean_title = temp_eid.replace('def-', '').replace('op-', '').replace('obj-', '').replace('prop-', '').replace('thm-', '').replace('-', ' ')
        entity_words = [w for w in clean_title.split() if len(w) > 2]
        discovery_terms = [w.title() for w in entity_words]
        if len(entity_words) >= 2:
            discovery_terms.append(''.join(w.title() for w in entity_words))
        discovery_terms = list(set(discovery_terms))[:4]
        
        signatures = []
        if discovery_terms and not syntax_error_feedback: 
            print(f"  [synthesizer] Running Mathlib discovery for terms: {discovery_terms}")
            try:
                signatures = discover_mathlib_signatures(discovery_terms)
            except Exception as e:
                pass
        hints = "\n".join(signatures) if signatures else "No hints found."

        # 3. Translate to Lean (with internal retry)
        lean_code_new = ""
        for inner_attempt in range(1, 4):
            print(f"  [synthesizer] Translating to Lean (Inner Attempt {inner_attempt}/3)...", flush=True)
            lean_code_new = translate_to_lean_via_llm(
                temp_eid, temp_etype, latex_content, 
                model=model, mathlib_hints=hints, 
                error_feedback=syntax_error_feedback, previous_code=lean_code,
                attempt=current_attempt
            )
            if lean_code_new:
                break
            print(f"  [synthesizer] [WARN] Lean translation returned empty. Inner retry {inner_attempt}/3 in 2s...")
            time.sleep(2)

        if not lean_code_new and not lean_code:
            lean_code_new = translate_to_lean_regex(temp_eid, temp_etype, latex_content)
            
        lean_code = lean_code_new or lean_code

        if skip_validation:
            print("  [SKIP] Skipping Lean validation loop (--no-validate passed).")
            valid_lean_code = lean_code
            break

        if lean_code:
            # Check if def is missing for non-theorems/non-axioms (objects, properties, operations)
            if temp_etype in ["object", "property", "operation"] and not re.search(r'\bdef\b', lean_code):
                print(f"  [FAIL] Missing required 'def' keyword for entity type '{temp_etype}'. Rejected.")
                result = {
                    "status": "failed",
                    "errors": [{
                        "line": 1,
                        "column": 1,
                        "message": f"CRITICAL RULE VIOLATION: Your Lean code for {temp_etype} '{temp_eid}' is declared as a `theorem` or `lemma` (or has no declaration). You MUST declare EXACTLY ONE `def` using `def {temp_eid.replace('-', '_')} ... : Prop := ...`. You are strictly FORBIDDEN from using `theorem` or `lemma` as the primary declaration for objects, operations, or properties!"
                    }]
                }
            else:
                print(f"  Lean validating: {lean_code[:80]}...")
                result = validate_entity(temp_eid, lean_code)
        else:
            print("  No translatable content for Lean validation, skipping.")
            result = {"status": "success", "errors": []}

        if result["status"] == "success" and not is_semantic_error(lean_code, [], temp_etype):
            print("  [OK] Lean validation passed!")
            valid_lean_code = lean_code
            break
        elif result["status"] == "timeout":
            print("  [TIMEOUT] Lean validation timed out. Proceeding without validation.")
            break
        else:
            print(f"  [FAIL] Lean validation failed or model cheated.")
            
            messages = []
            for e in result["errors"][:3]:
                msg = e.get("message", "")
                if "don't know how to synthesize placeholder" in msg:
                    type_match = re.search(r'of type\n\s*(.+)', msg)
                    if type_match:
                        msg = f"ОШИБКА ПЛЕЙСХОЛДЕРА (`_`): ожидается точный тип `{type_match.group(1).strip()}`."
                messages.append(msg)
                
            if is_semantic_error(lean_code, result["errors"], temp_etype):
                print("  [!] Semantic error detected (e.g. type mismatch). Routing back to LaTeX synthesizer.")
                semantic_error_feedback = "\n".join(messages)
                
                # Context Recovery (Look-back)
                if not implicit_assumptions:
                    print("  [*] Triggering Context Recovery (looking back at previous pages for implicit assumptions)...")
                    recovered_parts = []
                    for src, p_ref in zip(sources, page_refs):
                        if p_ref > 0:
                            assump = gather_implicit_assumptions(src, p_ref, "math entity", model)
                            if assump:
                                recovered_parts.append(f"[{src}]: {assump}")
                    
                    if recovered_parts:
                        implicit_assumptions = "\n".join(recovered_parts)
                        print(f"  [+] Recovered implicit assumptions:\n{implicit_assumptions}")
                    else:
                        print("  [-] No implicit assumptions found in preceding pages.")
                        implicit_assumptions = "NONE FOUND" # Mark as checked
            else:
                print(f"  [!] Syntax/Translation error detected. Routing back to Lean formalizer.")
                syntax_error_feedback = "\n".join(messages)
                
                # Check for sorry abuse in definitions or theorem formulations
                has_sorry_abuse = False
                sorry_warning = ""
                if temp_etype not in ["theorem"]:
                    # Isolate the definition block by splitting at the first theorem/lemma keyword
                    parts = re.split(r'\b(?:theorem|lemma)\b', lean_code, maxsplit=1)
                    definition_part = parts[0]
                    if "sorry" in definition_part:
                        has_sorry_abuse = True
                        sorry_warning = "CRITICAL ERROR: You used `sorry` inside the core `def` definition of an operation/object/property. This is strictly FORBIDDEN. You MUST provide a real, working Mathlib declaration body without `sorry`!"
                else:
                    parts = lean_code.rsplit(':=', 1)
                    if len(parts) > 1 and "sorry" in parts[0]:
                        has_sorry_abuse = True
                        sorry_warning = "CRITICAL ERROR: You used `sorry` in the theorem formulation/statement. This is strictly FORBIDDEN. You must write a complete, precise theorem statement, and `sorry` is only allowed as the proof after `:=`!"
                
                if has_sorry_abuse:
                    if syntax_error_feedback:
                        syntax_error_feedback = sorry_warning + "\n" + syntax_error_feedback
                    else:
                        syntax_error_feedback = sorry_warning
                
            # Log the Lean compile errors
            error_feedback = "\n".join([f"Line {e['line']}: {e['message']}" for e in result.get("errors", [])])
            from pipeline.export_to_lean import log_to_file
            log_to_file("lean_errors", error_feedback, entity_id=temp_eid, attempt=current_attempt)

            current_attempt += 1

    return latex_content, valid_lean_code, semantic_map

def rebuild_master_tex():
    master_path = CONTENT_DIR / "master.tex"
    print(f"\n[master-rebuild] Rebuilding {master_path.relative_to(PROJECT_ROOT)} from current content directory...", flush=True)
    
    # 1. Discover all tex files
    tex_files = []
    for filepath in CONTENT_DIR.rglob("*.tex"):
        if filepath.name in ("master.tex", "TEMPLATE.tex", "mathesis.sty"):
            continue
        tex_files.append(filepath)
        
    # 2. Parse ID and dependencies of each file
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
            
            # Extract dependencies
            deps = list(set(re.findall(r'\\entityref\{([^{}]+)\}', text)))
            
            # Extract abstract macro dependencies
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
            print(f"  [WARN] Failed to parse {filepath.name}: {e}", flush=True)
            
    # 3. Topological Sort using DFS
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
        
    # 4. Generate master.tex content
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
        
    print(f"[master-rebuild] [OK] Rebuilt master.tex with {len(order)} entities in topological order!\n", flush=True)


def main():
    global _LLM_PROVIDER, _GEMINI_CLIENT, _GEMINI_MODEL_NAME, _OPENAI_CLIENT, _OPENAI_MODEL_NAME, _GROQ_CLIENT, _GROQ_MODEL_NAME
    parser = argparse.ArgumentParser(description="Canonical Synthesizer")
    parser.add_argument("--cv-model", type=str, default="glm-ocr", help="CV Model")

    # ── Глобальные аргументы (оверрайдят все модули) ───────────────────────
    parser.add_argument("--provider", type=str, default=None, choices=PROVIDERS,
                        help="Глобальный LLM провайдер")
    parser.add_argument("--model",    type=str, default=None,
                        help="Глобальная модель")
    parser.add_argument("--api-key",  type=str, default=None,
                        help="Глобальный API ключ")

    # ── Per-module аргументы для synth ─────────────────────────────────────
    parser.add_argument("--synth-provider", type=str, default=None, choices=PROVIDERS,
                        help="Провайдер LLM для модуля синтеза")
    parser.add_argument("--synth-model",    type=str, default=None,
                        help="Модель LLM для модуля синтеза")
    parser.add_argument("--synth-api-key",  type=str, default=None,
                        help="API ключ для модуля синтеза")

    # ── Аргументы Lean-провайдера ──────────────────────────────────
    parser.add_argument("--lean-provider", type=str, default=None, choices=PROVIDERS,
                        help="Отдельный провайдер для Lean формализации")
    parser.add_argument("--lean-api-key",  type=str, default=None, help="API Key for Lean provider")
    parser.add_argument("--lean-model",    type=str, default=None, help="Model for Lean provider")
    parser.add_argument("--no-validate", action="store_true", help="Skip Lean validation during synthesis")
    parser.add_argument("--canonical-term", type=str, default="", help="The target mathematical term to synthesize")
    args = parser.parse_args()

    # Разрешаем итоговую конфигурацию модуля synth
    provider, model, api_key = resolve_module_config(
        module="synth",
        global_provider=args.provider,
        global_model=args.model,
        global_api_key=args.api_key,
        module_provider=args.synth_provider,
        module_model=args.synth_model,
        module_api_key=args.synth_api_key,
    )

    # Initialize LLM providers via shared logic
    setup_provider(provider, api_key=api_key, model=model)
    if args.lean_provider:
        setup_lean_provider(args.lean_provider, api_key=args.lean_api_key, model=args.lean_model)

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Ensure mapping & pending_edges tables exist
    cursor.execute("CREATE TABLE IF NOT EXISTS cluster_entity_map (cluster_id TEXT PRIMARY KEY, entity_id TEXT)")
    cursor.execute("CREATE TABLE IF NOT EXISTS pending_edges (source_id TEXT, raw_dep TEXT, status TEXT DEFAULT 'pending')")

    cursor.execute("SELECT temp_cluster_id, source_book, raw_text, has_proof, page_ref, raw_deps FROM formulation_raw_cache WHERE temp_cluster_id IS NOT NULL")
    rows = cursor.fetchall()

    clusters = {}
    for cid, source, text, proof_flag, page_ref, raw_deps_json in rows:
        if cid not in clusters:
            clusters[cid] = {'sources': [], 'texts': [], 'has_proof': False, 'page_refs': [], 'deps': []}
        clusters[cid]['sources'].append(source)
        clusters[cid]['texts'].append(text)
        clusters[cid]['page_refs'].append(page_ref or 0)
        if proof_flag == 1:
            clusters[cid]['has_proof'] = True
        if raw_deps_json:
            try:
                deps_list = json.loads(raw_deps_json)
                if isinstance(deps_list, list):
                    clusters[cid]['deps'].extend(deps_list)
                else:
                    clusters[cid]['deps'].append(str(deps_list))
            except Exception:
                pass

    print(f"[synthesizer] Found {len(clusters)} cluster(s) to synthesize.")
    if not clusters:
        print("[synthesizer] Nothing to synthesize. Exiting.")
        conn.close()
        return

    processed_entities = set()

    for cid, data in clusters.items():
        synthesized_tex, valid_lean_code, semantic_map = synthesize_cluster(
            cid, data['texts'], data['sources'], data['page_refs'], 
            has_proof=data['has_proof'], model=args.model, 
            skip_validation=args.no_validate, canonical_term=args.canonical_term
        )
        if not synthesized_tex:
            continue

        match_id = re.search(r"^% entity-id:\s*(.+)$", synthesized_tex, re.MULTILINE)
        match_type = re.search(r'% entity-type:\s*([a-zA-Z]+)', synthesized_tex)

        if not match_id or not match_type:
            print(f"[synthesizer] [FAIL] Failed to parse metadata from LLM output for cluster {cid}.")
            print(f"[synthesizer]   Output preview: {synthesized_tex[:200]}")
            continue

        entity_id = match_id.group(1).strip()
        
        # Prevent rewriting the same entity multiple times across different clusters
        if entity_id in processed_entities:
            print(f"[synthesizer] [SKIP] Entity '{entity_id}' already synthesized in this run. Skipping redundant cluster.")
            continue
            
        entity_type = match_type.group(1).strip()
        title = entity_id.replace('-', ' ').title()
        print(f"[synthesizer] Parsed: entity_id={entity_id}, type={entity_type}, title={title}")
        processed_entities.add(entity_id)

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

        # Prepend defined-in metadata and semantic_map from all source/page references
        defined_in_parts = [f"{src} (page {p_ref})" for src, p_ref in zip(data['sources'], data['page_refs'])]
        defined_in_str = ", ".join(defined_in_parts)
        tex_to_save = f"% defined-in: {defined_in_str}\n{semantic_map}{synthesized_tex}"

        with open(file_path, "w", encoding="utf-8") as f:
            f.write(tex_to_save)
        print(f"[synthesizer] [OK] Saved: {file_path.relative_to(PROJECT_ROOT)}")

        # Save validated lean code if available
        if valid_lean_code:
            lean_dir = PROJECT_ROOT / "lean_validator" / "Validated"
            lean_dir.mkdir(parents=True, exist_ok=True)
            lean_file_path = lean_dir / f"{entity_id}.lean"
            with open(lean_file_path, "w", encoding="utf-8") as f:
                f.write(valid_lean_code)
            print(f"[synthesizer] [OK] Saved Lean code: {lean_file_path.relative_to(PROJECT_ROOT)}")
            
            # Append to SuccessfulEntities.lean
            success_file = PROJECT_ROOT / "lean_validator" / "SuccessfulEntities.lean"
            if not success_file.exists():
                with open(success_file, "w", encoding="utf-8") as f:
                    f.write("import Mathlib\n\n-- Valid entities generated by Goedel-Formalizer\n\n")
            with open(success_file, "a", encoding="utf-8") as f:
                f.write(f"-- Entity: {entity_id} | Type: {entity_type}\n{valid_lean_code}\n\n")



        cursor.execute("INSERT OR REPLACE INTO entities (entity_id, type, title, path) VALUES (?, ?, ?, ?)",
                       (entity_id, entity_type, title, str(file_path.relative_to(PROJECT_ROOT))))
        print(f"[synthesizer] [OK] DB updated: entities({entity_id})")

        for source in data['sources']:
            cursor.execute("INSERT INTO formulation_sources (entity_id, source_book) VALUES (?, ?)", (entity_id, source))

        # Map cluster -> entity and record parsed deps
        cursor.execute("INSERT OR REPLACE INTO cluster_entity_map (cluster_id, entity_id) VALUES (?, ?)", (cid, entity_id))
        unique_deps = list({d.strip() for d in data.get('deps', []) if d and isinstance(d, str)})
        import json as _json
        print(f"[synthesizer] ParsedDeps: {_json.dumps({'entity_id': entity_id, 'deps': unique_deps}, ensure_ascii=False)}", flush=True)
        for dep in unique_deps:
            cursor.execute("INSERT INTO pending_edges (source_id, raw_dep, status) VALUES (?, ?, 'pending')", (entity_id, dep))

        # Clean up cache
        cursor.execute("DELETE FROM formulation_raw_cache WHERE temp_cluster_id = ?", (cid,))

    conn.commit()
    conn.close()
    
    print("Canonical synthesis complete.")

if __name__ == "__main__":
    main()
