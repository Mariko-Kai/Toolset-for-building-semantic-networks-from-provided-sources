"""
Export to Lean v2 — LLM-Assisted Translation
=============================================
Translates LaTeX entities to valid Lean 4 code using LLM.
Supports two providers: local Ollama and Google Gemini API.
Falls back to regex-based translation if LLM is unavailable.
Supports incremental validation (saves validated files individually).
"""
import sqlite3
import re
import os
import json
import urllib.request
import time
from pathlib import Path
from collections import defaultdict, deque

try:
    from google import genai
    from google.genai import types
    GEMINI_AVAILABLE = True
except ImportError:
    GEMINI_AVAILABLE = False

try:
    import openai
    OPENAI_AVAILABLE = True
except ImportError:
    OPENAI_AVAILABLE = False

try:
    from gradio_client import Client as GradioClient
    GRADIO_AVAILABLE = True
except ImportError:
    GRADIO_AVAILABLE = False

try:
    from llama_cpp import Llama
    LLAMA_CPP_AVAILABLE = True
except Exception:
    LLAMA_CPP_AVAILABLE = False

import datetime
from pipeline.lean_validator import validate_entity
PROJECT_ROOT = Path(__file__).resolve().parent.parent

def log_to_file(category: str, content: str, entity_id: str = None, attempt: int = None):
    """
    Saves content into a log file in logs/<category>/...
    And also appends to logs/pipeline_realtime.log in real-time with immediate disk flush.
    """
    import os
    import sys
    try:
        logs_dir = PROJECT_ROOT / "logs" / category
        logs_dir.mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.datetime.now().strftime("%Y-%m-%d_%H-%M-%S")
        
        # 1. Write the individual category log file
        parts = [timestamp]
        if entity_id:
            safe_eid = "".join(c for c in str(entity_id) if c.isalnum() or c in "-_")
            parts.append(safe_eid)
        if attempt is not None:
            parts.append(f"attempt_{attempt}")
            
        filename = "_".join(parts) + ".txt"
        file_path = logs_dir / filename
        
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(content)
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass
                
        # 2. Append to the real-time unified streaming log file
        realtime_log = PROJECT_ROOT / "logs" / "pipeline_realtime.log"
        header = f"\n=== [{datetime.datetime.now().isoformat()}] CATEGORY: {category.upper()} | ENTITY: {entity_id} | ATTEMPT: {attempt} ===\n"
        with open(realtime_log, "a", encoding="utf-8") as f:
            f.write(header)
            f.write(content)
            f.write("\n" + "="*80 + "\n")
            f.flush()
            try:
                os.fsync(f.fileno())
            except OSError:
                pass
                
        # 3. Flush standard output buffers for instant console response
        sys.stdout.flush()
        sys.stderr.flush()
    except Exception as e:
        print(f"  [logging-error] Failed to write log to category {category}: {e}")
        sys.stdout.flush()

DB_PATH = PROJECT_ROOT / "mathesis_index.db"
CONTENT_DIR = PROJECT_ROOT / "content"
LEAN_DIR = PROJECT_ROOT / "lean_validator"
VALIDATED_DIR = LEAN_DIR / "Validated"
OUT_FILE = LEAN_DIR / "MathesisGraph.lean"
SUCCESS_FILE = LEAN_DIR / "SuccessfulEntities.lean"



def setup_provider(provider, api_key=None, model=None):
    from pipeline.model_manager import ModelManager
    mgr = ModelManager.get_instance()
    mgr.setup_role('main', provider, model, api_key)

def setup_lean_provider(provider, api_key=None, model=None):
    from pipeline.model_manager import ModelManager
    mgr = ModelManager.get_instance()
    mgr.setup_role('lean', provider, model, api_key)

def setup_preview_provider(provider, api_key=None, model=None):
    from pipeline.model_manager import ModelManager
    mgr = ModelManager.get_instance()
    mgr.setup_role('preview', provider, model, api_key)


def query_llm(prompt, model=None, system_prompt=None, json_mode=False, provider=None):
    from pipeline.model_manager import ModelManager
    mgr = ModelManager.get_instance()
    return mgr.query_llm(prompt, model=model, system_prompt=system_prompt, json_mode=json_mode, provider=provider)


