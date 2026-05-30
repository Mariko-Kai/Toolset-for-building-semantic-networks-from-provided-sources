import glob
import re

ru_map = {
    'Axiom of Choice': 'Аксиома выбора',
    'Axiom of Extensionality': 'Аксиома объемности',
    'Axiom of Infinity': 'Аксиома бесконечности',
    'Axiom of Pairing': 'Аксиома пары',
    'Axiom of Power Set': 'Аксиома булеана',
    'Axiom of Regularity': 'Аксиома регулярности',
    'Axiom of Replacement': 'Аксиома подстановки',
    'Axiom of Specification': 'Аксиома выделения',
    'Axiom of Union': 'Аксиома объединения',
    'Completeness Axiom': 'Аксиома полноты',
    'Completeness': 'Аксиома полноты',
    'Modus Ponens': 'Modus Ponens',
    'Distribution': 'Дистрибутивность',
    'Specialization': 'Специализация',
    'Universal Instantiation': 'Универсальная инстанциация'
}

for path in glob.glob('content/foundations/*.tex'):
    with open(path, 'r', encoding='utf-8') as f:
        text = f.read()

    if '% defined-in:' not in text:
        text = re.sub(r'(% entity-type:.*?\n)', r'\1% defined-in: vereshchagin-shen\n', text)

    match = re.search(r'\\section\{([^}]+)\}', text)
    if match:
        en_name = match.group(1)
        if en_name in ru_map and ru_map[en_name] not in en_name:
            new_title = f"{ru_map[en_name]} ({en_name})"
            text = text.replace(f'\\section{{{en_name}}}', f'\\section{{{new_title}}}')

    with open(path, 'w', encoding='utf-8') as f:
        f.write(text)
print('ZFC updated')
