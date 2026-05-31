import sqlite3
import json
import re
import argparse
import sys
import time
from pathlib import Path

# Fix Windows console encoding. reconfigure на месте (не подменяем объект, чтобы
# не закрывать чужой буфер — важно под pytest-capture, где reconfigure отсутствует).
if sys.platform == 'win32':
    for _stream in (sys.stdout, sys.stderr):
        try:
            _stream.reconfigure(encoding='utf-8', errors='replace')
        except (AttributeError, ValueError):
            pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.config import PROVIDERS, get_db_path, resolve_module_config  # noqa: E402
from pipeline.model_manager import ModelManager  # noqa: E402
from mathesis import repo  # noqa: E402
from mathesis.models import Entity, Source  # noqa: E402

DB_PATH = get_db_path()
CONTENT_DIR = PROJECT_ROOT / "content"


def _detect_lean_decl(lean_code: str) -> str:
    """Грубо определяет форму Lean-декларации по первому ключевому слову."""
    for kw in ("theorem", "lemma", "def", "abbrev", "structure", "class", "instance", "axiom"):
        if re.search(rf'(^|\n)\s*(noncomputable\s+)?{kw}\b', lean_code):
            return kw
    return ""


def promote_cluster(conn, *, cluster_id, entity_id, entity_type, title, nl_desc,
                    tex_path, lean_path="", lean_code="", latex="",
                    sources=None, page_refs=None, deps=None, embed_blob=None):
    """Идемпотентно промоутит кластер черновиков в каноническую сущность.

    Пишет через типизированный mathesis.repo (синхронизирует FTS/алиасы/таймстемпы),
    поэтому синтезированные сущности сразу видны поиску. Повторный вызов с теми же
    данными приводит к тому же состоянию (upsert + перезапись источников/pending).
    Сырые (неразрешённые) зависимости складываются в pending_edges.
    """
    sources = sources or []
    page_refs = page_refs or []
    deps = deps or []

    if lean_code:
        lean_status = "sorry" if "sorry" in lean_code else "valid"
        lean_decl = _detect_lean_decl(lean_code)
    else:
        lean_status, lean_decl = "unvalidated", ""

    entity = Entity(
        id=entity_id, kind=entity_type, title=title, nl_desc=nl_desc,
        latex=latex, lean_code=lean_code or "", lean_decl=lean_decl,
        lean_status=lean_status, tex_path=tex_path, lean_path=lean_path or "",
    )
    repo.upsert_entity(conn, entity, commit=False)
    if embed_blob:
        repo.set_embedding(conn, entity_id, embed_blob, commit=False)

    # Провенанс: перезаписываем, чтобы повторный прогон не плодил дубликаты.
    conn.execute("DELETE FROM formulation_sources WHERE entity_id = ?", (entity_id,))
    seen = set()
    for src, pref in zip(sources, page_refs + [0] * (len(sources) - len(page_refs))):
        page = f"page {pref}" if pref else ""
        if (src, page) in seen:
            continue
        seen.add((src, page))
        repo.add_source(conn, Source(entity_id=entity_id, source_book=src, page_info=page), commit=False)

    conn.execute("INSERT OR REPLACE INTO cluster_entity_map (cluster_id, entity_id) VALUES (?, ?)",
                 (cluster_id, entity_id))

    # Сырые зависимости -> pending_edges (перезапись для идемпотентности).
    conn.execute("DELETE FROM pending_edges WHERE source_id = ?", (entity_id,))
    clean_deps = sorted({d.strip() for d in deps if isinstance(d, str) and d.strip()})
    for dep in clean_deps:
        conn.execute("INSERT INTO pending_edges (source_id, raw_dep, status) VALUES (?, ?, 'pending')",
                     (entity_id, dep))
    return entity_id



def detect_entity_type_from_text(raw_texts, has_proof=False):
    """Определяет тип сущности (def|prop). Делегирует в data-driven реестр
    pipeline.registries.entity_types (ключевые слова — данные, расширяемо)."""
    from pipeline.registries.entity_types import detect_entity_type
    return detect_entity_type(raw_texts, has_proof=has_proof)

