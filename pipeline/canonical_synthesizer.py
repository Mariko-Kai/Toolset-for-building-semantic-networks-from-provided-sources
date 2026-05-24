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

from pipeline.config import PROVIDERS, resolve_module_config
from pipeline.model_manager import ModelManager

DB_PATH = PROJECT_ROOT / "db/mathesis_index.db"
CONTENT_DIR = PROJECT_ROOT / "content"



def detect_entity_type_from_text(raw_texts, has_proof=False):
    """Определяет тип сущности. Согласно архитектуре, всё, что имеет доказательство — prop."""
    if has_proof:
        return "prop"
        
    combined = " ".join(raw_texts).lower()
    prop_keywords = ["теорема", "лемма", "следствие", "theorem", "lemma", "corollary", "свойство", "property"]
    
    # Strong prop check
    for kw in prop_keywords:
        if kw in combined:
            return "prop"
            
    # Default fallback
    return "def"

def prepare_macros_from_deps(deps, mgr):
    """Strict Dependency Resolution & Macro Injection."""
    if not deps:
        return ""
    
    unique_deps = list({d.strip() for d in deps if d and isinstance(d, str)})
    
    from pipeline.ollama_wrapper import resolve_entities
    import re
    import json
    import sqlite3
    
    macros_map = {}
    macro_file = PROJECT_ROOT / "content" / "mathesis_macros.sty"
    if macro_file.exists():
        m_content = macro_file.read_text(encoding="utf-8")
        for match in re.finditer(r'\\newcommand\{\\([a-zA-Z0-9_]+)\}(?:\[\d+\])?\{.*?\\hyperlink\{([a-zA-Z0-9_\-]+)\}', m_content):
            macros_map[match.group(2)] = "\\" + match.group(1)

    available_macros = []
    resolved_eids = []
    
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    cursor = conn.cursor()

    for dep in unique_deps:
        resolved, _ = resolve_entities("", dep, [])
        if resolved:
            eid = resolved[0]["entity_id"]
            resolved_eids.append(eid)
            if eid in macros_map:
                available_macros.append(f"{macros_map[eid]} (from {eid})")
            else:
                # Stub it if not in .sty
                pascal_name = "".join(w.title() for w in re.sub(r'[^\w\s]', '', dep).strip().split())
                if not pascal_name: continue
                new_macro = f"\\{pascal_name}"
                available_macros.append(f"{new_macro} (from {eid})")
                if macro_file.exists():
                    macro_def = f"\\newcommand{{{new_macro}}}{{\\hyperlink{{{eid}}}{{\\text{{{pascal_name}}}}}}}"
                    with open(macro_file, "a", encoding="utf-8") as f:
                        f.write(f"\n% Auto-generated stub for {dep}\n{macro_def}\n")
        else:
            # Complete Miss: generate stub entity + macro
            clean_dep = re.sub(r'[^\w\s]', '', dep).strip()
            if not clean_dep:
                continue
            
            pascal_name = "".join(w.title() for w in clean_dep.split())
            new_eid = f"def-{clean_dep.replace(' ', '-').lower()}"
            new_macro = f"\\{pascal_name}"
            
            # Quick arity check via LLM
            prompt = f'What is the standard LaTeX notation for "{dep}" and how many arguments does it take? Return EXACTLY valid JSON with keys "notation" (e.g. "C(#1)") and "args" (integer).'
            try:
                resp = mgr.query_llm(prompt, json_mode=True, role="extract")
                match = re.search(r'(\{.*\})', resp, re.DOTALL)
                if match: resp = match.group(1)
                data = json.loads(resp)
                args = data.get("args", 0)
                notation = data.get("notation", pascal_name)
            except:
                args = 0
                notation = pascal_name
                
            cursor.execute("INSERT OR IGNORE INTO entities (entity_id, type, title) VALUES (?, ?, ?)", (new_eid, "def", dep))
            conn.commit()
            
            if args > 0:
                macro_def = f"\\newcommand{{{new_macro}}}[{args}]{{\\mathopen{{\\hyperlink{{{new_eid}}}{{{notation}}}}}}}\\mathclose{{}}"
            else:
                macro_def = f"\\newcommand{{{new_macro}}}{{\\hyperlink{{{new_eid}}}{{{notation}}}}}"
                
            if macro_file.exists():
                with open(macro_file, "a", encoding="utf-8") as f:
                    f.write(f"\n% Auto-generated stub for {dep}\n{macro_def}\n")
                    
            available_macros.append(f"{new_macro} (from {new_eid})")
            resolved_eids.append(new_eid)

    conn.close()

    if not available_macros:
        return "", resolved_eids
        
    return "\nAVAILABLE MACROS (CRITICAL: You MUST use these instead of standard LaTeX for concepts/types. DO NOT invent standard commands if they are in this list. Example: use \\RealNumbers instead of \\mathbb{R}):\n" + "\n".join([f"- {m}" for m in available_macros]) + "\n", resolved_eids

