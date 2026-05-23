import os
import re
from pathlib import Path
import subprocess
import shutil
import sys
import io
import json

# Fix Windows console encoding
if sys.platform == 'win32' and getattr(sys.stdout, 'encoding', '').lower() != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(PROJECT_ROOT))
CONTENT_DIR = PROJECT_ROOT / "content"
CACHE_PATH = PROJECT_ROOT / "output" / "nl_translations_cache.json"

def load_book_citations():
    citations = {
        "zorich": "Зорич В.А., Математический анализ, Том I",
        "apostol": "Apostol T.M., Mathematical Analysis",
        "spivak": "Spivak M., Calculus",
    }
    books_dir = PROJECT_ROOT / "Books"
    if not books_dir.exists():
        return citations

    try:
        for f in books_dir.iterdir():
            if f.is_file() and f.suffix.lower() == ".pdf":
                name = f.stem
                parts = name.split(" - ")
                if len(parts) >= 2:
                    author = parts[0].strip()
                    title = parts[1].strip()
                    citation_str = f"{author}, {title}"
                    
                    # Derive key: e.g. "Apostol, T.M." -> "apostol"
                    key_base = author.split(',')[0].strip().split()[0].lower()
                    if "zorich" in key_base:
                        citations[key_base] = "Зорич В.А., Математический анализ, Том I"
                    else:
                        citations[key_base] = citation_str
                    
                    # Also map full stem to support precise matches
                    citations[name.lower()] = citation_str
    except Exception as e:
        print(f"[Warning] Failed to load citations from Books directory: {e}. Falling back to default list.")
        
    return citations

BOOK_CITATIONS = load_book_citations()

NL_DESCRIPTIONS = {
    "op-riemann-integral": r"Определенным интегралом Римана от функции $f(x)$ на отрезке $[a,b]$ называется предел интегральных сумм $\sum f(\xi_i) \Delta x_i$ при стремлении максимальной длины частичного отрезка $\lambda(P)$ к нулю, независимо от выбора разбиения $P$ и промежуточных точек $\xi_i$.",
    "op-darboux-integral": r"Функция $f$ называется интегрируемой по Дарбу на отрезке $[a,b]$, если нижний интеграл Дарбу $\underline{I}$ равен верхнему интегралу Дарбу $\overline{I}$. Их общее значение называется интегралом Дарбу функции $f$ по отрезку $[a,b]$.",
    "op-lower-darboux-sum": r"Нижней суммой Дарбу называется сумма произведений инфимумов функции $f$ на каждом отрезке разбиения $[x_{i-1}, x_i]$ на длину этого отрезка $\Delta x_i$.",
    "op-upper-darboux-sum": r"Верхней суммой Дарбу называется сумма произведений супремумов функции $f$ на каждом отрезке разбиения $[x_{i-1}, x_i]$ на длину этого отрезка $\Delta x_i$.",
    "obj-partition": r"Разбиением отрезка $[a,b]$ называется конечное множество точек $P = \{x_0, x_1, \ldots, x_n\}$, таких что $a = x_0 < x_1 < \cdots < x_n = b$.",
    "obj-function": r"Функция $f$ из множества $X$ в множество $Y$ — это правило (или бинарное отношение), по которому каждому элементу $x \in X$ ставится в соответствие ровно один элемент $y \in Y$. Формально, это подмножество декартова произведения $X \times Y$, обладающее свойством однозначности.",
    "obj-real-numbers": r"Множество вещественных чисел $\mathbb{R}$ — это непрерывная числовая прямая. Формально $\mathbb{R}$ задается как полное (непрерывное) архимедово упорядоченное поле. В нем можно складывать, умножать, сравнивать элементы, и в нем нет «дырок» (каждое ограниченное сверху подмножество имеет точную верхнюю грань).",
    "obj-set": r"Множество — базовое, неопределяемое напрямую понятие математики. Множество представляет собой совокупность объектов произвольной природы, называемых его элементами. Все свойства множеств строго выводятся из аксиом системы Цермело-Френкеля (ZFC).",
}