def prepare_macros_from_deps(deps, mgr):

    if not deps:
        deps = []

    unique_deps = list({d.strip() for d in deps if d and isinstance(d, str)})

    from pipeline.enrichment_coordinator import resolve_entities
    from pipeline.latex_utils import get_macro_metadata
    import re
    import json
    import sqlite3

    meta = get_macro_metadata()
    macros_map = {eid: data['macro'] for eid, data in meta.items()}

    macro_file = PROJECT_ROOT / "content" / "mathesis_macros.sty"

    available_macros = []
    resolved_eids = []

    # ALWAYS ADD ALL EXISTING MACROS to available_macros, formatted with notation
    for eid, data in meta.items():
        macro_name = data['macro']
        notation = data['notation']
        if notation:
            available_macros.append(f"{macro_name} : Use instead of standard notation \"{notation}\"")
        else:
            available_macros.append(f"{macro_name} : Use for the concept of '{eid}'")

    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    cursor = conn.cursor()

    for dep in unique_deps:
        resolved, _ = resolve_entities("", dep, [])
        if resolved:
            eid = resolved[0]["entity_id"]
            resolved_eids.append(eid)
            # If it was already added from meta, we don't need to add it again
            # But let's check if it's missing from meta (e.g. recent stub)
            if eid not in meta:
                pascal_name = "".join(w.title() for w in re.sub(r'[^\w\s]', '', dep).strip().split())
                if not pascal_name: continue
                new_macro = f"\\{pascal_name}"
                macro_entry = f"{new_macro} : Use instead of standard notation \"{pascal_name}\""
                if macro_entry not in available_macros:
                    available_macros.append(macro_entry)
                    macros_map[eid] = new_macro
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

            # Quick arity check via LLM (промпт вынесен в pipeline/prompts/templates).
            from pipeline.prompts import load_prompt
            prompt = load_prompt("macro_notation", dep=dep)
            try:
                resp = mgr.query_llm(prompt, json_mode=True, role="extract")
                match = re.search(r'(\{.*\})', resp, re.DOTALL)
                if match: resp = match.group(1)
                data = json.loads(resp)
                args = data.get("args", 0)
                notation = data.get("notation", pascal_name)
            except Exception:
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

            macro_entry = f"{new_macro} : Use instead of standard notation \"{notation}\""
            if macro_entry not in available_macros:
                available_macros.append(macro_entry)
            resolved_eids.append(new_eid)

    conn.close()

    if not available_macros:
        return "", resolved_eids

    # Deduplicate while preserving order
    seen = set()
    deduped_macros = []
    for m in available_macros:
        if m not in seen:
            seen.add(m)
            deduped_macros.append(f"- {m}")

    header = "\nAVAILABLE MACROS (CRITICAL: You MUST use these instead of standard LaTeX for concepts/types. Example: use \\RealNumbers instead of \\mathbb{R}):\n"
    return header + "\n".join(deduped_macros) + "\n", resolved_eids

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