def build_synthesis_prompt(cluster_id, formulations, sources, entity_type, implicit_assumptions="", canonical_term="", relevant_macros_str=""):
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
% entity-type: <def|prop>"""
    
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

3. Unpacking Informal Notation (The Ellipsis rule):
   Textbooks use informal ellipses like "{t_0, ..., t_n}". You must explicitly unpack these into rigorous functions and index bounds. Identify implicit dependencies (e.g., if a sequence is finite, you must introduce its length `n : ℕ` as a separate variable).

4. Tautology & Complexity Check:
   If you find yourself writing repetitive logical tautologies (e.g., `x ≠ y → x ≠ y`) or overly complex index bounds, your underlying type choice is wrong. Stop and re-evaluate your data structures.

5. Strict Semantic Identifiers (The Self-Describing ID Rule):
   When defining a new entity-id, the `id` MUST be globally unambiguous, self-documenting, and resistant to namespace collisions. 
   
   Format: <type>-{domain_or_parent}-{concept}

CRITICAL NAMING RULE: The entity-id MUST follow the Mathesis architecture standard:
- if type is def: prefix MUST be `def-` (e.g. def-real-numbers, def-continuous, def-riemann-integral)
- if type is prop: prefix MUST be `prop-` (e.g. prop-weierstrass)

CRITICAL: Generate EXACTLY ONE mathematical entity. DO NOT repeat the output. DO NOT provide multiple versions. One % entity-id, one % entity-type, and the LaTeX block(s).

TERMINALS: \emptyset = < > \leq \geq 0 1 \infty \varepsilon \delta \mathrm

CRITICAL WRAPPING RULE: ALL mathematical entities/concepts/operators in your formulas MUST be written using dynamic semantic macros (e.g. \RealNumbers, \Continuous, \AbsAbstract). DO NOT use hardcoded LaTeX like \mathbb{R}, \sup, \in if a macro exists!
NOTE: Local variables (like a, b, f, x) introduced in the current formula MUST NOT be wrapped in semantic macros. Only wrap the types, spaces, and operators.

TYPING: Every formula MUST start with variable declarations via quantors:
\forall f \colon \RealNumbers \to \RealNumbers

PURE MATH RULE: For \begin{definition} and \begin{proposition} blocks, NO NATURAL LANGUAGE IS ALLOWED AT ALL. NO English, NO Russian, NO plain text, NO "Note", NO "Remark", NO explanations. The content MUST be 100% formal math symbols and macros. ALL formulas MUST be wrapped in display math blocks \[ ... \]. Inline math $...$ is FORBIDDEN.
Natural language and explanatory notes are ONLY permitted inside \begin{proof} blocks. ALL math objects/variables/operators in proofs MUST be wrapped in inline math mode `$ ... $`. For example, write $\ClosedInterval{a, b}$ and $f(x)$ instead of \ClosedInterval{a, b} and f(x). Leaving mathematical text/variables naked without `$` is STRICTLY FORBIDDEN!
"""

    if relevant_macros_str:
        rules += relevant_macros_str

    if implicit_assumptions:
        rules += f"\nIMPLICIT ASSUMPTIONS DETECTED IN TEXTBOOK (Apply these to your variable declarations!):\n{implicit_assumptions}\n"

    example = r"""EXAMPLE:
% entity-id: prop-weierstrass-extreme
% entity-type: prop
\begin{proposition}[Weierstrass Extreme Value]
\forall f \colon \ClosedInterval{[a,b]} \to \RealNumbers \;\; \Continuous{f}
\implies \exists c \in \ClosedInterval{[a,b]} \;\;
\forall x \in \ClosedInterval{[a,b]} \quad f(x) \leq f(c)
\end{theorem}
"""

    if entity_type == "prop":
        prompt = rf"""Synthesize a strict formal THEOREM + PROOFS from these sources:
{text_input}

{rules}
{example}
Generate \begin{{proposition}}[Name] ... \end{{proposition}}.
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
1. NO EQUIVALENCE: You are STRICTLY FORBIDDEN from using `\iff` or `=` at the root level to connect the term to its definition.
2. USE PREDICATES: You MUST define the concept as a named predicate (e.g., `\mathrm{{IsDerivative}}(f, x, L)`).
3. USE \coloneqq: Use the `\coloneqq` macro to assign the logical condition to your predicate.

BAD EXAMPLE:
\left( f'(x) = L \right) \iff \left( L = \lim_{{h \to 0}} \frac{{f(x + h) - f(x)}}{{h}} \right)

GOOD EXAMPLE:
\mathrm{{IsDerivative}}(f, x, L) \coloneqq \left( L = \lim_{{h \to 0}} \frac{{f(x + h) - f(x)}}{{h}} \right)

Generate \begin{{definition}}[Name] ... \end{{definition}}.
CRITICAL: DO NOT add any notes, remarks, text, or English words outside or inside the block. ONLY the formal mathematical formula."""
    return prompt

