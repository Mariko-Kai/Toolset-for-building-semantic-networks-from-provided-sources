"""
Ollama Wrapper v2 — Multi-Result Routing
=========================================
Routes user queries to existing entities or triggers enrichment pipeline.
Returns ALL matching entities (not just one).
Supports reasoning/thinking models (like deepseek-r1) by stripping <think> tags.
"""
import argparse
import subprocess
import os
import json
import urllib.request
import re
import sys
import io
import difflib
from pathlib import Path

# Fix Windows console encoding
if sys.platform == 'win32' and getattr(sys.stdout, 'encoding', '').lower() != 'utf-8':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.config import PROVIDERS, resolve_module_config
from pipeline.model_manager import ModelManager
from pipeline.export_to_lean import setup_provider


# ── Path Configuration ───────────────────────────────────────────────────────
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONTENT_DIR = PROJECT_ROOT / "content"
GENERATE_SCRIPT = PROJECT_ROOT / "pipeline" / "generate_answer.py"
EXTRACTOR_SCRIPT = PROJECT_ROOT / "pipeline" / "ensemble_extractor.py"
ALIGNER_SCRIPT = PROJECT_ROOT / "pipeline" / "entity_aligner.py"
SYNTHESIZER_SCRIPT = PROJECT_ROOT / "pipeline" / "canonical_synthesizer.py"


# ── Entity Discovery ────────────────────────────────────────────────────────

def get_available_entities():
    """Scans content/ directory and collects entity IDs and titles."""
    entities = []
    if not CONTENT_DIR.exists():
        return entities
    for filepath in CONTENT_DIR.rglob("*.tex"):
        match = re.search(r'\[([^\]]+)\]\.tex$', filepath.name)
        if match:
            entity_id = match.group(1)
            title = filepath.name.replace(f" [{entity_id}].tex", "")
            entities.append({"id": entity_id, "title": title, "path": str(filepath)})
    return entities



# ── Keyword Extraction ───────────────────────────────────────────────────────

def extract_term_ru_en(term: str) -> tuple:
    """Translates a term into EN and RU using LLM with a robust local dictionary fallback."""
    term_clean = term.strip().lower()
    
    # Standard mathematical dictionary fallback for robust translation
    MATH_DICT = {
        "open interval": ("открытый интервал", "open interval"),
        "open intervals": ("открытые интервалы", "open intervals"),
        "closed interval": ("замкнутый интервал", "closed interval"),
        "closed intervals": ("замкнутые интервалы", "closed intervals"),
        "real number": ("вещественное число", "real number"),
        "real numbers": ("вещественные числа", "real numbers"),
        "natural number": ("натуральное число", "natural number"),
        "natural numbers": ("натуральные числа", "natural numbers"),
        "rational number": ("рациональное число", "rational number"),
        "rational numbers": ("рациональные числа", "rational numbers"),
        "continuous": ("непрерывная", "continuous"),
        "derivative": ("производная", "derivative"),
        "derivative at point": ("производная в точке", "derivative at point"),
        "integral": ("интеграл", "integral"),
        "limit": ("предел", "limit"),
        "set": ("множество", "set"),
        "real numbers": ("вещественные числа", "real numbers"),
        "sequence": ("последовательность", "sequence"),
        "series": ("ряд", "series"),
        "continuous": ("непрерывный", "continuous"),
        "theorem": ("теорема", "theorem"),
        "lemma": ("лемма", "lemma"),
        "axiom": ("аксиома", "axiom"),
        "supremum": ("супремум", "supremum"),
        "infimum": ("инфимум", "infimum"),
        "cartesian product": ("декартово произведение", "cartesian product"),
        "partial order": ("частичный порядок", "partial order"),
        "ordered set": ("упорядоченное множество", "ordered set"),
    }
    
    if term_clean in MATH_DICT:
        return MATH_DICT[term_clean]

    from pipeline.model_manager import ModelManager
    mgr = ModelManager.get_instance()
    prompt = f"""You are a professional mathematical translator.
Translate the mathematical term '{term}' into:
1. Russian (term_ru) - MUST be in Russian!
2. English (term_en) - MUST be in English!

IMPORTANT: Translate the term completely and literally, preserving all descriptive mathematical properties and contextual constraints present in the original term. Do NOT condense or simplify the translation into short eponymous names if the original term explicitly includes descriptive characteristics.

Return STRICTLY a JSON object with no other text or explanation:
{{
    "term_ru": "exact translation of the mathematical term in Russian",
    "term_en": "exact translation of the mathematical term in English"
}}"""
    resp = mgr.query_llm(prompt, json_mode=True, role="extract")
    try:
        parsed = json.loads(resp)
        return parsed.get("term_ru", term), parsed.get("term_en", term)
    except:
        return term, term