OUTPUT: Only LaTeX. No ```latex blocks. Include the following metadata at the top:
% entity-id: <prefix-short-id>
% entity-type: <def|prop>
% macro: \<PascalCaseNameOfEntity>
% args: <number-of-arguments>
% notation: <LaTeX-notation-if-any-using-#1-for-arguments>"""

    if target_requirement:
        rules += target_requirement

    rules += r"""

CRITICAL HEURISTICS & ANTI-PATTERNS TO AVOID:
1. Types vs. Sets (The \colon vs \in rule):
   Never confuse belonging to a fundamental type with belonging to a subset.
   - BAD: "x \TermIn \RealNumbers" when declaring a variable.
   - GOOD: "x \colon \RealNumbers" (in LaTeX) or "(x : ℝ)" (in Lean). Use "\TermIn" ONLY for subsets, e.g., "x \TermIn \ClosedInterval{a, b}".

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

CRITICAL WRAPPING RULE: ALL mathematical entities/concepts/operators in your formulas MUST be written using dynamic semantic macros (e.g. \RealNumbers, \Continuous, \AbsAbstract). DO NOT use hardcoded LaTeX like \mathbb{R}, \sup, \in, \forall if a macro exists in your AVAILABLE MACROS list!
NOTE: Local variables (like a, b, f, x) introduced in the current formula MUST NOT be wrapped in semantic macros UNLESS they are arguments to an operation, function, or paired delimiter macro (like absolute value, norm, inner product, etc.). For any macro that represents paired symbols or operations, you MUST pass the entire expression as its argument (e.g., \RealAbsoluteValue{x - y} or \Norm{x}), do NOT wrap just the operator name like \Norm{\mathrm{norm}}(x).

TYPING: Every formula MUST start with variable declarations via quantors:
\TerForall f \colon \RealNumbers \TermTo \RealNumbers

PURE MATH RULE: For \begin{definition} and \begin{proposition} blocks, NO NATURAL LANGUAGE IS ALLOWED AT ALL. NO English, NO Russian, NO plain text, NO "Note", NO "Remark", NO explanations. The content MUST be 100% formal math symbols and macros. ALL formulas MUST be wrapped in display math blocks \[ ... \]. Inline math $...$ is FORBIDDEN.
For long formulas, you MUST use \begin{aligned} ... \end{aligned} inside \[ ... \] and break lines at major relations (=, \implies) or operators using \\ so they do not overflow the page margins.

Natural language and explanatory notes are ONLY permitted inside \begin{proof} blocks. ALL math objects/variables/operators in proofs MUST be wrapped in inline math mode `$ ... $`. For example, write $\ClosedInterval{a, b}$ and $f(x)$ instead of \ClosedInterval{a, b} and f(x). Leaving mathematical text/variables naked without `$` is STRICTLY FORBIDDEN!
CRITICAL INLINE MATH RULE: Every opening `$` MUST have a corresponding closing `$`. Do not forget the closing symbol (выходной символ) or the rest of the text will disappear and the compiler will crash!"""

    if relevant_macros_str:
        rules += relevant_macros_str

    if implicit_assumptions:
        rules += f"\nIMPLICIT ASSUMPTIONS DETECTED IN TEXTBOOK (Apply these to your variable declarations!):\n{implicit_assumptions}\n"

    if entity_type == "prop":
        prompt = rf"""Synthesize a strict formal THEOREM + PROOFS from these sources:
{text_input}

{rules}
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
    """Checks if definition or proposition blocks contain natural language."""
    errors = []
    envs = ['definition', 'proposition', 'theorem', 'lemma', 'property', 'axiom', 'object', 'operation']
    for env in envs:
        pattern = rf'\\begin\{{{env}\}}(?:\[.*?\])?(.*?)\\end\{{{env}\}}'
        for match in re.finditer(pattern, latex, re.DOTALL):
            block_content = match.group(1)
            # 1. Search for \text{...}
            if re.search(r'\\text\s*\{', block_content):
                errors.append(f"ОШИБКА: Обнаружено использование \\text{{...}} внутри \\begin{{{env}}}. Использование естественного языка в формулировках строго запрещено по правилу Pure Math Absolute Rule.")

            # 2. Clean content to find raw natural language words
            # Remove \begin{...} and \end{...}
            clean_content = re.sub(r'\\(begin|end)\{[a-zA-Z*]+\}', ' ', block_content)
            # Remove \mathrm{...} wrappers so we don't treat predicate names as words
            clean_content = re.sub(r'\\mathrm\{[a-zA-Z0-9_]+\}', ' ', clean_content)
            # Remove other LaTeX commands: \abc
            clean_content = re.sub(r'\\[a-zA-Z]+', ' ', clean_content)
            # Remove comments
            clean_content = re.sub(r'%.*$', ' ', clean_content, flags=re.MULTILINE)

            # Find words (both Latin and Cyrillic)
            words = re.findall(r'[a-zA-Zа-яА-ЯёЁ]{2,}', clean_content)
            bad_words = [w for w in words if w.lower() not in ('dt', 'dx', 'dy', 'dz', 'dp', 'dq', 'ru', 'en')]
            if bad_words:
                errors.append(f"ОШИБКА: Обнаружен текст на естественном языке {bad_words} внутри \\begin{{{env}}}. Разрешены исключительно математические символы.")
    return errors

def validate_macros_exist(latex: str) -> list:
    """Checks if all macros used in LaTeX content exist in mathesis_macros.sty or mathesis.sty or are standard LaTeX."""
    errors = []

    # 1. Get custom macros defined in the project
    from pipeline.latex_utils import get_macro_to_id_mapping
    try:
        custom_macros = set(get_macro_to_id_mapping().keys())
    except Exception as e:
        print(f"[synthesizer] [WARN] Could not load custom macros mapping: {e}", flush=True)
        custom_macros = set()

    # 2. Standard allowed LaTeX macros (plus common packages macros loaded by mathesis.sty)
    standard_macros = {
        # Environments and structural
        "begin", "end", "entityref", "label", "ref", "eqref", "cite", "url", "href", "color", "textcolor",
        # Layout & Spacing & Alignment
        "quad", "qquad", "left", "right", "middle", "newline", "linebreak", "dots", "cdots", "vdots", "ddots", "frac", "sqrt", "cfrac", "aligned", "split", "array", "matrix", "pmatrix", "bmatrix",
        # Math operators & functions
        "lim", "limit", "sin", "cos", "tan", "cot", "arcsin", "arccos", "arctan", "sinh", "cosh", "tanh", "log", "ln", "exp", "min", "max", "sup", "inf", "det", "dim", "ker", "deg", "arg", "gcd", "hom",
        # Logic & Connectives
        "forall", "exists", "neg", "lor", "land", "implies", "impliedby", "iff", "to", "gets", "leftrightarrow", "Leftrightarrow", "Rightarrow", "Leftarrow",
        # Set theory & Relations
        "in", "notin", "ni", "subset", "subseteq", "supset", "supseteq", "cap", "cup", "setminus", "emptyset", "mid", "colon", "coloneqq", "eqalign", "times",
        # Math accents & styles
        "mathrm", "mathit", "mathbf", "mathsf", "mathtt", "mathcal", "mathbb", "mathfrak", "bar", "tilde", "hat", "vec", "overline", "underline", "prime", "cdot",
        # Greek letters (lowercase)
        "alpha", "beta", "gamma", "delta", "epsilon", "varepsilon", "zeta", "eta", "theta", "iota", "kappa", "lambda", "mu", "nu", "xi", "pi", "rho", "sigma", "tau", "upsilon", "phi", "chi", "psi", "omega",
        # Greek letters (uppercase)
        "Gamma", "Delta", "Theta", "Lambda", "Xi", "Pi", "Sigma", "Upsilon", "Phi", "Psi", "Omega",
        # Big operators
        "sum", "prod", "coprod", "int", "iint", "iiint", "oint", "bigcap", "bigcup", "bigsqcup",
        # Symbols & delimiters
        "infty", "partial", "nabla", "le", "ge", "leq", "geq", "neq", "approx", "sim", "cong", "equiv", "div", "pm", "mp", "ast", "star", "dagger", "ddagger", "langle", "rangle", "lvert", "rvert", "lVert", "rVert", "lbrace", "rbrace", "lbrack", "rbrack", "vert", "Vert", "backslash", "text", "Colon"
    }

    # 3. Add the macro being defined in this file's header (so it doesn't raise an error on itself)
    macro_match = re.search(r'^%\s*macro:\s*\\([a-zA-Z0-9]+)', latex, re.MULTILINE)
    if macro_match:
        standard_macros.add(macro_match.group(1))

    macro_match_any = re.search(r'%\s*macro:\s*\\([a-zA-Z0-9]+)', latex)
    if macro_match_any:
        standard_macros.add(macro_match_any.group(1))

    # 4. Find all macros in the text (word characters after a backslash)
    used_macros = set(re.findall(r'\\([a-zA-Z0-9]+)', latex))

    # 5. Check each used macro
    all_allowed = custom_macros.union(standard_macros)
    invalid_macros = sorted(list(used_macros - all_allowed))

    for m in invalid_macros:
        errors.append(f"ОШИБКА: Использован несуществующий или незарегистрированный макрос \\{m}. Проверьте его написание или зарегистрируйте его. Доступные семантические макросы: {sorted(list(custom_macros))[:10]}... и т.д.")

    return errors

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
    from pipeline.retry_utils import backoff_delay, RepeatedErrorDetector
    active_provider_name = "ModelManager (synth)"
    # Детектор «застревания»: одинаковый фидбек об ошибке подряд → прекращаем цикл.
    err_detector = RepeatedErrorDetector(max_repeats=2)

    while current_attempt <= max_attempts:
        print(f"\n[synthesizer] --- Attempt {current_attempt}/{max_attempts} ---", flush=True)

        # 1. Regenerate LaTeX if missing or if semantic error occurred
        if not latex_content or semantic_error_feedback:
            mgr = ModelManager.get_instance()
            relevant_macros_str, resolved_eids = prepare_macros_from_deps(deps, mgr)
            prompt = build_synthesis_prompt(cluster_id, formulations, sources, entity_type, implicit_assumptions, canonical_term, relevant_macros_str)
            current_prompt = prompt

            if semantic_error_feedback:
                print("[synthesizer] Injecting semantic/type error feedback into LaTeX prompt...", flush=True)
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

                delay = backoff_delay(inner_attempt, base=2.0)
                print(f"[synthesizer] [WARN] LLM returned empty/short response. Inner retry {inner_attempt}/3 in {delay:.0f}s...")
                time.sleep(delay)

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
            # Check if all used macros exist in current packages/files
            nonexistent_macro_warnings = validate_macros_exist(latex_content)

            all_warnings = nl_warnings + macro_warnings + nonexistent_macro_warnings
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
        skip_entity = False
        if processed_entities and temp_eid in processed_entities:
            skip_entity = True
        elif processed_entities:
            # Semantic deduplication
            from pipeline.enrichment_coordinator import normalize_math_term
            temp_title = temp_eid.replace('def-', '').replace('thm-', '').replace('axm-', '').replace('prop-', '').replace('-', ' ')
            norm_temp = normalize_math_term(temp_title)

            for pid in processed_entities:
                p_title = pid.replace('def-', '').replace('thm-', '').replace('axm-', '').replace('prop-', '').replace('-', ' ')
                norm_p = normalize_math_term(p_title)

                temp_words = set(norm_temp.split())
                p_words = set(norm_p.split())

                if norm_temp == norm_p or (len(p_words) >= 2 and p_words.issubset(temp_words)) or (len(temp_words) >= 2 and temp_words.issubset(p_words)):
                    print(f"  [synthesizer] [SEMAN-SKIP] Entity '{temp_eid}' semantically matches '{pid}'. Forcing ID to '{pid}'.")
                    temp_eid = pid
                    latex_content = re.sub(r'(% entity-id:\s*).+$', rf'\g<1>{pid}', latex_content, flags=re.MULTILINE)
                    skip_entity = True
                    break

        if skip_entity:
            print(f"  [synthesizer] [SKIP] Entity '{temp_eid}' already synthesized. Skipping Lean formalization.")
            valid_lean_code = ""
            break

        # Mathlib discovery
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
            except Exception:
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
            delay = backoff_delay(inner_attempt, base=2.0)
            print(f"  [synthesizer] [WARN] Lean translation returned empty. Inner retry {inner_attempt}/3 in {delay:.0f}s...")
            time.sleep(delay)

        if not lean_code_new and not lean_code:
            lean_code_new = translate_to_lean_regex(temp_eid, temp_etype, latex_content)

        lean_code = lean_code_new or lean_code

        if skip_validation:
            print("  [SKIP] Skipping Lean validation loop (--no-validate passed).")
            valid_lean_code = lean_code
            break

        if lean_code:
            print(f"  Lean validating: {lean_code[:80]}...")
            result = validate_entity(temp_eid, lean_code, deps=resolved_eids if 'resolved_eids' in locals() else [])
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
            print("  [FAIL] Lean validation failed or model cheated.")

            messages = []
            for e in result["errors"][:3]:
                msg = e.get("message", "")
                if "don't know how to synthesize placeholder" in msg:
                    type_match = re.search(r'of type\n\s*(.+)', msg)
                    if type_match:
                        msg = f"ОШИБКА ПЛЕЙСХОЛДЕРА (`_`): ожидается точный тип `{type_match.group(1).strip()}`."

                elif "unknown identifier" in msg:
                    ident_match = re.search(r"unknown identifier '([^']+)'", msg)
                    if ident_match:
                        ident = ident_match.group(1)
                        feedback = f"\nСИНТЕЗАТОРУ: Lean не распознал идентификатор '{ident}'. Это означает, что вы либо не объявили переменную '{ident}' с помощью кванторов (\\TerForall, \\TermExists), либо использовали сырой несемантический LaTeX макрос (например, \\{ident}). Пожалуйста, исправьте исходный LaTeX!"
                        if ident == "in":
                            feedback += "\nВНИМАНИЕ: Для объявления фундаментальных типов используйте \\colon (например, x \\colon \\RealNumbers), а для принадлежности к подмножеству — \\TermIn."
                        msg += feedback

                elif "expected " in msg:
                    msg += "\nСИНТЕЗАТОРУ: Синтаксическая ошибка. Возможно, вы использовали голый LaTeX-макрос, который разрушил парсер Lean. Используйте только разрешенные семантические макросы."

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
                print("  [!] Syntax/Translation error detected. Routing back to Lean formalizer.")
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

            # Если один и тот же фидбек об ошибке повторяется — модель «застряла»,
            # прекращаем цикл досрочно, не дожидаясь max_attempts.
            repeat_sig = (semantic_error_feedback or "") + "||" + (syntax_error_feedback or "")
            if err_detector.record(repeat_sig):
                print(f"  [synthesizer] [ABORT] Одинаковая ошибка повторяется для {temp_eid} — прекращаю попытки.")
                break

            current_attempt += 1

    return latex_content, valid_lean_code, semantic_map

def rebuild_master_tex():
    master_path = CONTENT_DIR / "master.tex"
    print(f"\n[master-rebuild] Rebuilding {master_path.relative_to(PROJECT_ROOT)} from current content directory...", flush=True)

    # 1. Discover all tex files
    file_by_id = {}
    all_ids = []
    for filepath in CONTENT_DIR.rglob("*.tex"):
        if filepath.name in ("master.tex", "TEMPLATE.tex", "mathesis.sty"):
            continue
        try:
            with open(filepath, "r", encoding="utf-8") as f:
                text = f.read()
            id_match = re.search(r'% entity-id:\s*(.*)', text)
            if not id_match:
                continue
            entity_id = id_match.group(1).strip()
            file_by_id[entity_id] = filepath
            all_ids.append(entity_id)
        except Exception as e:
            print(f"  [WARN] Failed to parse {filepath.name}: {e}", flush=True)

    # 2. Topological Sort using LeanTreeBuilder (single source of truth for ordering)
    import sys
    if str(PROJECT_ROOT) not in sys.path:
        sys.path.insert(0, str(PROJECT_ROOT))
    from tools.lean_tree_builder import LeanTreeBuilder
    builder = LeanTreeBuilder()

    order = builder.build_closure_order(all_ids)

    # 3. Generate master.tex content
    input_lines = []
    for entity_id in order:
        if entity_id in file_by_id:
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

    # Прогреваем Lean REPL в фоне ПАРАЛЛЕЛЬНО синтезу: загрузка Mathlib в ОЗУ
    # перекрывается с LLM-вызовами, поэтому к моменту самокоррекции Lean REPL уже
    # тёплый и таймаут проверки не тратится на инициализацию.
    if not args.no_validate:
        try:
            from pipeline.lean_validator import prewarm_repl_async
            prewarm_repl_async()
        except Exception:
            pass

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

        rel_tex = str(file_path.relative_to(PROJECT_ROOT))
        rel_lean = str(lean_file_path.relative_to(PROJECT_ROOT)) if valid_lean_code else ""
        unique_deps = list({d.strip() for d in data.get('deps', []) if d and isinstance(d, str)})

        # Идемпотентный промоушен черновика в каноническую сущность (через типизированный repo).
        promote_cluster(
            conn,
            cluster_id=cid, entity_id=entity_id, entity_type=entity_type,
            title=title, nl_desc=nl_desc, tex_path=rel_tex, lean_path=rel_lean,
            lean_code=valid_lean_code or "",
            sources=data['sources'], page_refs=data['page_refs'],
            deps=unique_deps, embed_blob=embed_blob,
        )
        print(f"[synthesizer] [OK] DB updated: entities({entity_id})")
        import json as _json
        print(f"[synthesizer] ParsedDeps: {_json.dumps({'entity_id': entity_id, 'deps': unique_deps}, ensure_ascii=False)}", flush=True)

        # Clean up cache (черновик промоутнут)
        cursor.execute("DELETE FROM formulation_raw_cache WHERE temp_cluster_id = ?", (cid,))

    conn.commit()
    conn.close()

    print("Canonical synthesis complete.")

if __name__ == "__main__":
    main()
