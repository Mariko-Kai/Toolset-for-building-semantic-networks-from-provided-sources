import os
import re

CONTENT_DIR = r"f:\Universe\Projects\Учебник по матанализу\content"

ENTITY_NAMES = {
    # Operations
    "op-logic-negation": "Отрицание",
    "op-logic-conjunction": "Конъюнкция",
    "op-logic-disjunction": "Дизъюнкция",
    "op-logic-implication": "Импликация",
    "op-logic-equivalence": "Эквивалентность",
    "op-logic-forall": "Квантор всеобщности",
    "op-logic-exists": "Квантор существования",
    "op-logic-exists-unique": "Квантор единственности",

    "op-union": "Объединение множеств",
    "op-intersection": "Пересечение множеств",
    "op-difference": "Разность множеств",
    "op-symmetric-difference": "Симметрическая разность",
    "op-complement": "Дополнение множества",
    "op-cartesian-product": "Декартово произведение",

    "op-composition": "Композиция функций",
    "op-inverse": "Обратная функция",
    "op-image": "Образ множества",
    "op-preimage": "Прообраз множества",
    "op-restriction": "Сужение функции",

    # Objects
    "obj-set": "Множество",
    "obj-empty-set": "Пустое множество",
    "obj-power-set": "Булеан",
    "obj-function": "Функция",
    "obj-graph": "График функции",
    "obj-natural-numbers": "Натуральные числа",

    # Properties
    "prop-subset": "Подмножество",
    "prop-set-equality": "Равенство множеств",
    "prop-de-morgan": "Законы Де Моргана",
    "prop-set-commutativity": "Коммутативность",
    "prop-set-associativity": "Ассоциативность",
    "prop-set-distributivity": "Дистрибутивность",
    "prop-set-duality": "Принцип двойственности",
    "prop-injective": "Инъективность",
    "prop-surjective": "Сюръективность",
    "prop-bijective": "Биективность",
    "prop-equipotent": "Равномощность",
    "prop-countable": "Счетное множество",
    "prop-continuum": "Мощность континуума"
}

def fix_file(filepath):
    with open(filepath, 'r', encoding='utf-8') as f:
        content = f.read()

    new_content = content

    # 1. Replace \section{proof} with \subsection*{Доказательство}
    new_content = re.sub(r'\\section\{proof\}', r'\\subsection*{Доказательство}', new_content)

    # 2. Replace \section{type} \label{entity:ID} with \section{Name} \label{entity:ID}
    # Matches: \section{word} ...whitespace... \label{entity:ID}

    # Regex explanation:
    # \\section\{[a-zA-Z]+\}  -> Matches \section{definition}, \section{property}, etc.
    # \s+                     -> Matches whitespace (newlines) between section and label
    # \\label\{entity:([a-zA-Z0-9-]+)\} -> Matches the label and captures the ID

    pattern = r'\\section\{[a-zA-Z]+\}(\s+)\\label\{entity:([a-zA-Z0-9-]+)\}'

    def replacement(match):
        spacer = match.group(1)
        entity_id = match.group(2)

        if entity_id in ENTITY_NAMES:
            name = ENTITY_NAMES[entity_id]
            return f"\\section{{{name}}}{spacer}\\label{{entity:{entity_id}}}"
        else:
            print(f"Warning: No name for ID {entity_id} in {filepath}")
            return match.group(0) # No change

    new_content = re.sub(pattern, replacement, new_content)

    if new_content != content:
        print(f"Renaming entities in {filepath}")
        with open(filepath, 'w', encoding='utf-8') as f:
            f.write(new_content)

def main():
    for root, dirs, files in os.walk(CONTENT_DIR):
        for file in files:
            if file.endswith(".tex") and file != "master.tex" and file != "mathesis.sty":
                fix_file(os.path.join(root, file))

if __name__ == "__main__":
    main()