def extract_keyword(query):
    """
    Deterministically extracts a clean mathematical term from the user query.
    Strips question words to act like a search engine, and translates to RU and EN.
    """
    stop_words = [
        "что называется", "что такое", "расскажи про", "дайте определение", 
        "определение", "свойства", "что значит", "как найти", "понятие", "объясни"
    ]
    
    clean = query.lower()
    for sw in stop_words:
        clean = clean.replace(sw, "")
    
    # Clean up punctuation and extra spaces
    import string
    punct_to_remove = string.punctuation.replace('-', '')
    clean = clean.translate(str.maketrans('', '', punct_to_remove))
    clean = " ".join(clean.split())
    
    # Translate clean term to both RU and EN
    canonical_ru, canonical_en = extract_term_ru_en(clean)
    
    # Clean them up just in case
    ru_term = canonical_ru.translate(str.maketrans('', '', punct_to_remove)).lower().strip()
    en_term = canonical_en.translate(str.maketrans('', '', punct_to_remove)).lower().strip()
    
    print(f"[*] Целевой термин (RU): '{ru_term}'")
    print(f"[*] Целевой термин (EN): '{en_term}'")
    return ru_term, en_term


# ── Multi-Result Entity Resolution ───────────────────────────────────────────

def normalize_math_term(term):
    """Кастомный стеммер/нормализатор для математических терминов"""
    import re
    t = term.lower()
    t = re.sub(r'\b(theorem|thm|prop|proposition|def|definition|lemma|axm|axiom)\b', '', t)
    t = re.sub(r'[^\w\s\-]', '', t)
    stop_words = {"the", "of", "on", "in", "a", "an", "for", "at", "by", "and", "or", "to"}
    words = []
    for w in t.split():
        if w in stop_words:
            continue
        if len(w) > 4:
            w = re.sub(r'(ый|ая|ое|ые|ого|ей|их|ом|ем|ой|у|а|о|е|и|ы|я|ic|al|ion|ing|ed|s)$', '', w)
        words.append(w)
    return " ".join(sorted(words))



def cosine_similarity(v1, v2):
    import math
    if not v1 or not v2: return 0.0
    dot = sum(a*b for a,b in zip(v1, v2))
    norm1 = math.sqrt(sum(a*a for a in v1))
    norm2 = math.sqrt(sum(b*b for b in v2))
    if norm1 == 0 or norm2 == 0: return 0.0
    return dot / (norm1 * norm2)

