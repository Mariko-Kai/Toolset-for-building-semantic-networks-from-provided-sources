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
import difflib
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.export_to_lean import query_llm, setup_provider, setup_lean_provider, _LLM_PROVIDER
from pipeline.config import PROVIDERS, resolve_module_config


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

def extract_keyword(query, model):
    """
    Deterministically extracts a clean mathematical term from the user query.
    Strips question words to act like a search engine. (Bypasses flaky LLM extraction).
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
    clean = clean.translate(str.maketrans('', '', string.punctuation))
    clean = " ".join(clean.split())
    
    # Translate to English using LLM
    prompt = f"Translate the mathematical term '{clean}' into English. Output ONLY the translated term in lowercase, no quotes, no punctuation, no explanations."
    en_term = query_llm(prompt, model=model).strip()
    
    # Clean it up just in case
    en_term = en_term.translate(str.maketrans('', '', string.punctuation)).lower()
    
    print(f"[*] Целевой термин (RU): '{clean}'")
    print(f"[*] Целевой термин (EN): '{en_term}'")
    return clean, en_term


# ── Multi-Result Entity Resolution ───────────────────────────────────────────

def resolve_entities(query, canonical_term, model, available_entities):
    """
    Resolves query against available entities. Returns ALL matches with confidence.
    Returns: (matches: list[dict], keyword: str)
    """
    if not available_entities:
        return [], canonical_term

    entities_str = "\n".join(
        f"- '{e['title']}' (ID: {e['id']})" for e in available_entities
    )

    prompt = f"""You are a STRICT semantic router for a mathematical database.

TASK: Find ALL entities from the available list that refer EXACTLY to the term "{canonical_term}".

AVAILABLE ENTITIES:
{entities_str}

USER TERM: "{canonical_term}"

RULES (EXTREMELY STRICT):
1. NO PARTIAL MATCHES: The entity's title MUST be a direct translation or exact synonym of "{canonical_term}".
2. NO CONCEPT MIXING: An operation is NOT the same as a class of objects. A limit operation is NOT a set. Reject these with confidence 0.0.
3. CONFIDENCE: 
   - 1.0 = EXACT match ONLY.
   - Do NOT return any entity with confidence < 1.0. 
   - If NO entities match EXACTLY, return an empty array `[]`.

Return ONLY valid JSON:
{{
    "matches": [
        {{"entity_id": "id", "confidence": 1.0, "reason": "why it is an EXACT match"}}
    ]
}}
"""
    response = query_llm(prompt, model=model)
    try:
        parsed = json.loads(response)
        matches = parsed.get("matches", [])
    except (json.JSONDecodeError, ValueError) as e:
        print(f"[-] Ошибка парсинга JSON: {e}\nОчищенный ответ модели:\n{response}")
        return [], canonical_term

    # Validate entity IDs exist
    valid_ids = {e["id"] for e in available_entities}
    validated_matches = []

    for m in matches:
        eid = m.get("entity_id", "")
        confidence = m.get("confidence", 0)

        if confidence < 0.7:
            continue

        if eid in valid_ids:
            validated_matches.append(m)
        else:
            # Try fuzzy match for typos
            closest = difflib.get_close_matches(eid, list(valid_ids), n=1, cutoff=0.90)
            if closest:
                m["entity_id"] = closest[0]
                validated_matches.append(m)

    return validated_matches, canonical_term


def translate_term(term, model="qwen3:8b"):
    """Translates a term into EN and RU using LLM."""
    prompt = f"""Translate the mathematical term '{term}' into both English and Russian.
