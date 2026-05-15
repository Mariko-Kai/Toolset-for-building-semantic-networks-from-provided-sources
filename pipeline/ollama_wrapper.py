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


# ── Ollama Interface ─────────────────────────────────────────────────────────

def query_ollama(prompt, model="llama3.1:8b", json_mode=False):
    """Sends a prompt to local Ollama API."""
    url = "http://localhost:11434/api/generate"
    data = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {"num_ctx": 8192}
    }
    
    # Модели DeepSeek иногда выдают пустые ответы, если жестко форсировать json_mode,
    # поэтому для них мы запрашиваем обычный текст, но просим JSON в системном промпте.
    if json_mode and "deepseek" not in model.lower():
        data["format"] = "json"
        
    try:
        req = urllib.request.Request(url, json.dumps(data).encode('utf-8'),
                                     headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req) as response:
            result = json.loads(response.read().decode('utf-8'))
            resp_text = result.get('response', '').strip()
            
            # 1. Извлекаем и логируем цепочку мыслей (thinking models)
            think_match = re.search(r'<think>(.*?)</think>', resp_text, flags=re.DOTALL)
            if think_match:
                think_content = think_match.group(1).strip()
                print(f"  [LLM Think]: {think_content}")
            resp_text = re.sub(r'<think>.*?</think>', '', resp_text, flags=re.DOTALL).strip()
            
            # 2. Если ожидается JSON, извлекаем его из текста (очистка от markdown-разметки)
            if json_mode:
                # Попытка извлечь JSON из ```json ... ``` блока
                json_block_match = re.search(r'```(?:json)?\s*([\s\S]*?)```', resp_text)
                if json_block_match:
                    resp_text = json_block_match.group(1).strip()
                else:
                    # Резервный поиск скобок JSON
                    brackets_match = re.search(r'(\{.*\}|\[.*\])', resp_text, re.DOTALL)
                    if brackets_match:
                        resp_text = brackets_match.group(1).strip()

            return resp_text
    except Exception as e:
        print(f"[-] Ошибка Ollama (проверьте, что сервер запущен): {e}")
        sys.exit(1)


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
    en_term = query_ollama(prompt, model=model).strip()
    
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
    response = query_ollama(prompt, model, json_mode=True)
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


def translate_term(term, model="deepseek-r1:14b"):
    """Translates a term into EN and RU using LLM."""
    prompt = f"""Translate the mathematical term '{term}' into both English and Russian.
Return strictly JSON:
{{
    "term_ru": "russian translation",
    "term_en": "english translation"
}}"""
    resp = query_ollama(prompt, model=model, json_mode=True)
    try:
        parsed = json.loads(resp)
        return parsed.get("term_ru", term), parsed.get("term_en", term)
    except:
        return term, term


def run_enrichment_pipeline(clean_term, model="deepseek-r1:14b", cv_model="glm-ocr"):
    """Runs the full extraction → alignment → synthesis pipeline."""
    print(f"\n[*] === AUTO-ENRICHMENT: Запускаю конвейер обогащения ===")
    
    term_ru, term_en = translate_term(clean_term, model)
    print(f"[*] Целевой термин (RU): '{term_ru}'")
    print(f"[*] Целевой термин (EN): '{term_en}'")

    env = os.environ.copy()
    env['PYTHONIOENCODING'] = 'utf-8'
    env['PYTHONUNBUFFERED'] = '1'

    steps = [
        ("1/3", "Извлечение из учебников", [sys.executable, str(EXTRACTOR_SCRIPT), f"{term_ru}|{term_en}", "--model", model, "--cv-model", cv_model]),
        ("2/3", "Выравнивание формулировок", [sys.executable, str(ALIGNER_SCRIPT)]),
        ("3/3", "Синтез канонической записи", [sys.executable, str(SYNTHESIZER_SCRIPT), "--model", model, "--cv-model", cv_model]),
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
    parser = argparse.ArgumentParser(description="Mathesis Pipeline — Multi-Result Wrapper")
    parser.add_argument("query", type=str, help="Входной запрос на естественном языке")
    parser.add_argument("--model", type=str, default="deepseek-r1:14b", 
                        help="Модель Ollama (например: llama3.1:8b, deepseek-r1:14b, gemma3:4b)")
    parser.add_argument("--cv-model", type=str, default="glm-ocr", 
                        help="Модель CV/OCR для обработки изображений (например: glm-ocr)")
    args = parser.parse_args()

    print(f"[*] Анализ запроса (LLM: {args.model}, CV: {args.cv_model})...")

    # Step 1: Extract clean keyword
    keyword, canonical = extract_keyword(args.query, args.model)

    # Step 2: Resolve against existing entities
    available = get_available_entities()
    matches, _ = resolve_entities(args.query, canonical, args.model, available)

    if matches:
        # Display all matches
        print(f"\n[+] Найдено {len(matches)} совпадений:")
        for i, m in enumerate(matches, 1):
            print(f"    {i}. [{m['entity_id']}] (confidence: {m['confidence']}) — {m.get('reason', '')}")

        # Build result with ALL matching entity roots
        root_ids = [m["entity_id"] for m in matches]
        roots_arg = ",".join(root_ids)
        print(f"\n[*] Сборка result.pdf для: {roots_arg}")
        try:
            subprocess.run(
                [sys.executable, str(GENERATE_SCRIPT), "--roots", roots_arg],
                check=True
            )
        except subprocess.CalledProcessError as e:
            print(f"[-] Ошибка генерации: {e}")
        return

    # Step 3: No matches — trigger enrichment
    print(f"\n[!] Сущности не найдены. Запускаю обогащение для: '{canonical}'")
    success = run_enrichment_pipeline(canonical, args.model, args.cv_model)

    if not success:
        print("[-] Конвейер обогащения завершился с ошибкой.")
        sys.exit(1)

    # Step 4: Retry after enrichment
    print(f"\n[*] Повторный поиск в обновленной базе...")
    available = get_available_entities()
    matches, _ = resolve_entities(canonical, canonical, args.model, available)

    if matches:
        print(f"\n[+] После обогащения найдено {len(matches)} совпадений:")
        for i, m in enumerate(matches, 1):
            print(f"    {i}. [{m['entity_id']}] (confidence: {m['confidence']})")

        root_ids = [m["entity_id"] for m in matches]
        roots_arg = ",".join(root_ids)
        print(f"\n[*] Сборка result.pdf для: {roots_arg}")
        try:
            subprocess.run(
                [sys.executable, str(GENERATE_SCRIPT), "--roots", roots_arg],
                check=True
            )
        except subprocess.CalledProcessError as e:
            print(f"[-] Ошибка генерации: {e}")
    else:
        print("[-] Даже после обогащения сущности не были найдены.")


if __name__ == "__main__":
    main()