def resolve_entities(query, canonical_term, available_entities):
    """
    Resolves query using Shift-Left Semantic Search Architecture.
    1. Dictionary (Normalized string match)
    2. Vector Embedding Search (cosine similarity > 0.85)
    3. LLM-Judge Arbitration (goedel-prover)
    """
    from pipeline.model_manager import ModelManager
    mgr = ModelManager.get_instance()
    import sqlite3
    import struct
    import json
    import re
    from pathlib import Path
    
    db_path = PROJECT_ROOT / "db/mathesis_index.db"
    if not db_path.exists():
        return [], canonical_term
        
    conn = sqlite3.connect(db_path, timeout=10.0)
    cursor = conn.cursor()
    
    try:
        cursor.execute("SELECT entity_id, title, nl_desc, embedding, lean_path FROM entities")
        rows = cursor.fetchall()
    except sqlite3.OperationalError:
        conn.close()
        return [], canonical_term
        
    conn.close()
    
    # 1. Normalization (Dictionary Search)
    norm_query = normalize_math_term(canonical_term)
    candidates = []
    
    for eid, title, nl_desc, emb_blob, lean_path in rows:
        norm_title = normalize_math_term(title)
        if norm_query == norm_title:
            candidates.append({"entity_id": eid, "title": title, "nl_desc": nl_desc, "score": 1.0, "method": "dictionary"})
            
    # 2. Embedding Search (Always run to pool candidates)
    if not candidates:
        try:
            query_emb = mgr.get_embedding(canonical_term, role="embed")
            if query_emb:
                for eid, title, nl_desc, emb_blob, lean_path in rows:
                    if emb_blob:
                        num_floats = len(emb_blob) // 4
                        emb_vec = struct.unpack(f"{num_floats}f", emb_blob)
                        sim = cosine_similarity(query_emb, emb_vec)
                        if sim > 0.85:
                            candidates.append({"entity_id": eid, "title": title, "nl_desc": nl_desc, "score": sim, "method": "embedding"})
        except Exception as e:
            print(f"[-] Embedding search failed: {e}")
            
    if not candidates:
        return [], canonical_term
        
    # Sort candidates by score
    candidates.sort(key=lambda x: x["score"], reverse=True)
    
    # 3. LLM-Judge Arbitration
    for best_candidate in candidates:
        print(f"[*] Candidate found by {best_candidate['method']}: {best_candidate['entity_id']} (score {best_candidate['score']:.2f})")
        
        desc_text = str(best_candidate['nl_desc'])[:1000] if best_candidate['nl_desc'] else "No description available."
        prompt = f"""You are 'goedel-prover', a strict mathematical arbiter.
Your goal is to decide if the USER TERM is EXACTLY equivalent to the CANDIDATE entity in the context of mathematical definitions.

USER TERM: "{canonical_term}"

CANDIDATE TITLE: "{best_candidate['title']}"
CANDIDATE DESCRIPTION:
{desc_text}

Is the USER TERM identical to this CANDIDATE? 
Answer EXACTLY with valid JSON:
{{ "is_identical": true, "reason": "short explanation" }} or {{ "is_identical": false, "reason": "why they differ" }}
"""
        try:
            response = mgr.query_llm(prompt, json_mode=True, role="extract")
            match = re.search(r'(\\{.*\\})', response, re.DOTALL)
            if match: response = match.group(1)
            
            decision = json.loads(response)
            if decision.get("is_identical", False):
                print(f"[Queue] [+] Goedel Arbitration confirmed match for {best_candidate['entity_id']}: {decision.get('reason')}")
                return [{"entity_id": best_candidate["entity_id"], "confidence": best_candidate["score"]}], canonical_term
            else:
                print(f"[Queue] [-] Goedel Arbitration rejected match for {best_candidate['entity_id']}: {decision.get('reason')}")
        except Exception as e:
            print(f"[-] Failed to parse arbiter JSON: {e}")
            if best_candidate["method"] == "dictionary":
                return [{"entity_id": best_candidate["entity_id"], "confidence": 1.0}], canonical_term
            
    return [], canonical_term





def translate_term(term: str, model: str = None, provider: str = None) -> tuple[str, str]:
    """Translates the term to RU and EN, ensuring correct search terms are used."""
    prompt = f"""You are a professional mathematician. Translate the following term to Russian and English.
Return ONLY valid JSON like this: {{"ru": "...", "en": "..."}}

Term to translate: "{term}"
"""
    try:
        from pipeline.model_manager import ModelManager
        mgr = ModelManager.get_instance()
        resp = mgr.query_llm(prompt, json_mode=True, role="extract")
        import re, json
        # Strip markdown JSON wrappers if present
        resp = re.sub(r'^```json\s*', '', resp.strip(), flags=re.MULTILINE)
        resp = re.sub(r'^```\s*$', '', resp.strip(), flags=re.MULTILINE).strip()
        data = json.loads(resp)
        return data.get("ru", term), data.get("en", term)
    except Exception as e:
        print(f"[-] Failed to translate term: {e}")
        return term, term