def enforce_single_entity(latex: str) -> str:
    """If LLM generated multiple entities, keep only the first one."""
    # 1. Truncate at the second occurrence of metadata
    ids = list(re.finditer(r'^\s*% entity-id:', latex, re.MULTILINE))
    if len(ids) > 1:
        latex = latex[:ids[1].start()].rstrip()
        print(f"[sanitize] Truncated output: {len(ids)} entities found (metadata marker), kept first only.", flush=True)
        return latex

    # 2. Truncate if we see a second main block of the same type
    main_envs = ['theorem', 'lemma', 'property', 'definition', 'axiom', 'object', 'operation']
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
    """Replace raw |...| with \\RealAbsoluteValue{...} inside math blocks."""
    # Only replace simple |expr| patterns (no nested |)
    latex = re.sub(r'(?<!\\)\|([^|]+?)\|', r'\\RealAbsoluteValue{\1}', latex)
    return latex

def check_forbidden_macros(latex: str, entity_type: str) -> list:
    """Checks if definitions use forbidden macros like \\iff."""
    errors = []
    if entity_type != "theorem" and r"\iff" in latex:
        errors.append("ОШИБКА: Использование \\iff в определениях/операциях строго запрещено. Используйте предикат и макрос \\coloneqq.")
    return errors

