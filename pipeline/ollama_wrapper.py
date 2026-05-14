import argparse
import subprocess
import os
import json
import urllib.request
import re
import sys
import difflib
from pathlib import Path

# Конфигурация путей
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONTENT_DIR = PROJECT_ROOT / "content"
GENERATE_SCRIPT = PROJECT_ROOT / "pipeline" / "generate_answer.py"
EXTRACTOR_SCRIPT = PROJECT_ROOT / "pipeline" / "ensemble_extractor.py"
ALIGNER_SCRIPT = PROJECT_ROOT / "pipeline" / "entity_aligner.py"
SYNTHESIZER_SCRIPT = PROJECT_ROOT / "pipeline" / "canonical_synthesizer.py"

def get_available_entities():
    """Сканирует директорию content и собирает доступные entity-id и их названия."""
    entities = []
    if not CONTENT_DIR.exists():
        return entities
        
    for filepath in CONTENT_DIR.rglob("*.tex"):
        match = re.search(r'\[([^\]]+)\]\.tex$', filepath.name)
        if match:
            entity_id = match.group(1)
            title = filepath.name.replace(f" [{entity_id}].tex", "")
            entities.append(f"- Название: '{title}', ID: '{entity_id}'")
    return entities

def query_ollama(prompt, model="llama3.1:8b", json_mode=False):
    """Отправляет запрос к локальному API Ollama."""
    url = "http://localhost:11434/api/generate"
    data = {
        "model": model,
        "prompt": prompt,
        "stream": False
    }
    if json_mode:
        data["format"] = "json"
    
    try:
        req = urllib.request.Request(url, json.dumps(data).encode('utf-8'), headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req) as response:
            result = json.loads(response.read().decode('utf-8'))
            return result.get('response', '').strip()
    except Exception as e:
        print(f"Ошибка при обращении к Ollama (проверьте, что сервер запущен): {e}")
        sys.exit(1)

def run_enrichment_pipeline(query):
    """
    Auto-Fallback: запускает полный конвейер извлечения, выравнивания и синтеза
    для автоматического обогащения базы знаний (content/).
    """
    print(f"\n[*] === AUTO-FALLBACK: Сущность не найдена. Запускаю конвейер обогащения ===")
    print(f"[*] Запрос: '{query}'")
    
    env = os.environ.copy()
    env['PYTHONIOENCODING'] = 'utf-8'
    
    # Шаг 1: Ensemble Extraction
    print(f"\n[1/3] Извлечение из учебников (ensemble_extractor.py)...")
    try:
        env['PYTHONUNBUFFERED'] = '1'
        subprocess.run(
            ["python", str(EXTRACTOR_SCRIPT), query],
            env=env, check=True
        )
    except subprocess.CalledProcessError as e:
        print(f"[-] Ошибка извлечения (Код: {e.returncode})")
        return False
    except Exception as e:
        print(f"[-] Не удалось запустить extractor: {e}")
        return False
    
    # Шаг 2: Entity Alignment
    print(f"[2/3] Выравнивание формулировок (entity_aligner.py)...")
    try:
        subprocess.run(
            ["python", str(ALIGNER_SCRIPT)],
            env=env, check=True
        )
    except subprocess.CalledProcessError as e:
        print(f"[-] Ошибка выравнивания (Код: {e.returncode})")
        return False
    except Exception as e:
        print(f"[-] Не удалось запустить aligner: {e}")
        return False
    
    # Шаг 3: Canonical Synthesis
    print(f"[3/3] Синтез канонической записи (canonical_synthesizer.py)...")
    try:
        subprocess.run(
            ["python", str(SYNTHESIZER_SCRIPT)],
            env=env, check=True
        )
    except subprocess.CalledProcessError as e:
        print(f"[-] Ошибка синтеза (Код: {e.returncode})")
        return False
    except Exception as e:
        print(f"[-] Не удалось запустить synthesizer: {e}")
        return False
    
    print(f"\n[+] Конвейер обогащения завершен успешно!")
    return True

