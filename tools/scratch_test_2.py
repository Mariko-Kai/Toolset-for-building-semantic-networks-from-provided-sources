import urllib.request, json
from pipeline.ollama_wrapper import get_available_entities
import difflib
import re

entities = get_available_entities()
entities_list_str = '\n'.join(entities)

system_prompt = f'''Ты — интеллектуальный маршрутизатор для конвейера формализации математики (Mathesis).
Твоя задача: найти среди доступных идентификаторов (ID) сущностей тот, который лучше всего соответствует запросу пользователя.

Доступные сущности:
{entities_list_str}

Запрос пользователя: "Что такое основной критерий интегрируемости?"

В ответ напиши ТОЛЬКО точный ID сущности (например, op-darboux-integral). Не пиши ничего больше, никаких пояснений, точек или кавычек. Если ни один ID не подходит, ответь UNKNOWN.
'''

url = 'http://localhost:11434/api/generate'
data = {'model': 'llama3.1:8b', 'prompt': system_prompt, 'stream': False}
req = urllib.request.Request(url, json.dumps(data).encode('utf-8'), headers={'Content-Type': 'application/json'})

with urllib.request.urlopen(req) as response:
    result = json.loads(response.read().decode('utf-8'))
    entity_id = result.get('response', '').strip()
    match = re.search(r'([a-zA-Z0-9\-]+)', entity_id)
    parsed_id = match.group(1) if match else ''
    print('Parsed ID:', parsed_id)
    
    valid_ids = []
    for e in entities:
        m = re.search(r"ID: '([^']+)'", e)
        if m: valid_ids.append(m.group(1))
        
    if parsed_id not in valid_ids and parsed_id != 'UNKNOWN':
        closest = difflib.get_close_matches(parsed_id, valid_ids, n=1, cutoff=0.5)
        if closest:
            print(f'Did you mean: {closest[0]}?')
        else:
            print('No close matches found.')
