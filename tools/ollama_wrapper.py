import argparse
import subprocess
import json
import urllib.request
import re
import sys
import difflib
from pathlib import Path

# Конфигурация путей
PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONTENT_DIR = PROJECT_ROOT / "content"
GENERATE_SCRIPT = PROJECT_ROOT / "tools" / "generate_answer.py"

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

def query_ollama(prompt, model="llama3.1:8b"):
    """Отправляет запрос к локальному API Ollama."""
    url = "http://localhost:11434/api/generate"
    data = {
        "model": model,
        "prompt": prompt,
        "stream": False
    }
    
    try:
        req = urllib.request.Request(url, json.dumps(data).encode('utf-8'), headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req) as response:
            result = json.loads(response.read().decode('utf-8'))
            return result.get('response', '').strip()
    except Exception as e:
        print(f"Ошибка при обращении к Ollama (проверьте, что сервер запущен): {e}")
        sys.exit(1)

def main():
    parser = argparse.ArgumentParser(description="Обертка на базе локальной LLM (Ollama) для запуска конвейера Mathesis.")
    parser.add_argument("query", type=str, help="Входной запрос на естественном языке (например, 'Сгенерируй документ про интеграл Дарбу')")
    parser.add_argument("--model", type=str, default="llama3.1:8b", help="Название модели Ollama (по умолчанию: llama3.1:8b)")
    args = parser.parse_args()

    print(f"[*] Анализ запроса локальной моделью ({args.model})...")

    available_entities = get_available_entities()
    if not available_entities:
        print("[-] Директория content/ пуста или не содержит файлов в нужном формате.")
        sys.exit(1)
        
    entities_list_str = "\n".join(available_entities)

    system_prompt = f"""Ты — интеллектуальный маршрутизатор для конвейера формализации математики (Mathesis).
Твоя задача: найти среди доступных идентификаторов (ID) сущностей тот, который лучше всего соответствует запросу пользователя.

Доступные сущности:
{entities_list_str}

Запрос пользователя: "{args.query}"

В ответ напиши ТОЛЬКО точный ID сущности (например, op-darboux-integral). Не пиши ничего больше, никаких пояснений, точек или кавычек. Если ни один ID не подходит, ответь UNKNOWN.
"""
    
    entity_id = query_ollama(system_prompt, args.model)
    
    # Очистка вывода на случай, если LLM всё-таки добавила мусор
    # Extract only the first valid entity-like string to avoid merging multiple IDs
    match = re.search(r'([a-zA-Z0-9\-]+)', entity_id)
    entity_id = match.group(1) if match else ''
    
    if entity_id != 'UNKNOWN' and entity_id:
        valid_ids = []
        for e in available_entities:
            m = re.search(r"ID: '([^']+)'", e)
            if m: valid_ids.append(m.group(1))
            
        if entity_id not in valid_ids:
            closest = difflib.get_close_matches(entity_id, valid_ids, n=1, cutoff=0.5)
            if closest:
                print(f"[*] Исходный ответ LLM: '{entity_id}'. Исправлено на: '{closest[0]}'")
                entity_id = closest[0]
                
    if entity_id == 'UNKNOWN' or not entity_id or entity_id not in valid_ids:
        print("[-] Локальная LLM не смогла сопоставить запрос с доступными сущностями.")
        sys.exit(1)

    print(f"[+] Распознанный Entity ID: {entity_id}")
    print(f"[*] Запуск конвейера: python tools/generate_answer.py --root {entity_id}\n")

    # Передача аргументов дальше в основной скрипт
    try:
        subprocess.run(["python", str(GENERATE_SCRIPT), "--root", entity_id], check=True)
    except subprocess.CalledProcessError as e:
        print(f"\n[-] Конвейер завершился с ошибкой (Код: {e.returncode})")

if __name__ == "__main__":
    main()