Return strictly JSON:
{{
    "term_ru": "russian translation",
    "term_en": "english translation"
}}"""
    # JSON mode is tricky with some models without specific formatting prompts, but handled inside the unified query_llm if possible.
    # We enforce JSON by explicitly instructing it in the prompt (already done).
    resp = query_llm(prompt, model=model)
    try:
        parsed = json.loads(resp)
        return parsed.get("term_ru", term), parsed.get("term_en", term)
    except:
        return term, term


def run_enrichment_pipeline(
    clean_term, *,
    # Extraction module
    extract_provider=None, extract_api_key=None, extract_model=None,
    # Synthesis module
    synth_provider=None, synth_api_key=None, synth_model=None,
    # Lean module
    lean_provider=None, lean_api_key=None, lean_model=None,
    # OCR
    cv_model="glm-ocr",
):
    """Runs the full extraction → alignment → synthesis pipeline."""
    print(f"\n[*] === AUTO-ENRICHMENT: Запускаю конвейер обогащения ===")

    term_ru, term_en = translate_term(clean_term, model=extract_model)
    print(f"[*] Целевой термин (RU): '{term_ru}'")
    print(f"[*] Целевой термин (EN): '{term_en}'")

    env = os.environ.copy()
    env['PYTHONIOENCODING'] = 'utf-8'
    env['PYTHONUNBUFFERED'] = '1'

    # ── Аргументы для ensemble_extractor (extraction) ────────────────────────
    extract_args = ["--cv-model", cv_model]
    if extract_provider:
        extract_args += ["--extract-provider", extract_provider]
        if extract_api_key: extract_args += ["--extract-api-key", extract_api_key]
        if extract_model:   extract_args += ["--extract-model", extract_model]
    if lean_provider:
        extract_args += ["--lean-provider", lean_provider]

    # ── Аргументы для canonical_synthesizer (synth) ──────────────────────────
    synth_args = ["--cv-model", cv_model]
    if synth_provider:
        synth_args += ["--synth-provider", synth_provider]
        if synth_api_key: synth_args += ["--synth-api-key", synth_api_key]
        if synth_model:   synth_args += ["--synth-model", synth_model]
    if lean_provider:
        synth_args += ["--lean-provider", lean_provider]
        if lean_api_key: synth_args += ["--lean-api-key", lean_api_key]
        if lean_model:   synth_args += ["--lean-model", lean_model]

    steps = [
        ("1/3", "Извлечение из учебников",
         [sys.executable, str(EXTRACTOR_SCRIPT), f"{term_ru}|{term_en}"] + extract_args),
        ("2/3", "Выравнивание формулировок",
         [sys.executable, str(ALIGNER_SCRIPT)]),
        ("3/3", "Синтез канонической записи",
         [sys.executable, str(SYNTHESIZER_SCRIPT)] + synth_args),
    ]

    for step_num, step_name, cmd in steps:
        print(f"\n[{step_num}] {step_name}...")
        try:
            subprocess.run(cmd, env=env, check=True)
        except subprocess.CalledProcessError as e:
            print(f"[-] Ошибка на шаге {step_num} (код: {e.returncode})")
            return False
        except Exception as e:
            print(f"[-] Не удалось запустить шаг {step_num}: {e}")
            return False

    print(f"\n[+] Конвейер обогащения завершен успешно!")
    return True


# ── Main ─────────────────────────────────────────────────────────────────────

def main():
    global _LLM_PROVIDER, _GEMINI_CLIENT, _GEMINI_MODEL_NAME, _OPENAI_CLIENT, _OPENAI_MODEL_NAME, _GROQ_CLIENT, _GROQ_MODEL_NAME
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

    # ── Per-module: Synthesis ─────────────────────────────────────────────────
    parser.add_argument("--synth-provider", type=str, default=None, choices=PROVIDERS)
    parser.add_argument("--synth-model",    type=str, default=None)
    parser.add_argument("--synth-api-key",  type=str, default=None)

    # ── Per-module: Lean formalization ────────────────────────────────────────
    parser.add_argument("--lean-provider", type=str, default=None, choices=PROVIDERS)
    parser.add_argument("--lean-model",    type=str, default=None)
    parser.add_argument("--lean-api-key",  type=str, default=None)

    args = parser.parse_args()

    # ── Разрешаем конфигурацию для каждого модуля ────────────────────────────
    extract_provider, extract_model, extract_api_key = resolve_module_config(
        module="extract",
        global_provider=args.provider, global_model=args.model, global_api_key=args.api_key,
        module_provider=args.extract_provider, module_model=args.extract_model, module_api_key=args.extract_api_key,
    )
    synth_provider, synth_model, synth_api_key = resolve_module_config(
        module="synth",
        global_provider=args.provider, global_model=args.model, global_api_key=args.api_key,
        module_provider=args.synth_provider, module_model=args.synth_model, module_api_key=args.synth_api_key,
    )

    # Для routing-запросов (extract_keyword, resolve_entities) используем extract-провайдер
    setup_provider(extract_provider, api_key=extract_api_key, model=extract_model)

    from pipeline.export_to_lean import _LLM_PROVIDER
    active_provider_name = (_LLM_PROVIDER or "OLLAMA").upper()
    print(f"[*] Анализ запроса (Провайдер: {active_provider_name}, Модель: {extract_model}, CV: {args.cv_model})...")

    # Step 1: Extract clean keyword
    keyword, canonical = extract_keyword(args.query, extract_model)

    # Step 2: Resolve against existing entities
    available = get_available_entities()
    matches, _ = resolve_entities(args.query, canonical, extract_model, available)

    if matches:
        print(f"\n[+] Найдено {len(matches)} совпадений:")
        for i, m in enumerate(matches, 1):
            print(f"    {i}. [{m['entity_id']}] (confidence: {m['confidence']}) — {m.get('reason', '')}")

        root_ids = [m["entity_id"] for m in matches]
        roots_arg = ",".join(root_ids)
        print(f"\n[*] Сборка result.pdf для: {roots_arg}")
        try:
            subprocess.run([sys.executable, str(GENERATE_SCRIPT), "--roots", roots_arg], check=True)
        except subprocess.CalledProcessError as e:
            print(f"[-] Ошибка генерации: {e}")
        return

    # Step 3: No matches — trigger enrichment
    print(f"\n[!] Сущности не найдены. Запускаю обогащение для: '{canonical}'")
    success = run_enrichment_pipeline(
        canonical,
        extract_provider=extract_provider, extract_api_key=extract_api_key, extract_model=extract_model,
        synth_provider=synth_provider,     synth_api_key=synth_api_key,     synth_model=synth_model,
        lean_provider=args.lean_provider,  lean_api_key=args.lean_api_key,  lean_model=args.lean_model,
        cv_model=args.cv_model,
    )

    if not success:
        print("[-] Конвейер обогащения завершился с ошибкой.")
        sys.exit(1)

    # Step 4: Retry after enrichment
    print(f"\n[*] Повторный поиск в обновленной базе...")
    available = get_available_entities()
    matches, _ = resolve_entities(canonical, canonical, extract_model, available)

    if matches:
        print(f"\n[+] После обогащения найдено {len(matches)} совпадений:")
        for i, m in enumerate(matches, 1):
            print(f"    {i}. [{m['entity_id']}] (confidence: {m['confidence']})")

        root_ids = [m["entity_id"] for m in matches]
        roots_arg = ",".join(root_ids)
        print(f"\n[*] Сборка result.pdf для: {roots_arg}")
        try:
            subprocess.run([sys.executable, str(GENERATE_SCRIPT), "--roots", roots_arg], check=True)
        except subprocess.CalledProcessError as e:
            print(f"[-] Ошибка генерации: {e}")
    else:
        print("[-] Даже после обогащения сущности не были найдены.")






if __name__ == "__main__":
    main()
