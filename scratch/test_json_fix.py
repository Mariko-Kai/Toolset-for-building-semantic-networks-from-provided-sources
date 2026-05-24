import sys, re, json
sys.stdout.reconfigure(encoding='utf-8')
with open('pipeline/generate_answer.py', 'r', encoding='utf-8') as f:
    lines = f.readlines()

# Find line 213 (0-indexed = 212)
line = lines[212]
print('Line 213 raw:', repr(line))

# The synthesize_entity_details function - test it end-to-end
sys.path.insert(0, 'f:/Universe/Projects/Учебник по матанализу')

# Simulate what synthesize_entity_details does with JSON parsing
response = r'{"name_ru": "Инфимум", "name_en": "Infimum", "desc_ru": "Инфимум $\inf A$ — наибольшая нижняя грань $A \subseteq \mathbb{R}$.", "desc_en": "The infimum $\inf A$ is the greatest lower bound of $A \subseteq \mathbb{R}$."}'

response = re.sub(r'^```json\s*', '', response.strip(), flags=re.MULTILINE)
response = re.sub(r'^```\s*$', '', response.strip(), flags=re.MULTILINE).strip()

match = re.search(r'(\{.*\})', response, re.DOTALL)
if match:
    response = match.group(1)

# This is the exact pattern from line 213 in generate_answer.py
response_fixed = re.sub(r'\\(?!["\\/bfnrtu])', r'\\\\', response)

print('\nFixed response:', repr(response_fixed[:100]))
try:
    res = json.loads(response_fixed)
    print('JSON OK:', res['name_ru'], '|', res['name_en'])
    print('desc_ru:', res['desc_ru'][:60])
except Exception as e:
    print('JSON FAIL:', e)