# ── LLM Translation ─────────────────────────────────────────────────────────

def is_semantic_error(lean_code: str, errors: list, entity_type: str) -> bool:
    """
    Determines if Lean compiler errors or generated code indicate a structural/semantic flaw
    that requires fixing the original LaTeX formulation (e.g. missing assumptions).
    """
    # Check compiler errors for structural hints
    for err in errors:
        msg = err.get("message", "").lower()
        if "type mismatch" in msg:
            return True
        if "failed to synthesize instance" in msg:
            return True
        if "don't know how to synthesize placeholder" in msg:
            return True
            
    return False


def translate_to_lean_via_llm(entity_id, entity_type, tex_content, model="goedel:latest", mathlib_hints="", error_feedback=None, previous_code=None, attempt=None):
    """
    Translates LaTeX to Lean 4 using LLM, supporting error feedback for self-correction.
    """
        
    tex_clean = re.sub(r'\\begin\{proof\}.*?\\end\{proof\}', '', tex_content, flags=re.DOTALL)
    tex_clean = re.sub(r'^%.*$', '', tex_clean, flags=re.MULTILINE).strip()
    if not tex_clean:
        return ""

    lean_name = entity_id.replace('-', '_')

    from pipeline.model_manager import ModelManager
    mgr = ModelManager.get_instance()
    target_model = model

    if not target_model:
        target_model = "goedel:latest"

    # Decryption guide of custom LaTeX macros used in the project
    latex_decryption_guide = """=== LaTeX Project Macro Translation Guide ===
Our LaTeX formulas use semantic macros to represent standard mathematical concepts (e.g. \\RealNumbers, \\Continuous, \\Supremum, \\TermConjunction, \\TerForall). You should interpret them by their standard mathematical meaning and translate them into their exact Lean 4 Mathlib equivalents."""

    # Declaration rules based on Entity Type
    declaration_rules = f"""=== Lean 4 Declaration Mapping Rules ===
The target entity has type: '{entity_type}'."""

    # Detect if we are using the Goedel-Formalizer model
    is_goedel = "goedel" in target_model.lower()

    if is_goedel:
        problem_name = lean_name
        informal_statement_content = f"We define a mathematical {entity_type}.\n"
        informal_statement_content += f"Formal definition/theorem in LaTeX:\n${tex_clean}$\n"
        if mathlib_hints:
            informal_statement_content += f"\nRelevant Mathlib signatures:\n{mathlib_hints}\n"
            
        informal_statement_content += f"\n{declaration_rules}\n\n{latex_decryption_guide}\n"
        system_prompt = None

        # Смена фрейма и Prefix Forcing
        if entity_type == "def":
            system_intro = f"Please formalize the following mathematical definition in Lean 4 as a pure `def`. Use the following definition name: {problem_name}"
            prefix_hint = f"\n\nCRITICAL: Output ONLY the Lean code. You MUST start your code exactly like this:\n```lean4\ndef {lean_name}"
        else:
            system_intro = f"Please autoformalize the following natural language problem statement in Lean 4. Use the following theorem name: {problem_name}"
            prefix_hint = f"\n\nCRITICAL: Output ONLY the Lean code. You MUST start your code exactly like this:\n```lean4\ntheorem {lean_name}"

        if error_feedback and previous_code:
            user_prompt = f"""{system_intro}
The natural language statement is: 
{informal_statement_content}

CRITICAL: The previous Lean 4 attempt produced compiler errors. 
Previous Lean 4 code:
{previous_code}

Compiler Errors:
{error_feedback}

Please correct the Lean 4 code so it compiles successfully.
Think before you provide the lean statement.{prefix_hint}"""
        else:
            user_prompt = f"""{system_intro}
The natural language statement is: 
{informal_statement_content}
Think before you provide the lean statement.{prefix_hint}"""
    else:
        # Standard system prompt for general instruction models
        system_prompt = f"""You are an expert mathematician and a Lean 4 formalization specialist.
Your task is to translate mathematical statements into valid Lean 4 declarations.

Textbooks use informal Set Theory (ZFC) and often abuse notation. Your target environment (Lean 4) uses strict Type Theory (Calculus of Inductive Constructions). You must bridge this gap by performing a rigorous semantic translation before generating the final code.

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
   Textbooks use informal ellipses like "{{t_0, ..., t_n}}". You must explicitly unpack these into rigorous functions and index bounds. Identify implicit dependencies (e.g., if a sequence is finite, you must introduce its length `n : ℕ` as a separate variable).

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

OUTPUT FORMAT:
Before writing the final Lean 4 code, you MUST output a `<semantic_mapping>` block where you explicitly map the informal concepts to their strict Type Theory equivalents:

<semantic_mapping>
1. Variables & Types: [List all variables and state whether they are Types (:) or Sets (∈)]
2. Data Structures: [Explain how you will represent complex objects like partitions or sequences]
3. Implicit Bounds: [List any hidden variables, like `n : ℕ`, needed to make the definition strict]
</semantic_mapping>

[Your final Lean 4 code block follows here enclosed in ```lean ... ```]

{declaration_rules}

{latex_decryption_guide}

RULES:
1. Output the `<semantic_mapping>` block first, then the valid Lean 4 code block. No additional markdown formatting, no explanations outside these blocks, no `import` statements.
2. Use Mathlib types: ℝ, ℕ, ℤ, Set, Prop, Type.
3. ALL variables must be bound explicitly (∀ or ∃).
4. Do NOT use LaTeX commands (\\forall, \\in, \\mathbb, etc.)."""

        if error_feedback and previous_code:
            user_prompt = f"""The following Lean 4 code generated for entity '{lean_name}' produced compiler errors.
Code:
{previous_code}

Compiler Errors:
{error_feedback}

Fix the Lean 4 code. Output ONLY the fixed code."""
        else:
            user_prompt = f"""Entity Type: {entity_type}
Name: {lean_name}

LaTeX Source:
{tex_clean}

Mathlib Hints:
{mathlib_hints}

Lean 4 Code:"""

        if error_feedback and previous_code:
            user_prompt = f"""The following Lean 4 code generated for entity '{lean_name}' produced compiler errors.
Code:
{previous_code}

Compiler Errors:
{error_feedback}

Fix the Lean 4 code. Output ONLY the fixed code."""
        else:
            user_prompt = f"""Entity Type: {entity_type}
Name: {lean_name}

LaTeX Source:
{tex_clean}

Mathlib Hints:
{mathlib_hints}

Lean 4 Code:"""

    response = mgr.query_llm(user_prompt, model=target_model, system_prompt=system_prompt, role="lean")
    
    # Log synthesis prompt and response
    synth_log = f"=== SYSTEM PROMPT ===\n{system_prompt}\n\n=== PROMPT ===\n{user_prompt}\n\n=== RESPONSE ===\n{response}\n"
    log_to_file("synthesis/lean", synth_log, entity_id=entity_id, attempt=attempt)
    
    # Extract Lean code blocks robustly
    prompt_ends_in_code_block = is_goedel and entity_type == "def"
    
    parts = re.split(r'```(?:lean|lean4)?\s*', response, flags=re.IGNORECASE)
    blocks = []
    if prompt_ends_in_code_block:
        # Segment 0 is the immediate completion of the prefix
        if parts[0].strip():
            blocks.append(parts[0].strip())
        # Other segments are in between backticks
        for i in range(2, len(parts), 2):
            blocks.append(parts[i].strip())
    else:
        for i in range(1, len(parts), 2):
            blocks.append(parts[i].strip())
            
    if not blocks:
        clean = re.sub(r'^```(?:lean|lean4)?\s*', '', response, flags=re.MULTILINE | re.IGNORECASE)
        clean = re.sub(r'^```\s*$', '', clean, flags=re.MULTILINE)
        if clean.strip():
            blocks.append(clean.strip())
            
    # Select the best block containing actual Lean declarations
    if blocks:
        best_block = blocks[-1]
        for b in reversed(blocks):
            if "def " in b or "theorem " in b or "axiom " in b:
                best_block = b
                break
                
        if prompt_ends_in_code_block and best_block == blocks[0]:
            response = f"def {lean_name} {best_block}"
        else:
            response = best_block
    else:
        response = response.strip()
        
    # Clean up LLM completion prefix junk (like '4', 'lean', 'lean4') on the first line
    lines = response.splitlines()
    if lines and lines[0].strip() in ("4", "lean", "lean4"):
        lines = lines[1:]
    response = "\n".join(lines).strip()
    
    # Auto-heal cheat patterns where reasoning models define helper defs and theorem equivalents
    if entity_type == "def":
        helper_matches = re.findall(r'\bdef\s+([A-Za-z0-9_]+)\b', response)
        helpers = [h for h in helper_matches if h != lean_name]
        
        if helpers and lean_name not in helper_matches:
            has_theorem = re.search(rf'\b(theorem|lemma)\s+{lean_name}\b', response)
            if has_theorem:
                helper_to_rename = helpers[0]
                print(f"  [Auto-Heal] Renaming helper '{helper_to_rename}' to target '{lean_name}' and removing theorem.")
                response = re.sub(rf'\bdef\s+{helper_to_rename}\b', f'def {lean_name}', response)
                response = re.sub(rf'\b(theorem|lemma)\s+{lean_name}\b.*', '', response, flags=re.DOTALL).strip()
                
        elif not re.search(r'\bdef\b', response) and re.search(rf'\b(theorem|lemma)\s+{lean_name}\b', response):
            print(f"  [Auto-Heal] Changing theorem '{lean_name}' to def.")
            response = re.sub(rf'\b(theorem|lemma)\s+{lean_name}\b', f'def {lean_name}', response)
    
    # Log Lean code
    if response:
        log_to_file("lean_code", response, entity_id=entity_id, attempt=attempt)
        
    print(f"  [lean-export] Сгенерированный код Lean:\n{response}\n")

    # Forbid 'noncomputable' in generated Lean code per policy
    if 'noncomputable' in response.lower():
        print(f"  [lean-export] REJECTING: 'noncomputable' used in generated code (forbidden).")
        return ""

    if '\\' in response and ('\\mathcal' in response or '\\in' in response or '\\mForall' in response):
        print(f"  [lean-export] LLM output still contains LaTeX. Rejecting.")
        return ""

    return response.strip()