def resolve_entity(query, model, available_entities):
    """Пытается сопоставить запрос с доступными сущностями через LLM."""
    if not available_entities:
        return None, []
    
    entities_list_str = "\n".join(available_entities)
    
    system_prompt = f"""Ты — интеллектуальный маршрутизатор для конвейера формализации математики (Mathesis).
Твоя задача: выделить ключевое математическое понятие из запроса пользователя и найти среди доступных идентификаторов (ID) тот, который ему соответствует.

Доступные сущности (Название и ID):
{entities_list_str}

Запрос пользователя: "{query}"

ПРАВИЛА:
1. Если подходящей сущности нет в списке, используй ID "UNKNOWN".
2. Не угадывай и не подставляй теоремы, если они не совпадают по смыслу.
3. Верни результат строго в формате JSON, содержащий два поля: "keyword" (выделенное понятие) и "entity_id" (найденный ID).

Пример вывода:
{{
  "keyword": "предел последовательности",
  "entity_id": "lim-sequential"
}}
"""
    
    response_text = query_ollama(system_prompt, model, json_mode=True)
    
    try:
        parsed = json.loads(response_text)
        keyword = parsed.get("keyword", "")
        entity_id = parsed.get("entity_id", "UNKNOWN")
        print(f"[*] Выделенное ключевое слово: '{keyword}'")
    except json.JSONDecodeError:
        print("[-] Ошибка парсинга JSON от LLM. Использую fallback.")
        match = re.search(r'([a-zA-Z0-9\-]+)', response_text)
        entity_id = match.group(1) if match else 'UNKNOWN'

    
    # Собираем валидные ID
    valid_ids = []
    for e in available_entities:
        m = re.search(r"ID: '([^']+)'", e)
        if m:
            valid_ids.append(m.group(1))
    
    if entity_id and entity_id != 'UNKNOWN':
        if entity_id not in valid_ids:
            # Порог 0.9 — разрешаем только мелкие опечатки
            closest = difflib.get_close_matches(entity_id, valid_ids, n=1, cutoff=0.9)
            if closest:
                print(f"[*] Исправление опечатки LLM: '{entity_id}' -> '{closest[0]}'")
                entity_id = closest[0]
            else:
                print(f"[!] LLM выдала несуществующий ID '{entity_id}', который не является опечаткой. Сброс в UNKNOWN.")
                entity_id = 'UNKNOWN'
    
    if entity_id == 'UNKNOWN' or not entity_id or entity_id not in valid_ids:
        return None, valid_ids
    
    return entity_id, valid_ids

def main():
    parser = argparse.ArgumentParser(description="Обертка на базе локальной LLM (Ollama) для запуска конвейера Mathesis.")
    parser.add_argument("query", type=str, help="Входной запрос на естественном языке (например, 'Сгенерируй документ про интеграл Дарбу')")
    parser.add_argument("--model", type=str, default="llama3.1:8b", help="Название модели Ollama (по умолчанию: llama3.1:8b)")
    args = parser.parse_args()

    print(f"[*] Анализ запроса локальной моделью ({args.model})...")

    # === Попытка 1: поиск среди существующих сущностей ===
    available_entities = get_available_entities()
    entity_id, valid_ids = resolve_entity(args.query, args.model, available_entities)
    
    if entity_id:
        print(f"[+] Распознанный Entity ID: {entity_id}")
        print(f"[*] Запуск конвейера: python pipeline/generate_answer.py --root {entity_id}\n")
        try:
            subprocess.run(["python", str(GENERATE_SCRIPT), "--root", entity_id], check=True)
        except subprocess.CalledProcessError as e:
            print(f"\n[-] Конвейер завершился с ошибкой (Код: {e.returncode})")
        return

    # === Auto-Fallback: сущность не найдена — запускаем конвейер обогащения ===
    print(f"[!] Сущность не найдена в базе. Запускаю автоматическое обогащение...")
    
    success = run_enrichment_pipeline(args.query)
    
    if not success:
        print("[-] Конвейер обогащения завершился с ошибкой.")
        sys.exit(1)
    
    # === Попытка 2: повторный поиск после обогащения ===
    print(f"\n[*] Повторный поиск после обогащения базы...")
    available_entities = get_available_entities()
    entity_id, valid_ids = resolve_entity(args.query, args.model, available_entities)
    
    if entity_id:
        print(f"[+] Распознанный Entity ID: {entity_id}")
        print(f"[*] Запуск конвейера: python pipeline/generate_answer.py --root {entity_id}\n")
        try:
            subprocess.run(["python", str(GENERATE_SCRIPT), "--root", entity_id], check=True)
        except subprocess.CalledProcessError as e:
            print(f"\n[-] Конвейер завершился с ошибкой (Код: {e.returncode})")
    else:
        print("[-] Даже после обогащения сущность не была найдена. Возможно, запрос выходит за рамки текущего покрытия учебников.")
        sys.exit(1)

if __name__ == "__main__":
    main()