TEMPLATE = r"""\documentclass[12pt,a4paper]{report}
\usepackage[utf8]{inputenc}
\usepackage[russian]{babel}
\usepackage{mathesis}
\usepackage{geometry}
\geometry{left=3cm,right=2cm,top=2cm,bottom=2cm}

\title{\textbf{Справочник математических сущностей}}
\author{Конвейер компиляции Mathesis}
\date{\today}

\begin{document}

\maketitle

\tableofcontents
\newpage

%(content)s

\end{document}
"""

def parse_bilingual_title(title):
    title = title.strip()
    match = re.match(r"^([^(]+)\s*\(([^)]+)\)$", title)
    if match:
        ru_part = match.group(1).strip()
        en_part = match.group(2).strip()
        en_part = re.sub(r"\s*\[[^\]]+\]", "", en_part).strip()
        en_part = en_part.replace('[', '').replace(']', '').strip()
        return ru_part, en_part
    else:
        cleaned = re.sub(r"\s*\[[^\]]+\]", "", title).strip()
        cleaned = cleaned.replace('[', '').replace(']', '').strip()
        return cleaned, None

def is_id_or_placeholder(name):
    if not name:
        return True
    name_lower = name.lower()
    if any(prefix in name_lower for prefix in ["obj-", "op-", "prop-", "thm-", "axm-", "def-", "axm-fol-"]):
        return True
    if name_lower.startswith("название сущности"):
        return True
    return False

def humanize_id(eid):
    parts = eid.split('-', 1)
    if len(parts) > 1:
        return parts[1].replace('-', ' ').title()
    return eid.replace('-', ' ').title()