def synthesize_cluster(cluster_id, formulations, sources, page_refs, has_proof=False, model="qwen3:8b", skip_validation=False, canonical_term="", processed_entities=None, deps=None):
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
    active_provider_name = "ModelManager (synth)"

    while current_attempt <= max_attempts:
        print(f"\n[synthesizer] --- Attempt {current_attempt}/{max_attempts} ---", flush=True)
        
        # 1. Regenerate LaTeX if missing or if semantic error occurred
        if not latex_content or semantic_error_feedback:
            mgr = ModelManager.get_instance()
            relevant_macros_str, resolved_eids = prepare_macros_from_deps(deps, mgr)
            prompt = build_synthesis_prompt(cluster_id, formulations, sources, entity_type, implicit_assumptions, canonical_term, relevant_macros_str)
            current_prompt = prompt
            
            if semantic_error_feedback:
                print(f"[synthesizer] Injecting semantic/type error feedback into LaTeX prompt...", flush=True)
                current_prompt += f"\n\nПРЕДУПРЕЖДЕНИЕ: Твоя предыдущая формулировка семантически неполна или отклонена формализатором Lean.\nОбратная связь от Lean:\n{semantic_error_feedback}\n\nОБЯЗАТЕЛЬНО явно укажи все неявные типы, кванторы (∀, ∃) и домены."

            # 1a. Internal LLM Retry Loop for LaTeX Generation
            response = ""
            for inner_attempt in range(1, 4):
                print(f"[synthesizer] Sending prompt to {active_provider_name} LLM to generate LaTeX (Inner Attempt {inner_attempt}/3)...", flush=True)
                t0 = time.time()
                mgr = ModelManager.get_instance()
                response = mgr.query_llm(current_prompt, role="synth")
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

        # Fast-fail for redundant entities to save LLM tokens and time
        if processed_entities and temp_eid in processed_entities:
            print(f"  [synthesizer] [SKIP] Entity '{temp_eid}' already synthesized. Skipping Lean formalization.")
            valid_lean_code = ""
            break

        # Mathlib discovery
        import string
        clean_title = temp_eid.replace('def-', '').replace('thm-', '').replace('axm-', '').replace('-', ' ')
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
                attempt=current_attempt, local_lemmas=[eid.replace('-', '_') for eid in resolved_eids] if 'resolved_eids' in locals() else []
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
                if temp_etype != "prop":
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
            
            if current_attempt == max_attempts:
                print(f"  [synthesizer] Max attempts reached for {temp_eid}. Applying Fallback to `sorry`...")
                if temp_etype == "prop" and "sorry" not in lean_code:
                    fallback_code = re.sub(r':=.*', ':= by sorry', lean_code, flags=re.DOTALL)
                    res = validate_entity(temp_eid, fallback_code)
                    if res["status"] == "success":
                        print("  [OK] Fallback to sorry compiled successfully.")
                        valid_lean_code = fallback_code
                        break

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
            
            # Extract dependencies using latex_utils macro parser
            from pipeline.latex_utils import extract_dependencies
            deps = extract_dependencies(text)
            
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
    
    # ── Аргументы Embed-провайдера ──────────────────────────────────
    parser.add_argument("--embed-provider", type=str, default=None, choices=PROVIDERS)
    parser.add_argument("--embed-api-key",  type=str, default=None)
    parser.add_argument("--embed-model",    type=str, default=None)

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

    # Initialize LLM providers via ModelManager
    mgr = ModelManager.get_instance()
    mgr.setup_role("synth", provider, model, api_key)
    if args.lean_provider:
        mgr.setup_role("lean", args.lean_provider, args.lean_model, args.lean_api_key)
    if args.embed_provider:
        mgr.setup_role("embed", args.embed_provider, args.embed_model, args.embed_api_key)

    conn = sqlite3.connect(DB_PATH, timeout=10.0)
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
            skip_validation=args.no_validate, canonical_term=args.canonical_term,
            processed_entities=processed_entities, deps=data.get('deps', [])
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
        # Remove standard architectural prefixes before generating human-readable title
        clean_id = re.sub(r'^(def|prop)-', '', entity_id)
        title = clean_id.replace('-', ' ').title()
        print(f"[synthesizer] Parsed: entity_id={entity_id}, type={entity_type}, title={title}")
        processed_entities.add(entity_id)

        # Decide directory based on type (correct pluralization)
        TYPE_DIR_MAP = {
            "def": "defs",
            "prop": "props",
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



        nl_desc = data['texts'][0] if data['texts'] else title
        # Generate embedding for the new entity
        embed_blob = None
        try:
            mgr = ModelManager.get_instance()
            
            # Use 'embed' role if it exists, otherwise it will fallback to main/provider
            embed_vec = mgr.get_embedding(
                nl_desc, 
                provider=getattr(args, "embed_provider", None), 
                model=getattr(args, "embed_model", None),
                role="embed"
            )
            if embed_vec:
                import struct
                embed_blob = struct.pack(f"{len(embed_vec)}f", *embed_vec)
        except Exception as e:
            print(f"[synthesizer] [-] Could not generate embedding: {e}")
        
        cursor.execute("INSERT OR REPLACE INTO entities (entity_id, type, title, path, file_path, lean_path, nl_desc, embedding) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
                       (entity_id, entity_type, title, str(file_path.relative_to(PROJECT_ROOT)), str(file_path.relative_to(PROJECT_ROOT)), str(lean_file_path.relative_to(PROJECT_ROOT)) if valid_lean_code else None, nl_desc, embed_blob))
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