# ── Regex Fallback Translation ───────────────────────────────────────────────

def translate_to_lean_regex(entity_id, entity_type, tex_content):
    """Legacy regex-based translation. Used as fallback when LLM fails."""
    formulas = re.findall(r'\\\[(.*?)\\\]', tex_content, re.DOTALL)
    if not formulas:
        return ""

    math = " ".join(formulas)
    lean_name = entity_id.replace('-', '_')

    replacements = [
        # Quantifiers (Parameterized)
        (r'\\mForall\{([^}]+)\}', r'∀ \1, '),
        (r'\\mExists\{([^}]+)\}', r'∃ \1, '),
        
        # Mappings
        (r'\\mMap\{([^}]+)\}\{([^}]+)\}\{([^}]+)\}', r'\1 : \2 → \3'),

        # Quantifiers (Standalone)
        (r'\\mForall', '∀'), (r'\\forall', '∀'),
        (r'\\mExists', '∃'), (r'\\exists', '∃'),

        # Logic Connectives
        (r'\\mImplies', '→'), (r'\\Rightarrow', '→'), (r'\\implies', '→'),
        (r'\\mIff', '↔'), (r'\\Leftrightarrow', '↔'), (r'\\iff', '↔'),
        (r'\\mDefIff', ':='), (r'\\mDefinedAs', ':='),
        (r'\\mAnd', '∧'), (r'\\land', '∧'),
        (r'\\mOr', '∨'), (r'\\lor', '∨'),
        (r'\\mNot', '¬'), (r'\\lnot', '¬'),
        (r'\\mTurnstile', '⊢'), (r'\\vdash', '⊢'),

        # Sets
        (r'\\mIn', '∈'), (r'\\in', '∈'),
        (r'\\mSubseteq', '⊆'), (r'\\subseteq', '⊆'),
        (r'\\mSubset', '⊆'), (r'\\subset', '⊆'),
        (r'\\mEmpty', '∅'), (r'\\varnothing', '∅'), (r'\\emptyset', '∅'),

        # Number Sets
        (r'\\mReal', 'ℝ'), (r'\\mathbb\{R\}', 'ℝ'),
        (r'\\mNat', 'ℕ'), (r'\\mathbb\{N\}', 'ℕ'),
        (r'\\mInt', 'ℤ'), (r'\\mathbb\{Z\}', 'ℤ'),
        (r'\\mComplex', 'ℂ'), (r'\\mathbb\{C\}', 'ℂ'),

        # Formatting / Structural
        (r'\\entityref\{[^}]+\}\{(.*?)\}', r'\1'),
        (r'\\quad', ' '), (r'\\;', ' '),
        (r'\\text\{([^}]+)\}', r'\1'),
        (r'\\left', ''), (r'\\right', ''),
        (r'\\colon', ':'),
        (r'\\mTo', '→'), (r'\\to', '→'),

        # Relational / Variables
        (r'\\neq', '≠'),
        (r'\\leq', '≤'), (r'\\le', '≤'),
        (r'\\geq', '≥'), (r'\\ge', '≥'),
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
    if entity_type == "def":
        return f"def {lean_name} : {lean_math} := sorry"
    elif entity_type == "prop":
        return f"theorem {lean_name} : {lean_math} := by sorry"

    return f"-- Unrecognized type: {lean_name}"


# ── Generation with Repair Loop ──────────────────────────────────────────────

def attempt_generation_with_repair(eid, entity_type, tex_content, model="goedel:latest", max_attempts=7):
    """
    Loop: Generate -> Validate -> Analyze errors -> Regenerate.
    Returns: (lean_code, is_valid)
    """
    lean_code = ""
    error_feedback = None

    for attempt in range(1, max_attempts + 1):
        lean_code = translate_to_lean_via_llm(
            eid, entity_type, tex_content, 
            model=model,
            error_feedback=error_feedback, 
            previous_code=lean_code,
            attempt=attempt
        )
        
        if not lean_code:
            return None, False

        validation_result = validate_entity(eid, lean_code)
        
        if validation_result["status"] == "success":
            print(f"  [✓] {eid} успешно валидирован (Попытка {attempt})")
            return lean_code, True
            
        elif validation_result["status"] == "failed":
            errors = validation_result.get("errors", [])
            error_feedback = "\n".join([f"Line {e['line']}: {e['message']}" for e in errors])
            print(f"  [!] {eid} ошибка (Попытка {attempt}/{max_attempts}). Отправляем фидбек модели...")
            log_to_file("lean_errors", error_feedback, entity_id=eid, attempt=attempt)
            
    return lean_code, False


# ── Main Export Pipeline ─────────────────────────────────────────────────────

def main():
    import argparse
    parser = argparse.ArgumentParser(description="Export Mathesis graph to Lean 4")
    parser.add_argument("--model", type=str, default=None, help="LLM model name")
    parser.add_argument("--api-key", type=str, default=None, help="API Key for cloud providers")
    parser.add_argument("--force", action="store_true", help="Re-translate all entities")
    parser.add_argument("--provider", type=str, default="ollama", choices=["ollama", "gemini", "openai", "groq"],
                        help="Main LLM provider")
    parser.add_argument("--lean-provider", type=str, default=None, choices=["ollama", "gemini", "openai", "groq"],
                        help="Optional separate provider for Lean generation")
    parser.add_argument("--lean-api-key", type=str, default=None, help="API Key for Lean provider")
    parser.add_argument("--lean-model", type=str, default=None, help="Model for Lean provider")
    args = parser.parse_args()

    # Default models per provider
    if not args.model:
        if args.provider == "gemini": args.model = "gemini-2.5-flash"
        elif args.provider == "openai": args.model = "gpt-4o-mini"
        elif args.provider == "groq": args.model = "llama-3.3-70b-versatile"
        else: args.model = "qwen3:8b"
    
    if args.lean_provider and not args.lean_model:
        if args.lean_provider == "gemini": args.lean_model = "gemini-2.5-flash"
        elif args.lean_provider == "openai": args.lean_model = "gpt-4o-mini"
        elif args.lean_provider == "groq": args.lean_model = "llama-3.3-70b-versatile"
        else: args.lean_model = "qwen3:8b"

    # Initialize LLM providers
    setup_provider(args.provider, api_key=args.api_key, model=args.model)
    if args.lean_provider:
        setup_lean_provider(args.lean_provider, api_key=args.lean_api_key, model=args.lean_model)



    print("=== Exporting Mathesis graph to Lean 4 ===")

    nodes, edges = get_graph_from_files()
    sorted_ids = topological_sort(nodes, edges)

    if not sorted_ids:
        print("No entities found.")
        return

    VALIDATED_DIR.mkdir(parents=True, exist_ok=True)
    LEAN_DIR.mkdir(parents=True, exist_ok=True)

    # Initialize file for successful entities
    with open(SUCCESS_FILE, 'w', encoding='utf-8') as f:
        f.write("import Mathlib\n\n-- Valid entities generated by Goedel-Formalizer\n\n")

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
            
            # Since it's cached, optionally we can add it to SUCCESS_FILE if we assume it's valid,
            # but we won't double-append to prevent duplicates unless we do a fresh run.
            continue

        try:
            content = node["path"].read_text(encoding='utf-8')
        except Exception as e:
            print(f"  [SKIP] {eid}: {e}")
            stats["failed"] += 1
            continue

        # Strip proof blocks for translation
        content_no_proofs = re.sub(r'\\begin\{proof\}.*?\\end\{proof\}', '', content, flags=re.DOTALL)

        # Use new self-correction loop
        lean_code, is_valid = attempt_generation_with_repair(eid, node["type"], content_no_proofs, model=args.model)

        if lean_code and is_valid:
            print(f"  [LLM] {eid} → OK ({len(lean_code)} chars)")
            stats["llm_ok"] += 1
            validated_file.write_text(lean_code, encoding='utf-8')
            lean_fragments.append((eid, lean_code))
            
            with open(SUCCESS_FILE, 'a', encoding='utf-8') as sf:
                sf.write(f"-- Entity: {eid} | Type: {node['type']}\n")
                sf.write(f"{lean_code}\n\n")
        else:
            # Fallback (Regex) with additional validation
            lean_code_regex = translate_to_lean_regex(eid, node["type"], content_no_proofs)
            if lean_code_regex:
                regex_val = validate_entity(eid, lean_code_regex)
                if regex_val["status"] == "success":
                    print(f"  [REGEX] {eid} → fallback валиден")
                    stats["regex_ok"] += 1
                    validated_file.write_text(lean_code_regex, encoding='utf-8')
                    lean_fragments.append((eid, lean_code_regex))
                    
                    with open(SUCCESS_FILE, 'a', encoding='utf-8') as sf:
                        sf.write(f"-- Entity: {eid} (Regex Fallback)\n{lean_code_regex}\n\n")
                else:
                    print(f"  [REGEX] {eid} → fallback также не прошел валидацию")
                    stats["failed"] += 1
            else:
                print(f"  [SKIP] {eid} → no translatable content")
                stats["failed"] += 1

    # Assemble MathesisGraph.lean
    with open(OUT_FILE, 'w', encoding='utf-8') as f:
        f.write("import Mathlib\n\n")
        f.write("-- Auto-generated by pipeline/export_to_lean.py\n")
        f.write(f"-- Entities: {len(lean_fragments)}\n\n")

        for eid, code in lean_fragments:
            f.write(f"-- {eid}\n")
            f.write(f"{code}\n\n")

    print(f"\n=== Export complete ===")
    print(f"  LLM translations (OK): {stats['llm_ok']}")
    print(f"  Regex fallbacks (OK):  {stats['regex_ok']}")
    print(f"  Cached:                {stats['cached']}")
    print(f"  Failed/skipped:        {stats['failed']}")
    print(f"  Successful entities:   {SUCCESS_FILE}")
    print(f"  Output Graph:          {OUT_FILE}")


if __name__ == "__main__":
    main()