def synthesize_entity_details(data, provider, model, api_key, force_refresh=False, nl_cache=None):
    
    if nl_cache is None: nl_cache = {}
    if not force_refresh and data["id"] in nl_cache:
        c = nl_cache[data["id"]]
        print(f"  [Synth] Loaded cached translations for {data['id']}")
        return c.get("name_ru", ""), c.get("name_en", ""), c.get("desc_ru", ""), c.get("desc_en", "")

    ru_name, en_name = parse_bilingual_title(data["title"])
    if is_id_or_placeholder(ru_name):
        ru_name = None
    if is_id_or_placeholder(en_name):
        en_name = None

    desc_ru = ""
    if not desc_ru:
        desc_ru = data.get("nl_desc", "").strip()

    if desc_ru:
        desc_ru = re.sub(r"\s*\[[^\]]+\]", "", desc_ru).strip()
        desc_ru = desc_ru.replace('[', '').replace(']', '').strip()

    if not provider:
        try:
            config_path = Path(__file__).resolve().parent.parent / "api_config.json"
            if config_path.exists():
                with open(config_path, "r", encoding="utf-8") as f:
                    cfg = json.load(f)
                    provider = cfg.get("providers", {}).get("synth", "gemini")
                    model = cfg.get("models", {}).get("synth", "gemini-2.5-flash-lite")
                    api_key = cfg.get("api_keys", {}).get(provider, "")
        except Exception as e:
            print(f"[Warning] Failed to load provider settings from api_config.json: {e}")
            provider = "gemini"
            model = "gemini-2.5-flash-lite"
            api_key = ""

    print(f"  [Synth] Synthesizing bilingual details for {data['id']} using {provider} ({model})...")

    try:
        from pipeline.model_manager import ModelManager
        ModelManager.get_instance().setup_role("generate", provider, model, api_key)
    except Exception as e:
        print(f"[Warning] Failed to setup LLM provider: {e}")
        provider = "ollama"

    prompt = f"""You are a world-class mathematician and textbook editor.
We are compiling a high-quality mathematical analysis textbook/handbook.
Your task is to synthesize/translate/clean up the bilingual names and natural language descriptions for the following mathematical entity.

ENTITY DETAILS:
- ID: {data["id"]}
- Type: {data["type"]}
- Parsed RU Name: {ru_name or "Not provided"}
- Parsed EN Name: {en_name or "Not provided"}
- Existing RU Description: {desc_ru or "Not provided"}
- Canonical Math Block (LaTeX):
{data.get("full_body", "")}

INSTRUCTIONS:
1. Names ("name_ru" and "name_en"):
   - Must be the standard, clean mathematical textbook names (e.g., "Частичный порядок" / "Partial Order").
   - If they are already parsed and valid (not empty/placeholder), use them. If only one is valid, translate it to the other language. If none are valid, generate them professionally based on standard mathematical terminology for this entity.
   - Absolutely HIDE/REMOVE any IDs (like `[axm-fol-4]` or `op-riemann-integral`) or internal codes.

2. Descriptions ("desc_ru" and "desc_en"):
   - "desc_ru" must be a clean, beautiful, mathematically rigorous formulation/definition of this entity in Russian, using standard inline LaTeX math mode (e.g., $f(x)$, $[a, b]$). If "Existing RU Description" is provided, clean it up (removing any IDs or brackets). If not provided, generate it from the Canonical Math Block.
   - "desc_en" must be a high-quality, professional mathematical English translation/equivalent of "desc_ru".
   - Do NOT include headers like "Формулировка на русском языке" or "Математическая формулировка" inside the description fields.
   - Make sure absolutely NO internal IDs or reference codes appear in either description.

Return ONLY a valid JSON object with the following schema:
{{
    "name_ru": "...",
    "name_en": "...",
    "desc_ru": "...",
    "desc_en": "..."
}}
"""

    try:
        from pipeline.model_manager import ModelManager
        response = ModelManager.get_instance().query_llm(prompt, json_mode=True, role="generate")
        
        response = re.sub(r'^```json\s*', '', response.strip(), flags=re.MULTILINE)
        response = re.sub(r'^```\s*$', '', response.strip(), flags=re.MULTILINE).strip()
        
        match = re.search(r'(\{.*\})', response, re.DOTALL)
        if match:
            response = match.group(1)
        
        # Fix unescaped backslashes from LaTeX in JSON strings (e.g. \mathbb, \in, \forall).
        # Valid JSON escape chars are: " \\ / b f n r t u. Anything else is invalid.
        try:
            # First attempt: try to parse as-is
            res = json.loads(response)
        except Exception as parse_err:
            # Log the raw problematic response for debugging
            try:
                from pipeline.export_to_lean import log_to_file
                log_to_file("synthesis/json-fail", f"RAW RESPONSE:\n{response}", entity_id=data['id'])
            except Exception:
                pass
            # Second attempt: aggressively escape all backslashes (safe fallback)
            safe_resp = response.replace('\\', '\\\\')
            try:
                res = json.loads(safe_resp)
            except Exception as parse_err2:
                # As a last resort, try to extract a JSON object substring and parse that
                m = re.search(r'(\{.*\})', response, re.DOTALL)
                if m:
                    try:
                        res = json.loads(m.group(1))
                    except Exception:
                        raise parse_err2
                else:
                    raise parse_err2
        
        
        synth_ru_name = res.get("name_ru", "").strip()
        synth_en_name = res.get("name_en", "").strip()
        synth_desc_ru = res.get("desc_ru", "").strip()
        synth_desc_en = res.get("desc_en", "").strip()
        
        if is_id_or_placeholder(synth_ru_name):
            synth_ru_name = ru_name or humanize_id(data["id"])
        if is_id_or_placeholder(synth_en_name):
            synth_en_name = en_name or humanize_id(data["id"])
            
        synth_ru_name = re.sub(r"\s*\[[^\]]+\]", "", synth_ru_name).strip()
        synth_en_name = re.sub(r"\s*\[[^\]]+\]", "", synth_en_name).strip()
        synth_desc_ru = re.sub(r"\s*\[[^\]]+\]", "", synth_desc_ru).strip()
        
        synth_desc_en = re.sub(r"\s*\[[^\]]+\]", "", synth_desc_en).strip()
        
        # Save to cache
        nl_cache[data["id"]] = {
            "id": data["id"],
            "type": data.get("type", "unknown"),
            "name_ru": synth_ru_name,
            "name_en": synth_en_name,
            "desc_ru": synth_desc_ru,
            "desc_en": synth_desc_en
        }
        try:
            with open(CACHE_PATH, "w", encoding="utf-8") as f:
                json.dump(nl_cache, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[Warning] Failed to write to translation cache: {e}")

        
        print(f"  [Synth Success] Name RU: {synth_ru_name} | Name EN: {synth_en_name}")
        return synth_ru_name, synth_en_name, synth_desc_ru, synth_desc_en
        
    except Exception as e:
        print(f"  [Synth Failed] Error: {e}. Using robust fallbacks.")
        final_ru_name = ru_name or humanize_id(data["id"])
        final_en_name = en_name or humanize_id(data["id"])
        final_desc_ru = desc_ru or ""
        final_desc_en = ""
        
        final_ru_name = re.sub(r"\s*\[[^\]]+\]", "", final_ru_name).strip()
        final_en_name = re.sub(r"\s*\[[^\]]+\]", "", final_en_name).strip()
        
        return final_ru_name, final_en_name, final_desc_ru, final_desc_en

def parse_canonical(filepath):
    with open(filepath, "r", encoding="utf-8") as f:
        text = f.read()
    
    source_match = re.search(r'% defined-in: (.*)', text)
    source = source_match.group(1).strip() if source_match else "Unknown"
    
    id_match = re.search(r'% entity-id: (.*)', text)
    entity_id = id_match.group(1).strip() if id_match else "unknown"
    
    type_match = re.search(r'% entity-type: (.*)', text)
    entity_type = type_match.group(1).strip() if type_match else "unknown"

    module_match = re.search(r'% module: (.*)', text)
    module = module_match.group(1).strip() if module_match else ""
    
    section_match = re.search(r'\\section\{(.*?)\}', text)
    title = section_match.group(1).strip() if section_match else entity_id
    
    formulas = re.findall(r'\\\[(.*?)\\\]', text, re.DOTALL)
    
    from pipeline.latex_utils import extract_dependencies
    deps = extract_dependencies(text)
            
    deps = list(set(deps))
    
    # Extract the full body by removing metadata comments and redundant sections/labels
    body_lines = [line for line in text.split('\n') if not line.strip().startswith('%')]
    full_body = '\n'.join(body_lines).strip()
    full_body = re.sub(r'\\section\{.*?\}', '', full_body)
    full_body = re.sub(r'\\label\{entity:.*?\}', '', full_body)
    
    # Extract description before removing it
    nl_desc = ""
    # Match \textbf{Описание:} ... up to \begin{object/axiom/theorem/operation} or \end{document}
    # Use a non-greedy match that also captures \begin{itemize} blocks within the description
    desc_match = re.search(
        r'\\textbf\{Описание:\}\s*(.*?)(?=\\begin\{(?:object|axiom|theorem|operation|property)\}|\\textbf\{(?!Описание)\}|\\section|$)',
        full_body, flags=re.DOTALL
    )
    if desc_match:
        nl_desc = desc_match.group(1).strip()

    # Strip the Описание block from canonical output as it violates PURE MATH RULE
    full_body = re.sub(
        r'\\textbf\{Описание:\}\s*.*?(?=\\begin\{(?:object|axiom|theorem|operation|property)\}|\\textbf\{(?!Описание)\}|\\section|$)',
        '', full_body, flags=re.DOTALL
    )
    full_body = full_body.strip()
    
    return {
        "id": entity_id,
        "type": entity_type,
        "module": module,
        "title": title,
        "source": source,
        "formulas": formulas,
        "full_body": full_body,
        "nl_desc": nl_desc,
        "deps": deps,
        "path": filepath
    }

def find_entity_file(entity_id):
    pattern = f"[{entity_id}].tex"
    for dirpath, _, filenames in os.walk(CONTENT_DIR):
        for fn in filenames:
            if pattern in fn:
                return Path(dirpath) / fn
    return None

def bfs_collect(root_id, args=None):
    visited = []
    queue = [root_id]
    seen = set()
    no_enrich = getattr(args, 'no_enrich', False) if args else False
    
    while queue:
        eid = queue.pop(0)
        if eid in seen:
            continue
        seen.add(eid)
        
        fpath = find_entity_file(eid)
        if fpath is None:
            if no_enrich:
                print(f"  [SKIP] {eid} — file not found (--no-enrich mode).")
                continue
            print(f"  [MISSING] {eid} — file not found. Triggering Pipeline v2 enrichment...")
            # Преобразуем ID в человеческий запрос (например, 'prop-partial-order' -> 'partial order')
            human_query = eid.split('-', 1)[1].replace('-', ' ') if '-' in eid else eid
            
            # Resolve module configs using passed args (or defaults)
            from pipeline.config import resolve_module_config
            from pipeline.ollama_wrapper import run_enrichment_pipeline
            
            extract_provider = extract_model = extract_api_key = None
            preview_provider = preview_model = preview_api_key = None
            synth_provider = synth_model = synth_api_key = None
            lean_provider = lean_model = lean_api_key = None
            cv_model = "glm-ocr"
            no_validate = False
            
            if args:
                extract_provider, extract_model, extract_api_key = resolve_module_config(
                    module="extract",
                    global_provider=args.provider, global_model=args.model, global_api_key=args.api_key,
                    module_provider=args.extract_provider, module_model=args.extract_model, module_api_key=args.extract_api_key,
                )
                preview_provider, preview_model, preview_api_key = resolve_module_config(
                    module="preview",
                    global_provider=args.provider, global_model=args.model, global_api_key=args.api_key,
                    module_provider=args.extract_preview_provider, module_model=args.extract_preview_model, module_api_key=args.extract_preview_api_key,
                )
                synth_provider, synth_model, synth_api_key = resolve_module_config(
                    module="synth",
                    global_provider=args.provider, global_model=args.model, global_api_key=args.api_key,
                    module_provider=args.synth_provider, module_model=args.synth_model, module_api_key=args.synth_api_key,
                )
                lean_provider = args.lean_provider
                lean_model = args.lean_model
                lean_api_key = args.lean_api_key
                cv_model = args.cv_model
                no_validate = args.no_validate

            try:
                success, generated, _ = run_enrichment_pipeline(
                    human_query,
                    extract_provider=extract_provider, extract_api_key=extract_api_key, extract_model=extract_model,
                    preview_provider=preview_provider, preview_api_key=preview_api_key, preview_model=preview_model,
                    synth_provider=synth_provider,     synth_api_key=synth_api_key,     synth_model=synth_model,
                    lean_provider=lean_provider,        lean_api_key=lean_api_key,        lean_model=lean_model,
                    cv_model=cv_model,
                    no_validate=no_validate,
                )
            except Exception as e:
                import traceback
                print(f"  [ERROR] Failed to run enrichment pipeline: {e}", flush=True)
                traceback.print_exc(file=sys.stdout)
                print(f"  [SKIP] {eid} — enrichment failed, skipping.")
                continue
            
            if success:
                fpath = find_entity_file(eid)
            if fpath is None:
                print(f"  [SKIP] {eid} — failed to generate or find.")
                continue

        
        data = parse_canonical(fpath)
        visited.append(data)
        print(f"  [BFS] {eid} -> deps: {data['deps']}")
        
        for dep in data['deps']:
            if dep not in seen:
                queue.append(dep)
    
    return visited

import argparse

def multi_root_bfs_collect(root_ids, args=None):
    """Runs BFS from multiple roots, merging graphs without duplication."""
    all_entities = []
    seen_ids = set()

    for root_id in root_ids:
        print(f"\n=== BFS от корня: {root_id} ===")
        branch = bfs_collect(root_id, args)
        for entity in branch:
            if entity["id"] not in seen_ids:
                seen_ids.add(entity["id"])
                all_entities.append(entity)

    return all_entities

def main():
    parser = argparse.ArgumentParser(description="Dynamic LaTeX Compiler via BFS (Multi-Root)")
    parser.add_argument('--root', type=str, default=None, help='Single root entity ID')
    parser.add_argument('--roots', type=str, default=None, help='Comma-separated root entity IDs')
    
    # Forwarded model configurations
    parser.add_argument("--cv-model", type=str, default="glm-ocr")
    parser.add_argument("--provider", type=str, default=None)
    parser.add_argument("--model",    type=str, default=None)
    parser.add_argument("--api-key",  type=str, default=None)

    parser.add_argument("--extract-provider", type=str, default=None)
    parser.add_argument("--extract-model",    type=str, default=None)
    parser.add_argument("--extract-api-key",  type=str, default=None)
    
    parser.add_argument("--extract-preview-provider", type=str, default=None)
    parser.add_argument("--extract-preview-model",    type=str, default=None)
    parser.add_argument("--extract-preview-api-key",  type=str, default=None)

    parser.add_argument("--synth-provider", type=str, default=None)
    parser.add_argument("--synth-model",    type=str, default=None)
    parser.add_argument("--synth-api-key",  type=str, default=None)

    parser.add_argument("--lean-provider", type=str, default=None)
    parser.add_argument("--lean-model",    type=str, default=None)
    parser.add_argument("--lean-api-key",  type=str, default=None)
    parser.add_argument("--embed-provider", type=str, default=None)
    parser.add_argument("--embed-model",    type=str, default=None)
    parser.add_argument("--embed-api-key",  type=str, default=None)
    parser.add_argument("--no-validate", action='store_true')
    parser.add_argument("--force-refresh", action='store_true', help='Force override of cached NLP translations')
    parser.add_argument("--no-enrich", action='store_true', help='Skip enrichment of missing entities; compile only existing content')

    args = parser.parse_args()


    nl_cache = {}
    if CACHE_PATH.exists():
        with open(CACHE_PATH, "r", encoding="utf-8") as f:
            nl_cache = json.load(f)


    if args.roots:
        root_ids = [r.strip() for r in args.roots.split(',') if r.strip()]
    elif args.root:
        root_ids = [args.root]
    else:
        print("[-] Укажите --root или --roots")
        return

    # Resolve configurations for all modules
    from pipeline.config import resolve_module_config
    
    extract_provider, extract_model, extract_api_key = resolve_module_config(
        module="extract",
        global_provider=args.provider, global_model=args.model, global_api_key=args.api_key,
        module_provider=args.extract_provider, module_model=args.extract_model, module_api_key=args.extract_api_key,
    )
    preview_provider, preview_model, preview_api_key = resolve_module_config(
        module="preview",
        global_provider=args.provider, global_model=args.model, global_api_key=args.api_key,
        module_provider=args.extract_preview_provider, module_model=args.extract_preview_model, module_api_key=args.extract_preview_api_key,
    )
    synth_provider, synth_model, synth_api_key = resolve_module_config(
        module="synth",
        global_provider=args.provider, global_model=args.model, global_api_key=args.api_key,
        module_provider=args.synth_provider, module_model=args.synth_model, module_api_key=args.synth_api_key,
    )
    embed_provider, embed_model, embed_api_key = resolve_module_config(
        module="embed",
        global_provider=args.provider, global_model=args.model, global_api_key=args.api_key,
        module_provider=getattr(args, 'embed_provider', None),
        module_model=getattr(args, 'embed_model', None),
        module_api_key=getattr(args, 'embed_api_key', None),
    )

    # Setup ModelManager roles
    from pipeline.model_manager import ModelManager
    mgr = ModelManager.get_instance()
    mgr.setup_role("extract", extract_provider, extract_model, extract_api_key)
    mgr.setup_role("synth",   synth_provider,   synth_model,   synth_api_key)
    mgr.setup_role("embed",   embed_provider,   embed_model,   embed_api_key)
    print(f"[*] Embed role: provider={embed_provider}, model={embed_model}, host={embed_api_key or 'localhost:11434'}")

    print(f"=== DYNAMIC COMPILER: Сборка графа для {root_ids} (Multi-Root BFS) ===\n")

    entities = multi_root_bfs_collect(root_ids, args)

    print(f"\nCollected {len(entities)} unique entities.\n")

    # Recursive lean-validation loop: discover missing mathesis dependencies and trigger enrichment
    # Skip entirely if --no-validate or --no-enrich is set
    if args.no_validate or args.no_enrich:
        print("[SKIP] Lean validation/enrichment loop skipped (--no-validate or --no-enrich).\n")
    else:
        from pipeline.lean_validator import validate_entity
        from pipeline.ollama_wrapper import get_missing_deps_from_lean_error, run_enrichment_pipeline

        max_iters = 5
        iter_count = 0
        roots_changed = True
        while iter_count < max_iters and roots_changed:
            iter_count += 1
            roots_changed = False
            missing_terms = []
            for ent in entities:
                eid = ent["id"]
                lean_path = PROJECT_ROOT / "lean_validator" / "Validated" / f"{eid}.lean"
                if not lean_path.exists():
                    continue
                lean_code = lean_path.read_text(encoding='utf-8')
                result = validate_entity(eid, lean_code)
                if result.get("status") != "success":
                    # Log the Lean compile errors
                    error_feedback = "\n".join([f"Line {e['line']}: {e['message']}" for e in result.get("errors", [])])
                    from pipeline.export_to_lean import log_to_file
                    log_to_file("lean_errors", error_feedback, entity_id=eid)
                    
                    missing = get_missing_deps_from_lean_error(result.get("errors", []))
                    mathesis_deps = [d for d in missing if any(d.startswith(p) for p in ["obj-", "prop-", "op-", "thm-", "def-"]) ]
                    for dep in mathesis_deps:
                        human = dep.split('-',1)[1].replace('-', ' ')
                        if human not in missing_terms:
                            missing_terms.append(human)
            if not missing_terms:
                break
            print(f"[Validation loop {iter_count}] Found missing dependencies to enrich: {missing_terms}")
            for term in missing_terms:
                ok, gen, _ = run_enrichment_pipeline(
                    term,
                    extract_provider=extract_provider, extract_api_key=extract_api_key, extract_model=extract_model,
                    preview_provider=preview_provider, preview_api_key=preview_api_key, preview_model=preview_model,
                    synth_provider=synth_provider,     synth_api_key=synth_api_key,     synth_model=synth_model,
                    lean_provider=args.lean_provider,  lean_api_key=args.lean_api_key,  lean_model=args.lean_model,
                    cv_model=args.cv_model,
                    no_validate=args.no_validate,
                )
                if ok:
                    roots_changed = True
            if roots_changed:
                # rebuild entities graph to include newly synthesized entities
                entities = multi_root_bfs_collect(root_ids, args)

        print(f"Validation/enrichment loop finished after {iter_count} iterations.")

    # Build and log the final graph structure for this query
    from pipeline.export_to_lean import log_to_file
    
    graph_lines = []
    graph_lines.append("=== FINAL GRAPH STRUCTURE ===")
    graph_lines.append(f"Query Roots: {root_ids}")
    graph_lines.append(f"Total Unique Entities: {len(entities)}\n")
    
    graph_lines.append("Nodes:")
    for ent in entities:
        graph_lines.append(f"  - {ent['id']} (Type: {ent['type']})")
        
    graph_lines.append("\nEdges (Dependencies):")
    for ent in entities:
        if ent.get('deps'):
            for dep in ent['deps']:
                graph_lines.append(f"  {ent['id']} -> {dep}")
        else:
            graph_lines.append(f"  {ent['id']} -> (No dependencies)")
            
    graph_content = "\n".join(graph_lines)
    
    # Save log to logs/graphs/ category using the combined roots as the entity_id
    combined_roots = "_".join(root_ids)
    log_to_file("graphs", graph_content, entity_id=combined_roots)

    content = ""
    for data in entities:
        # Synthesize bilingual details and natural language descriptions
        synth_ru, synth_en, desc_ru, desc_en = synthesize_entity_details(
            data=data,
            provider=synth_provider,
            model=synth_model,
            api_key=synth_api_key,
            force_refresh=args.force_refresh,
            nl_cache=nl_cache
        )
        
        # Enrich NLP descriptions with hyperlinks for known entities in the cache
        def enrich_text(text):
            if not text: return text
            # sort by length descending to match longest names first
            sorted_entities = sorted(nl_cache.values(), key=lambda x: len(x.get("name_ru", "")), reverse=True)
            for ent in sorted_entities:
                n_ru = ent.get("name_ru", "").strip()
                eid = ent.get("id", "")
                if len(n_ru) > 3 and eid != data["id"]:
                    # Match the exact word, case-sensitive or insensitive depending on needs
                    # Just simple word match for now
                    pattern = r"(?<!\\hyperlink\{)" + re.escape(n_ru) + r"(?![a-zA-Zа-яА-Я])"
                    text = re.sub(pattern, lambda m, eid=eid, n_ru=n_ru: f"\\hyperlink{{{eid}}}{{{n_ru}}}", text)
            return text
            
        desc_ru = enrich_text(desc_ru)

        
        title_bilingual = f"{synth_ru} / {synth_en}"
        
        # Resolve book citation base key
        book_key = data["source"].split(",")[0].strip().lower()
        book_key_base = re.sub(r'[-\d]', '', book_key).strip()
        citation = BOOK_CITATIONS.get(book_key_base, BOOK_CITATIONS.get(book_key, data["source"]))
        page_info = data["source"]
        if "," in page_info:
            page_info = page_info.split(",", 1)[1].strip() # Clean up formatting for display
        citation_full = f"{citation}, {page_info}"
        
        # Map type to Russian textbook terminology
        TYPE_MAPPING = {
            "object": "Объект",
            "operation": "Операция",
            "property": "Свойство",
            "axiom": "Аксиома",
            "theorem": "Теорема",
            "lemma": "Лемма",
            "corollary": "Следствие",
        }
        type_ru = TYPE_MAPPING.get(data["type"].lower(), data["type"].capitalize())
        
        # Assembly of a highly readable and clean bilingual chapter block
        block = f"\\chapter{{{title_bilingual}}}\\label{{entity:{data['id']}}}\n"
        block += f"\\textbf{{Тип:}} {type_ru} \\hfill \\textbf{{Источник:}} {citation_full}\n\n"
        block += "\\vspace{0.5em}\n\\hrule\n\\vspace{1em}\n\n"
        
        # 1. Russian formulation (first)
        block += "\\section*{Формулировка на русском языке}\n"
        if desc_ru:
            block += f"{desc_ru}\n\n"
        else:
            block += "Формулировка отсутствует.\n\n"
            
        # 2. English formulation (second)
        block += "\\section*{Formulation in English}\n"
        if desc_en:
            block += f"{desc_en}\n\n"
        else:
            block += "Formulation is not available.\n\n"
            
        # 3. Mathematical formulation (third)
        block += "\\section*{Математическая формулировка}\n"
        # Strip internal ID leaks (math env arguments)
        clean_body = data.get("full_body", "")
        clean_body = re.sub(r'\\begin\{(object|operation|property|axiom|theorem|lemma|corollary)\}\[[^\]]+\]', r'\\begin{\1}', clean_body)
        
        block += f"{clean_body}\n\n"
        
        content += block
    
    output_dir = PROJECT_ROOT / "output"
    output_dir.mkdir(parents=True, exist_ok=True)
    result_tex = output_dir / "result.tex"
    with open(result_tex, "w", encoding="utf-8") as f:
        f.write(TEMPLATE % {"content": content})
    
    print(f"Generated {result_tex}")
    
    # Rebuild master.tex at the very end during result formation
    try:
        from pipeline.canonical_synthesizer import rebuild_master_tex
        rebuild_master_tex()
    except Exception as e:
        print(f"[WARN] Failed to rebuild master.tex: {e}")
    
    # Copy style files into output dir for pdflatex
    for sty in ["mathesis.sty", "mathesis_macros.sty"]:
        sty_dest = output_dir / sty
        if not sty_dest.exists():
            sty_src = CONTENT_DIR / sty
            if sty_src.exists():
                shutil.copy(sty_src, sty_dest)
            elif (PROJECT_ROOT / sty).exists():
                shutil.copy(PROJECT_ROOT / sty, sty_dest)
    
    pdflatex_cmd = [
        "pdflatex",
        "-interaction=nonstopmode",
        f"-output-directory={output_dir}",
        str(result_tex),
    ]

    print("Compiling result.pdf (pass 1)...")
    subprocess.run(pdflatex_cmd, capture_output=True, text=True, cwd=str(output_dir))
    
    print("Compiling result.pdf (pass 2 for references)...")
    result = subprocess.run(pdflatex_cmd, capture_output=True, text=True, cwd=str(output_dir))
    
    result_pdf = output_dir / "result.pdf"
    if result_pdf.exists():
        print(f"PDF compilation successful! -> {result_pdf}")
    else:
        print("PDF compilation issue. Last 500 chars of log:")
        print(result.stdout[-500:])

if __name__ == "__main__":
    main()