def run_enrichment_pipeline(
    clean_term, *,
    # Extraction module
    extract_provider=None, extract_api_key=None, extract_model=None,
    # Preview module (fast page scan)
    preview_provider=None, preview_api_key=None, preview_model=None,
    # Synthesis module
    synth_provider=None, synth_api_key=None, synth_model=None,
    # Lean module
    lean_provider=None, lean_api_key=None, lean_model=None,
    # Embed module
    embed_provider=None, embed_api_key=None, embed_model=None,
    # OCR
    cv_model="glm-ocr",
    # Skip internal lean validation when synthesizer supports it
    no_validate=False,
    canonical_term="",
    # OCR pages override (skip search, process only these pages)
    ocr_pages_spec=None,
    term_ru=None,
):
    """Runs the full extraction → alignment → synthesis pipeline. Returns list of generated entity IDs."""
    print(f"\n[*] === AUTO-ENRICHMENT: Запускаю конвейер обогащения ===")

    if term_ru:
        term_en = clean_term
    else:
        if extract_provider:
            setup_provider(extract_provider, api_key=extract_api_key, model=extract_model)
        term_ru, term_en = translate_term(clean_term, model=extract_model, provider=extract_provider)
        
    print(f"[*] Целевой термин (RU): '{term_ru}'")
    print(f"[*] Целевой термин (EN): '{term_en}'")

    env = os.environ.copy()
    env['PYTHONIOENCODING'] = 'utf-8'
    env['PYTHONUNBUFFERED'] = '1'
    env['HF_HUB_OFFLINE'] = '1'
    env['TRANSFORMERS_OFFLINE'] = '1'

    # ── Аргументы для ensemble_extractor (extraction) ────────────────────────
    extract_args = ["--cv-model", cv_model]
    if extract_provider:
        extract_args += ["--extract-provider", extract_provider]
        if extract_api_key: extract_args += ["--extract-api-key", extract_api_key]
        if extract_model:   extract_args += ["--extract-model", extract_model]
    if preview_provider:
        extract_args += ["--extract-preview-provider", preview_provider]
        if preview_api_key: extract_args += ["--extract-preview-api-key", preview_api_key]
        if preview_model:   extract_args += ["--extract-preview-model", preview_model]
    if lean_provider:
        extract_args += ["--lean-provider", lean_provider]
    # OCR pages override
    if ocr_pages_spec:
        extract_args += ["--ocr-pages", ocr_pages_spec]

    # ── Аргументы для canonical_synthesizer (synth) ──────────────────────────
    synth_args = ["--cv-model", cv_model]
    if no_validate:
        synth_args += ["--no-validate"]
    if canonical_term:
        synth_args += ["--canonical-term", canonical_term]
    if synth_provider:
        synth_args += ["--synth-provider", synth_provider]
        if synth_api_key: synth_args += ["--synth-api-key", synth_api_key]
        if synth_model:   synth_args += ["--synth-model", synth_model]
    if lean_provider:
        synth_args += ["--lean-provider", lean_provider]
        if lean_api_key: synth_args += ["--lean-api-key", lean_api_key]
        if lean_model:   synth_args += ["--lean-model", lean_model]
    if embed_provider:
        synth_args += ["--embed-provider", embed_provider]
        if embed_api_key: synth_args += ["--embed-api-key", embed_api_key]
        if embed_model:   synth_args += ["--embed-model", embed_model]

    steps = [
        ("1/3", "Извлечение из учебников",
         [sys.executable, str(EXTRACTOR_SCRIPT), f"{term_ru}|{term_en}"] + extract_args),
        ("2/3", "Выравнивание формулировок",
         [sys.executable, str(ALIGNER_SCRIPT)]),
        ("3/3", "Синтез канонической записи",
         [sys.executable, str(SYNTHESIZER_SCRIPT)] + synth_args),
    ]

    generated_entities = []
    generated_entities_deps = {}

    for step_num, step_name, cmd in steps:
        print(f"\n[{step_num}] {step_name}...")
        try:
            process = subprocess.Popen(cmd, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8')
            for line in iter(process.stdout.readline, ''):
                print(line, end='', flush=True)
                if step_num == "3/3":
                    if "[synthesizer] Parsed: entity_id=" in line:
                        match = re.search(r'entity_id=([^,\s,]+)', line)
                        if match:
                            generated_entities.append(match.group(1).strip())
                    if "[synthesizer] ParsedDeps:" in line:
                        try:
                            payload = json.loads(line.split("ParsedDeps: ", 1)[1])
                            eid = payload.get("entity_id")
                            deps = payload.get("deps", [])
                            if eid:
                                generated_entities_deps[eid] = deps
                        except Exception:
                            pass
            process.wait()
            if process.returncode != 0:
                print(f"[-] Ошибка на шаге {step_num} (код: {process.returncode})")
                return False, [], {}
        except Exception as e:
            print(f"[-] Не удалось запустить шаг {step_num}: {e}")
            return False, [], {}

    print(f"\n[+] Конвейер обогащения завершен успешно!")
    return True, generated_entities, generated_entities_deps


# ── Main ─────────────────────────────────────────────────────────────────────

def get_missing_deps_from_lean_error(error_msgs):
    """Parses Lean 4 error messages to find missing dependencies."""
    missing = []
    for msg in error_msgs:
        # e.g., "unknown constant 'obj-real-numbers'"
        match = re.search(r"unknown constant '([^']+)'", msg.get("message", ""))
        if match:
            missing.append(match.group(1).strip())
    return missing


def main():
    parser = argparse.ArgumentParser(description="Mathesis Pipeline — Multi-Result Wrapper")
    parser.add_argument("query", type=str, help="Входной запрос на естественном языке")
    parser.add_argument("--cv-model", type=str, default="glm-ocr",
                        help="Модель CV/OCR для обработки изображений")

    # ── Глобальные аргументы (оверрайдят ВСЕ модули) ─────────────────────────
    parser.add_argument("--provider", type=str, default=None, choices=PROVIDERS,
                        help="Глобальный LLM провайдер для всех модулей")
    parser.add_argument("--model",    type=str, default=None,
                        help="Глобальная LLM модель для всех модулей")
    parser.add_argument("--api-key",  type=str, default=None,
                        help="Глобальный API ключ для всех модулей")

    # ── Per-module: Extraction ────────────────────────────────────────────────
    parser.add_argument("--extract-provider", type=str, default=None, choices=PROVIDERS)
    parser.add_argument("--extract-model",    type=str, default=None)
    parser.add_argument("--extract-api-key",  type=str, default=None)
    # Preview (fast scan) options
    parser.add_argument("--extract-preview-provider", type=str, default=None, choices=PROVIDERS)
    parser.add_argument("--extract-preview-model",    type=str, default=None)
    parser.add_argument("--extract-preview-api-key",  type=str, default=None)

    # ── Per-module: Synthesis ─────────────────────────────────────────────────
    parser.add_argument("--synth-provider", type=str, default=None, choices=PROVIDERS)
    parser.add_argument("--synth-model",    type=str, default=None)
    parser.add_argument("--synth-api-key",  type=str, default=None)

    # ── Per-module: Lean formalization ────────────────────────────────────────
    parser.add_argument("--lean-provider", type=str, default=None, choices=PROVIDERS)
    parser.add_argument("--lean-model",    type=str, default=None)
    parser.add_argument("--lean-api-key",  type=str, default=None)
    parser.add_argument("--no-validate", action='store_true', help='Disable Lean validation inside synthesizer (default: enabled)')
    parser.add_argument("--force-refresh", action='store_true', help='Force overwrite of cached NLP translations (nl_translations_cache.json)')
    
    # ── Per-module: Embedding ────────────────────────────────────────────────
    parser.add_argument("--embed-provider", type=str, default="ollama", choices=PROVIDERS)
    parser.add_argument("--embed-model",    type=str, default="nomic-embed-text:latest")
    parser.add_argument("--embed-api-key",  type=str, default=None)
    
    # ── OCR Pages Override ────────────────────────────────────────────────────
    parser.add_argument("--ocr-pages", type=str, default=None,
                        help='Skip search and process only specified pages. Format: JSON {"book": "zorich", "pages": [1, 2, 3]} or comma-separated "1,2,3" (first book)')


    args = parser.parse_args()

    # ── Разрешаем конфигурацию для каждого модуля ────────────────────────────
    extract_provider, extract_model, extract_api_key = resolve_module_config(
        module="extract",
        global_provider=args.provider, global_model=args.model, global_api_key=args.api_key,
        module_provider=args.extract_provider, module_model=args.extract_model, module_api_key=args.extract_api_key,
    )
    # Preview config resolution
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
    lean_provider, lean_model, lean_api_key = resolve_module_config(
        module="lean",
        global_provider=args.provider, global_model=args.model, global_api_key=args.api_key,
        module_provider=args.lean_provider, module_model=args.lean_model, module_api_key=args.lean_api_key,
    )
    embed_provider, embed_model, embed_api_key = resolve_module_config(
        module="embed",
        global_provider=args.provider, global_model=args.model, global_api_key=args.api_key,
        module_provider=args.embed_provider, module_model=args.embed_model, module_api_key=args.embed_api_key,
    )

    # Setup ModelManager roles
    mgr = ModelManager.get_instance()
    mgr.setup_role("extract", extract_provider, extract_model, extract_api_key)
    mgr.setup_role("preview", preview_provider, preview_model, preview_api_key)
    mgr.setup_role("synth", synth_provider, synth_model, synth_api_key)
    mgr.setup_role("lean", lean_provider, lean_model, lean_api_key)
    mgr.setup_role("embed", embed_provider, embed_model, embed_api_key)
    print(f"[*] Embed role: provider={embed_provider}, model={embed_model}, host={embed_api_key or 'localhost:11434'}")

    active_provider_name = (extract_provider or "OLLAMA").upper()
    print(f"[*] Анализ запроса (Провайдер: {active_provider_name}, Модель: {extract_model}, CV: {args.cv_model})...")

    # Step 1: Extract clean keyword
    keyword, canonical = extract_keyword(args.query)

    # Queues for recursive resolution
    synthesis_queue = [canonical]
    validation_queue = []
    processed_synthesis_terms = set()
    validated_entities = set()
    root_generated_ids = [] # IDs generated specifically for the initial query term


    import sqlite3
    from pipeline.lean_validator import validate_entity
    
    # Dual-queue loop
    while synthesis_queue or validation_queue:
        
        # ── Phase 1: Process Synthesis Queue ──
        while synthesis_queue:
            # We pop from the front to process dependencies first (DFS-like)
            term = synthesis_queue.pop(0)
            
            if term in processed_synthesis_terms:
                continue
            processed_synthesis_terms.add(term)

            print(f"\n[Queue] Извлечение и синтез для термина: '{term}'")
            available = get_available_entities()
            matches, _ = resolve_entities(term, term, available)
            
            if matches:
                print(f"[Queue] Термин '{term}' уже существует в базе:")
                for m in matches:
                    print(f"    - {m['entity_id']} (confidence: {m['confidence']})")
                    # Add to validation queue if not already valid
                    if m['entity_id'] not in validated_entities and m['entity_id'] not in validation_queue:
                        validation_queue.append(m['entity_id'])
                continue
            
            # If not in base, trigger enrichment
            success, generated_ids, generated_deps = run_enrichment_pipeline(
                term,
                extract_provider=extract_provider, extract_api_key=extract_api_key, extract_model=extract_model,
                preview_provider=preview_provider, preview_api_key=preview_api_key, preview_model=preview_model,
                synth_provider=synth_provider,     synth_api_key=synth_api_key,     synth_model=synth_model,
                lean_provider=args.lean_provider,  lean_api_key=args.lean_api_key,  lean_model=args.lean_model,
                embed_provider=embed_provider,     embed_api_key=embed_api_key,     embed_model=embed_model,
                cv_model=args.cv_model,
                no_validate=args.no_validate,
                canonical_term=term,
                ocr_pages_spec=args.ocr_pages if hasattr(args, 'ocr_pages') else None,
                term_ru=keyword if term == canonical else None,
            )
            
            if success:
                print(f"[Queue] Синтезированы новые сущности: {generated_ids}")
                if term == canonical:
                    root_generated_ids.extend(generated_ids)
                for gid in generated_ids:
                    if gid not in validation_queue and gid not in validated_entities:
                        validation_queue.append(gid)
                # Immediate handling of generated deps: enqueue raw dep strings for synthesis and record pending edges
                if generated_deps:
                    import sqlite3 as _sqlite3
                    db_path = PROJECT_ROOT / "db/mathesis_index.db"
                    conn2 = _sqlite3.connect(db_path)
                    cur2 = conn2.cursor()
                    cur2.execute("CREATE TABLE IF NOT EXISTS pending_edges (source_id TEXT, raw_dep TEXT, status TEXT DEFAULT 'pending')")
                    for eid, deps in generated_deps.items():
                        for dep in deps:
                            clean_dep = dep.strip() if isinstance(dep, str) else str(dep)
                            if clean_dep and clean_dep not in processed_synthesis_terms and clean_dep not in synthesis_queue:
                                synthesis_queue.insert(0, clean_dep)  # prioritize dependencies
                            cur2.execute("INSERT INTO pending_edges (source_id, raw_dep, status) VALUES (?, ?, 'pending')", (eid, clean_dep))
                    conn2.commit()
                    conn2.close()
            else:
                print(f"[Queue] [-] Ошибка синтеза для '{term}'. Пропускаю.")

        # ── Phase 2: Process Validation Queue ──
        if validation_queue:
            # Take the first one in the queue
            eid = validation_queue.pop(0)
            
            if eid in validated_entities:
                continue
                
            print(f"\n[Queue] Lean-валидация для сущности: '{eid}'")
            
            # Load the lean draft saved by the synthesizer
            lean_file_path = PROJECT_ROOT / "lean_validator" / "Validated" / f"{eid}.lean"
            if not lean_file_path.exists():
                print(f"[Queue] [-] Lean файл не найден: {lean_file_path}")
                print(f"[Queue] [*] Запуск догенерации Lean для сущности {eid}...")
                
                from pipeline.export_to_lean import attempt_generation_with_repair
                tex_files = list(PROJECT_ROOT.joinpath("content").rglob(f"*[{eid}].tex"))
                if not tex_files:
                    print(f"[Queue] [-] Не удалось найти .tex файл для {eid} в content/ для догенерации!")
                    continue
                
                tex_content = tex_files[0].read_text(encoding='utf-8')
                entity_type = "def" if "def-" in eid else "prop"
                
                lean_strategy = mgr.strategies.get('lean')
                lean_model = getattr(lean_strategy, 'model_name', 'goedel:latest') if lean_strategy else 'goedel:latest'
                lean_code, is_valid = attempt_generation_with_repair(
                    eid, entity_type, tex_content, model=lean_model
                )
                
                if lean_code and is_valid:
                    lean_file_path.parent.mkdir(parents=True, exist_ok=True)
                    lean_file_path.write_text(lean_code, encoding='utf-8')
                    print(f"[Queue] [+] Успешно сгенерирован и сохранен {lean_file_path}")
                else:
                    print(f"[Queue] [-] Не удалось догенерировать Lean для {eid}")
                    continue
                
            lean_code = lean_file_path.read_text(encoding='utf-8')
            print(f"  Lean validating: {lean_code[:80]}...")
            
            # Run lean_validator logic directly
            result = validate_entity(eid, lean_code)
            
            if result["status"] == "success":
                print(f"[Queue] [OK] Сущность {eid} успешно прошла валидацию!")
                validated_entities.add(eid)
                
                # Append to SuccessfulEntities
                success_file = PROJECT_ROOT / "lean_validator" / "SuccessfulEntities.lean"
                if not success_file.exists():
                    success_file.write_text("import Mathlib\n\n-- Valid entities generated by Goedel-Formalizer\n\n", encoding='utf-8')
                with open(success_file, "a", encoding="utf-8") as f:
                    f.write(f"-- Entity: {eid}\n{lean_code}\n\n")
                    
            elif result["status"] == "timeout":
                print(f"[Queue] [TIMEOUT] Валидация для {eid} превысила время ожидания.")
                # Could re-queue or skip
            else:
                print(f"[Queue] [FAIL] Ошибки валидации для {eid}.")
                
                # Log the Lean errors
                error_feedback = "\n".join([f"Line {e['line']}: {e['message']}" for e in result.get("errors", [])])
                from pipeline.export_to_lean import log_to_file
                log_to_file("lean_errors", error_feedback, entity_id=eid)
                
                # Check for missing dependencies
                missing_deps = get_missing_deps_from_lean_error(result["errors"])
                mathesis_deps = [d for d in missing_deps if any(d.startswith(p) for p in ["obj-", "prop-", "op-", "thm-", "def-"])]
                
                if mathesis_deps:
                    print(f"[Queue] [!] Обнаружены отсутствующие зависимости: {mathesis_deps}")
                    print(f"[Queue] [+] Добавляю отсутствующие зависимости вне очереди (в начало S-Queue).")
                    
                    for dep in mathesis_deps:
                        # Clean prefix to use as natural language term
                        clean_dep = dep.replace('def-', '').replace('op-', '').replace('obj-', '').replace('prop-', '').replace('thm-', '').replace('-', ' ')
                        if clean_dep not in processed_synthesis_terms:
                            synthesis_queue.insert(0, clean_dep)
                    
                    # Re-queue the current entity at the end of the validation queue
                    print(f"[Queue] [*] Сущность {eid} возвращена в конец V-Queue.")
                    validation_queue.append(eid)
                else:
                    print(f"[Queue] [-] Семантические ошибки без явных пропущенных зависимостей.")
                    for e in result["errors"][:3]:
                        print(f"    - {e.get('message', '')}")
                    # Without dependencies missing, we don't automatically trigger re-synthesis in this wrapper.
                    # It would require Lean correction logic. We leave it as failed for now.

    print(f"\n[!] Конвейер полностью завершил работу (Очереди пусты).")
    
    # Generate the final PDF with the originally requested canonical entity
    available = get_available_entities()
    matches, _ = resolve_entities(args.query, canonical, available)
    
    root_ids = [m["entity_id"] for m in matches]
    
    # Fallback 1: use entities that passed Lean validation during this run
    if not root_ids and validated_entities:
        print(f"[*] Роутер не нашел точных совпадений, использую успешно валидированные сущности: {validated_entities}")
        root_ids = list(validated_entities)
    
    # Fallback 2: if there are recently synthesized root ids (legacy variable), use them
    elif not root_ids and 'root_generated_ids' in locals() and root_generated_ids:
        print(f"[*] Роутер не нашел точных совпадений, использую синтезированные результаты: {root_generated_ids}")
        root_ids = root_generated_ids

    if root_ids:
        roots_arg = ",".join(root_ids)
        print(f"\n[*] Сборка финального result.pdf для: {roots_arg}")
        cmd = [sys.executable, str(GENERATE_SCRIPT), "--roots", roots_arg]
        # Forward all model/provider parameters to maintain configuration in the sub-pipeline
        for arg_name, arg_val in vars(args).items():
            if arg_name in ["query", "roots", "root"]:
                continue
            if arg_val is True:
                cmd.append(f"--{arg_name.replace('_', '-')}")
            elif arg_val is False or arg_val is None:
                continue
            else:
                cmd.extend([f"--{arg_name.replace('_', '-')}", str(arg_val)])
                
        try:
            subprocess.run(cmd, check=True)
        except subprocess.CalledProcessError as e:
            print(f"[-] Ошибка генерации: {e}")
    else:
        print("[-] Не удалось найти итоговые сущности для генерации PDF.")

if __name__ == "__main__":
    main()

