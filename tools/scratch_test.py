import urllib.request
import json
from pipeline.ollama_wrapper import get_available_entities

entities = get_available_entities()
entities_list_str = '\n'.join(entities)

system_prompt = f"""Ты — интеллектуальный маршрутизатор для конвейера формализации математики (Mathesis).
Твоя задача: найти среди доступных идентификаторов (ID) сущностей тот, который лучше всего соответствует запросу пользователя.

Доступные сущности:
{entities_list_str}

Запрос пользователя: "определение интеграла Римана"

В ответ напиши ТОЛЬКО точный ID сущности (например, op-darboux-integral). Не пиши ничего больше, никаких пояснений, точек или кавычек. Если ни один ID не подходит, ответь UNKNOWN.
"""

print("PROMPT:", repr(system_prompt))

url = 'http://localhost:11434/api/generate'
data = {'model': 'llava-phi3:latest', 'prompt': system_prompt, 'stream': False}
req = urllib.request.Request(url, json.dumps(data).encode('utf-8'), headers={'Content-Type': 'application/json'})

with urllib.request.urlopen(req) as response:
    result = json.loads(response.read().decode('utf-8'))
    print('RAW RESPONSE:')
    print(repr(result.get('response', '')))
