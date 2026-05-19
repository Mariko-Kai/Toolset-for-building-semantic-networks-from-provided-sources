import os
import re
import glob
import sys
import numpy as np
import logging
import ollama  # Оставляем для локальных эмбеддингов
from pathlib import Path

# Добавляем корень проекта в пути импорта для совместимости
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

# Импортируем общую конфигурацию и функции запросов Mathesis
from pipeline.config import resolve_module_config
from pipeline.export_to_lean import setup_provider, setup_lean_provider, query_llm

class MathesisSemanticMerger:
    def __init__(self, content_dir="content", db_path="mathesis.db", cli_args=None):
        self.content_dir = content_dir
        self.db_path = db_path
        
        # Настройка логирования
        self.setup_logging()
        
        # Разрешаем конфигурацию для классификатора (модуль extract)
        self.classifier_provider, self.classifier_model, self.classifier_api_key = resolve_module_config(
            module="extract",
            global_provider=getattr(cli_args, 'provider', None),
            global_model=getattr(cli_args, 'model', None),
            global_api_key=getattr(cli_args, 'api_key', None),
            module_provider=getattr(cli_args, 'extract_provider', None),
            module_model=getattr(cli_args, 'extract_model', None),
            module_api_key=getattr(cli_args, 'extract_api_key', None)
        )
        
        # Разрешаем конфигурацию для Lean-валидации (модуль lean)
        self.lean_provider, self.lean_model, self.lean_api_key = resolve_module_config(
            module="lean",
            global_provider=getattr(cli_args, 'provider', None),
            global_model=getattr(cli_args, 'model', None),
            global_api_key=getattr(cli_args, 'api_key', None),
            module_provider=getattr(cli_args, 'lean_provider', None),
            module_model=getattr(cli_args, 'lean_model', None),
            module_api_key=getattr(cli_args, 'lean_api_key', None)
        )
        
        # Если модель для lean не задана явно в CLI, по умолчанию используем "goedel-prover" с провайдером "ollama"
        has_explicit_lean_model = cli_args and (getattr(cli_args, 'lean_model', None) or getattr(cli_args, 'model', None))
        if not has_explicit_lean_model:
            self.lean_model = "goedel-prover"
            self.lean_provider = "ollama"

        
        # Модель для эмбеддингов
        self.embed_model = "nomic-embed-text:latest"
        
        # Допустимые роли для семантического сравнения
        self.valid_roles = ['obj', 'prop', 'oper', 'thm', 'lem']
        
        # Инициализируем провайдеры в глобальном окружении Mathesis
        self.logger.info(f"Инициализация классификатора (Провайдер: {self.classifier_provider.upper()}, Модель: {self.classifier_model})")
        setup_provider(self.classifier_provider, api_key=self.classifier_api_key, model=self.classifier_model)
        
        self.logger.info(f"Инициализация Lean-валидатора (Провайдер: {self.lean_provider.upper()}, Модель: {self.lean_model})")
        setup_lean_provider(self.lean_provider, api_key=self.lean_api_key, model=self.lean_model)

    def setup_logging(self):
        """Настройка двух уровней логирования: лаконичный консольный и детальный в файл"""
        os.makedirs("logs", exist_ok=True)
        log_file = "logs/postprocess_equivalence.log"
        
        # Создаем логгер
        self.logger = logging.getLogger("MathesisSemanticMerger")
        self.logger.setLevel(logging.DEBUG)
        
        # Очищаем старые обработчики, если они есть (например, при повторном импорте)
        if self.logger.hasHandlers():
            self.logger.handlers.clear()
            
        # 1. Детальный лог в файл (DEBUG уровень)
        fh = logging.FileHandler(log_file, encoding='utf-8', mode='w')
        fh.setLevel(logging.DEBUG)
        fh_formatter = logging.Formatter('%(asctime)s [%(levelname)s] %(message)s')
        fh.setFormatter(fh_formatter)
        self.logger.addHandler(fh)
        
        # 2. Лаконичный лог в консоль (INFO уровень)
        sh = logging.StreamHandler()
        sh.setLevel(logging.INFO)
        sh_formatter = logging.Formatter('[*] %(message)s')
        sh.setFormatter(sh_formatter)
        self.logger.addHandler(sh)

    def extract_formulation(self, content):
        """Эвристика извлечения значимого текста из LaTeX"""
        # Ищет тело окружения (object, operation, property, axiom, theorem, lemma, etc.)
        form_match = re.search(
            r'\\begin\{(object|operation|property|axiom|theorem|lemma|corollary|terminal)\}(.*?)\\end\{\1\}',
            content,
            re.DOTALL | re.IGNORECASE
        )
        if form_match:
            # Очищаем от возможных аргументов окружения в начале
            body = form_match.group(2).strip()
            body_clean = re.sub(r'^\[[^\]]*\]', '', body).strip()
            return body_clean
        return content[:500]

    def get_true_role(self, entity_id, formulation):
        """Определяет истинную роль сущности. Теоремы пропускают проверку."""
        # 1. Если префикс уже валидный, возвращаем его мгновенно
        match = re.search(r"^([a-z]+)-", entity_id)
        if match:
            role = match.group(1)
            if role == "op":
                return "oper"
            if role in self.valid_roles or role in ['axm', 'term']:
                return role

        if entity_id.startswith("thm-"):
            return "thm"
            
        prompt = f"""
        Ты математический классификатор. Твоя задача — определить роль математического утверждения.
        Доступные роли:
        - obj (Объект/Определение)
        - prop (Свойство)
        - oper (Операция)
        - thm (Теорема)
        - axm (Аксиома)
        - lem (Лемма)
        
        Утверждение: {formulation}
        
        В ответе напиши ТОЛЬКО ОДНО слово — аббревиатуру роли из списка выше. Без точек и пояснений.
        """
        
        try:
            # Делаем запрос через централизованный query_llm Mathesis
            reply = query_llm(
                prompt=prompt,
                model=self.classifier_model,
                provider=self.classifier_provider
            ).strip().lower()
            
            for role in self.valid_roles + ['axm', 'term']:
                if role in reply:
                    return role
            
            # Fallback к префиксу из текущего ID
            match = re.search(r"^([a-z]+)-", entity_id)
            return match.group(1) if match and match.group(1) in self.valid_roles else "obj"
        except Exception as e:
            self.logger.error(f"Ошибка LLM классификации для {entity_id}: {e}")
            match = re.search(r"^([a-z]+)-", entity_id)
            return match.group(1) if match and match.group(1) in self.valid_roles else "obj"

    def load_and_classify_entities(self):
        """Загрузка контента и определение истинных ролей с выделением чистого ID"""
        entities = []
        filepaths = glob.glob(os.path.join(self.content_dir, '**', '*.tex'), recursive=True)
        
        self.logger.info(f"Загрузка и классификация ролей для {len(filepaths)} файлов контента...")
        for filepath in filepaths:
            filename_base = os.path.splitext(os.path.basename(filepath))[0]
            
            # Извлекаем ID из квадратных скобок: "Human Name [entity-id]" -> "entity-id"
            id_match = re.search(r'\[(.*?)\]', filename_base)
            if not id_match:
                self.logger.warning(f"Файл {filepath} пропущен: отсутствует квадратные скобки ID в названии.")
                continue
            entity_id = id_match.group(1).strip()
            
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
                
            formulation = self.extract_formulation(content)
            true_role = self.get_true_role(entity_id, formulation)
            
            # Исключаем аксиомы (axm) и термы (term/terminal) из проверки дубликатов
            if true_role in ['axm', 'term', 'terminal']:
                self.logger.debug(f"[{entity_id}] Классифицирован как {true_role}. Исключен из проверки дубликатов.")
                continue
            
            entities.append({
                "path": filepath,
                "filename_base": filename_base,
                "id": entity_id,
                "formulation": formulation,
                "content": content,
                "true_role": true_role
            })
            self.logger.debug(f"[{entity_id}] ({filename_base}) классифицирован как роль: {true_role}")
            
        self.logger.info(f"Успешно загружено {len(entities)} семантически значимых сущностей (аксиомы и термы отфильтрованы).")
        return entities

    def get_embedding(self, text):
        try:
            self.logger.debug(f"Запрос эмбеддинга для текста: {text[:100]}...")
            response = ollama.embeddings(model=self.embed_model, prompt=text)
            return response['embedding']
        except Exception as e:
            self.logger.error(f"Ошибка запроса эмбеддинга: {e}")
            return [0.0] * 768

    def cosine_similarity(self, v1, v2):
        norm1 = np.linalg.norm(v1)
        norm2 = np.linalg.norm(v2)
        if norm1 == 0 or norm2 == 0:
            return 0.0
        return np.dot(v1, v2) / (norm1 * norm2)

    def find_lean_file_by_id(self, entity_id):
        """Ищет .lean файл в lean_validator/Validated или в контенте."""
        # 1. Сначала ищем в lean_validator/Validated (где хранятся валидированные файлы в формате {entity_id}.lean)
        validated_path = os.path.join("lean_validator", "Validated", f"{entity_id}.lean")
        if os.path.exists(validated_path):
            return validated_path
            
        # 2. Если не нашли, ищем по точному вхождению ID в квадратных скобках
        pattern = f"*{entity_id}*.lean"
        matches = glob.glob(os.path.join(self.content_dir, '**', pattern), recursive=True)
        for match in matches:
            if f"[{entity_id}]" in os.path.basename(match):
                return match
        return None

    def extract_lean_statement(self, lean_filepath):
        """Извлекает строгую формулировку конкретной сущности, соответствующей имени файла."""
        # Получаем ожидаемое имя сущности в Lean (например, op_derivative)
        basename = os.path.splitext(os.path.basename(lean_filepath))[0]
        # Если это файл эквивалентности, или вспомогательный файл, имя может не соответствовать
        # Но для обычных сущностей оно соответствует:
        target_name = basename.replace('-', '_')
        
        with open(lean_filepath, 'r', encoding='utf-8') as f:
            lean_content = f.read()
            
        # Убираем комментарии и импорты
        lines = []
        for line in lean_content.splitlines():
            if line.strip().startswith(('import ', 'open ', 'set_option ')):
                continue
            lines.append(line)
        content_clean = "\n".join(lines).strip()
        
        # Ищем блок, который начинается с объявления нашей target_name
        # Шаблон ищет слово def/theorem/lemma/abbrev/structure/class, за которым идет target_name
        pattern = rf'\b(def|theorem|lemma|abbrev|structure|class)\s+{re.escape(target_name)}\b'
        match = re.search(pattern, content_clean)
        
        if match:
            start_idx = match.start()
            # Нам нужно найти конец этого блока.
            # Блок обычно заканчивается перед следующим объявлением def/theorem/lemma/abbrev/structure/class.
            rest = content_clean[start_idx:]
            next_decl = re.search(r'\n\s*\b(def|theorem|lemma|abbrev|structure|class)\b', rest[1:])
            if next_decl:
                # Отрезаем до следующего объявления
                statement_block = rest[:next_decl.start() + 1].strip()
            else:
                statement_block = rest.strip()
                
            # Если это теорема/лемма, отрезаем доказательство (после := или := by)
            keyword = match.group(1)
            if keyword in ('theorem', 'lemma'):
                match_proof = re.search(r'(.*?)(?::=|:= by)', statement_block, re.DOTALL)
                if match_proof:
                    statement = match_proof.group(1).strip()
                    if statement.endswith('by'):
                        statement = statement[:-2].strip()
                    if statement.endswith(':='):
                        statement = statement[:-2].strip()
                    return statement
            return statement_block
            
        # Резервный вариант: старая логика
        if re.search(r'\b(def|abbrev|structure|class)\b', content_clean):
            return content_clean
            
        match_proof = re.search(r'((?:theorem|lemma)\s+.*?(?::=|:= by))', content_clean, re.DOTALL)
        if match_proof:
            statement = match_proof.group(1).strip()
            if statement.endswith('by'):
                statement = statement[:-2].strip()
            if statement.endswith(':='):
                statement = statement[:-2].strip()
            return statement
            
        return content_clean

    def get_lean_name(self, statement):
        """Извлекает имя теоремы или определения из Lean-формулировки."""
        match = re.search(r'(?:theorem|lemma|def|abbrev|structure|class)\s+([a-zA-Z0-9_’\']+)', statement)
        return match.group(1).strip() if match else "Name"

    def determine_operator(self, entity_id):
        """Эвристика определения оператора эквивалентности по префиксу ID."""
        if entity_id.startswith(('thm-', 'lem-', 'prop-')):
            return "↔"
        return "="

    def ask_goedel_for_lean(self, e1, e2):
        """Lean 4 validation via Goedel (Adapted for formal Lean-based verification)"""
        # 1. Поиск .lean файлов
        path1 = self.find_lean_file_by_id(e1['id'])
        path2 = self.find_lean_file_by_id(e2['id'])
        
        # Если хотя бы у одного нет .lean файла, мы не можем провести формальную Lean-верификацию.
        if not path1 or not path2:
            self.logger.warning(f"Не найдены .lean файлы для пары {e1['id']} и {e2['id']}. Формальная проверка невозможна.")
            return False, None
            
        stmt1 = self.extract_lean_statement(path1)
        stmt2 = self.extract_lean_statement(path2)
        
        name1 = self.get_lean_name(stmt1)
        name2 = self.get_lean_name(stmt2)
        
        prompt = f"""You are Goedel-Prover, an expert theorem-proving AI for Lean 4.
Your objective is to mathematically prove the equivalence of two previously formalized statements.

Statement 1 (defining '{name1}'):
```lean
{stmt1}
```

Statement 2 (defining '{name2}'):
```lean
{stmt2}
```

Task:
Provide a cohesive Lean 4 code block enclosed in ```lean ... ```.
Formulate a new theorem asserting the equivalence of '{name1}' and '{name2}'.
Choose an appropriate name for the theorem, for example: `equiv_{e1['id'].replace('-','_')}_{e2['id'].replace('-','_')}`.
Generate the tactical proof. Use powerful Mathlib tactics like `aesop`, `tauto`, `ext`, or `simp`.
If the equivalence requires complex intermediate lemmas not present in the context, gracefully close the goal with `sorry`.

Do not provide conversational text. Output ONLY the valid Lean 4 code block.
"""
        self.logger.debug(f"Запрос Goedel Lean валидации для {e1['id']} <-> {e2['id']}...")
        
        # Подготовка директории и файла для логирования Goedel
        goedel_log_dir = os.path.join("logs", "postprocess_prover")
        os.makedirs(goedel_log_dir, exist_ok=True)
        log_filepath = os.path.join(goedel_log_dir, f"{e1['id']}_vs_{e2['id']}.txt")
        
        try:
            # Делаем запрос через централизованный query_llm Mathesis
            reply = query_llm(
                prompt=prompt,
                model=self.lean_model,
                provider=self.lean_provider
            )
            
            # Логируем успешный запрос и ответ
            with open(log_filepath, 'w', encoding='utf-8') as lf:
                lf.write(f"=== PROMPT ===\n{prompt}\n\n=== REPLY ===\n{reply}\n")
            
            lean_matches = re.findall(r'```lean(.*?)```', reply, re.DOTALL)
            if lean_matches:
                best_code = None
                for match in lean_matches:
                    code_candidate = match.strip()
                    if "sorry" not in code_candidate:
                        best_code = code_candidate
                        break
                    elif best_code is None:
                        best_code = code_candidate
                
                if best_code and "sorry" not in best_code:
                    self.logger.debug(f"Goedel подтвердил эквивалентность {e1['id']} <-> {e2['id']}.")
                    return True, best_code
                    
        except Exception as e:
            try:
                with open(log_filepath, 'w', encoding='utf-8') as lf:
                    lf.write(f"=== PROMPT ===\n{prompt}\n\n=== EXCEPTION ===\n{e}\n")
            except Exception:
                pass
            self.logger.error(f"Ошибка Lean валидации Goedel: {e}")
            
        self.logger.debug(f"Goedel отклонил эквивалентность {e1['id']} <-> {e2['id']} или произошла ошибка.")
        return False, None

    def enforce_naming_design(self, original_id, true_role):
        """Создает правильное имя с учетом перерассчитанной роли"""
        # Удаляем старый префикс типа obj-, prop- и т.д.
        clean_id = re.sub(r'^(obj|prop|oper|thm|axm|lem|term)-', '', original_id)
        clean_id = re.sub(r'[^a-zA-Z0-9-]', '', clean_id).strip().lower()
        return f"{true_role}-{clean_id}"

    def is_naming_perfect(self, entity_id, true_role):
        """Проверяет, идеально ли имя (правильный префикс + валидные символы)"""
        pattern = re.compile(f"^{true_role}-[a-z0-9-]+$")
        return bool(pattern.match(entity_id))

    def replace_references(self, old_ids, new_id):
        """Массовый рефакторинг графа по чистым ID"""
        self.logger.debug(f"Массовый рефакторинг упоминаний в LaTeX: замена {old_ids} -> {new_id}...")
        for filepath in glob.glob(os.path.join(self.content_dir, '**', '*.tex'), recursive=True):
            with open(filepath, 'r', encoding='utf-8') as f:
                text = f.read()
            modified = False
            for old_id in old_ids:
                if old_id in text and old_id != new_id:
                    # Заменяем чистые ID во всех вхождениях
                    text = text.replace(old_id, new_id)
                    modified = True
            if modified:
                self.logger.debug(f"  Успешно обновлены ссылки в файле: {filepath}")
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(text)

    def cleanup_database(self, e1_id, e2_id):
        """Очищает базу данных mathesis_index.db от удаленной сущности e2_id и перенаправляет связи на e1_id."""
        db_path = os.path.join(PROJECT_ROOT, "mathesis_index.db")
        if not os.path.exists(db_path):
            self.logger.warning(f"База данных {db_path} не найдена. Пропуск очистки БД.")
            return
            
        try:
            import sqlite3
            conn = sqlite3.connect(db_path)
            cursor = conn.cursor()
            
            # 1. Удаляем e2_id из entities
            cursor.execute("DELETE FROM entities WHERE entity_id = ?", (e2_id,))
            
            # 2. Удаляем e2_id из formulation_sources
            cursor.execute("DELETE FROM formulation_sources WHERE entity_id = ?", (e2_id,))
            
            # 3. Перенаправляем зависимости в entity_dependency
            cursor.execute("UPDATE OR IGNORE entity_dependency SET source_id = ? WHERE source_id = ?", (e1_id, e2_id))
            cursor.execute("UPDATE OR IGNORE entity_dependency SET target_id = ? WHERE target_id = ?", (e1_id, e2_id))
            
            # 4. Удаляем любые остаточные битые зависимости с e2_id
            cursor.execute("DELETE FROM entity_dependency WHERE source_id = ? OR target_id = ?", (e2_id, e2_id))
            
            conn.commit()
            conn.close()
            self.logger.info(f"[*] База данных успешно очищена для пары: {e1_id} <-> {e2_id}.")
        except Exception as e:
            self.logger.error(f"Ошибка при очистке базы данных: {e}")

    def remove_entity_from_successful_entities(self, entity_id):
        """Удаляет блок кода сущности из SuccessfulEntities.lean."""
        filepath = os.path.join("lean_validator", "SuccessfulEntities.lean")
        if not os.path.exists(filepath):
            self.logger.warning(f"Файл {filepath} не найден. Пропуск очистки SuccessfulEntities.")
            return
            
        try:
            with open(filepath, 'r', encoding='utf-8') as f:
                content = f.read()
            
            blocks = content.split("-- Entity: ")
            new_blocks = [blocks[0]]
            removed_count = 0
            
            for block in blocks[1:]:
                lines = block.splitlines()
                if not lines:
                    new_blocks.append("-- Entity: " + block)
                    continue
                header = lines[0]
                block_id = header.split('|')[0].strip()
                if block_id == entity_id:
                    removed_count += 1
                    continue
                new_blocks.append("-- Entity: " + block)
                
            if removed_count > 0:
                new_content = "".join(new_blocks)
                with open(filepath, 'w', encoding='utf-8') as f:
                    f.write(new_content)
                self.logger.info(f"[*] Стерта запись '{entity_id}' из SuccessfulEntities.lean.")
        except Exception as e:
            self.logger.error(f"Ошибка при обновлении SuccessfulEntities.lean: {e}")

    def actualize_lean_files(self):
        """Сканирует Validated/ и SuccessfulEntities.lean и удаляет сиротские сущности, которых больше нет в content."""
        self.logger.info("Запуск актуализации (garbage collection) Lean файлов...")
        
        # Шаг 1: Загружаем все активные ID из content
        active_ids = set()
        for filepath in glob.glob(os.path.join(self.content_dir, '**', '*.tex'), recursive=True):
            filename_base = os.path.splitext(os.path.basename(filepath))[0]
            id_match = re.search(r'\[(.*?)\]', filename_base)
            if id_match:
                active_ids.add(id_match.group(1).strip())
                
        self.logger.info(f"Найдено {len(active_ids)} активных ID сущностей в LaTeX контенте.")
        
        # Шаг 2: Сканируем Validated/ и удаляем сиротские файлы
        validated_dir = os.path.join("lean_validator", "Validated")
        if os.path.exists(validated_dir):
            lean_files = glob.glob(os.path.join(validated_dir, '*.lean'))
            for filepath in lean_files:
                basename = os.path.splitext(os.path.basename(filepath))[0]
                
                # Если это файл эквивалентности (equiv_{id1}_{id2}):
                if basename.startswith("equiv_"):
                    active_ids_underscored = [aid.replace('-', '_') for aid in active_ids]
                    matched_active_ids = [aid for aid in active_ids_underscored if aid in basename]
                    if len(matched_active_ids) < 2:
                        self.logger.info(f"[*] Удаление сиротского файла эквивалентности: {filepath}")
                        try:
                            os.remove(filepath)
                        except Exception as e:
                            self.logger.error(f"Не удалось удалить файл {filepath}: {e}")
                else:
                    # Это обычный файл сущности {entity_id}.lean
                    if basename not in active_ids:
                        self.logger.info(f"[*] Удаление сиротского Lean файла: {filepath}")
                        try:
                            os.remove(filepath)
                        except Exception as e:
                            self.logger.error(f"Не удалось удалить файл {filepath}: {e}")
                            
        # Шаг 3: Удаляем сиротские записи из SuccessfulEntities.lean
        filepath = os.path.join("lean_validator", "SuccessfulEntities.lean")
        if os.path.exists(filepath):
            try:
                with open(filepath, 'r', encoding='utf-8') as f:
                    content = f.read()
                
                blocks = content.split("-- Entity: ")
                new_blocks = [blocks[0]]
                removed_count = 0
                
                for block in blocks[1:]:
                    lines = block.splitlines()
                    if not lines:
                        new_blocks.append("-- Entity: " + block)
                        continue
                    header = lines[0]
                    block_id = header.split('|')[0].strip()
                    if block_id not in active_ids:
                        removed_count += 1
                        continue
                    new_blocks.append("-- Entity: " + block)
                    
                if removed_count > 0:
                    new_content = "".join(new_blocks)
                    with open(filepath, 'w', encoding='utf-8') as f:
                        f.write(new_content)
                    self.logger.info(f"[*] Из SuccessfulEntities.lean вычищено {removed_count} сиротских записей.")
            except Exception as e:
                self.logger.error(f"Ошибка при очистке SuccessfulEntities.lean: {e}")

    def process(self):
        entities = self.load_and_classify_entities()
        if not entities:
            self.logger.info("Семантических сущностей для анализа не найдено.")
            return

        # Группируем сущности по их чистому ID для синтаксической дедупликации
        id_groups = {}
        for e in entities:
            id_groups.setdefault(e['id'], []).append(e)

        # Фаза 1: Синтаксическое слияние по абсолютно совпадающим ID
        unique_entities = []
        for entity_id, group in id_groups.items():
            if len(group) > 1:
                self.logger.info(f"[!] Обнаружены синтаксические дубликаты с одинаковым ID '{entity_id}' (Количество: {len(group)})")
                for e in group:
                    self.logger.debug(f"  - Путь к файлу: {e['path']}")
                
                # Выбираем лучшего кандидата: отдаем приоритет файлу с более полной формулировкой (длиннее контент)
                group_sorted = sorted(group, key=lambda x: len(x['content']), reverse=True)
                target_entity = group_sorted[0]
                duplicates_to_delete = group_sorted[1:]
                
                self.logger.info(f"[*] Сохраняем наиболее полный файл: {target_entity['path']}")
                unique_entities.append(target_entity)
                
                # Физически удаляем остальные
                for dup in duplicates_to_delete:
                    if os.path.exists(dup['path']):
                        self.logger.info(f"[*] Удаление дубликата: {dup['path']}")
                        os.remove(dup['path'])
                        
                    # Физически удаляем соответствующий Lean файл дубликата
                    dup_lean_path = self.find_lean_file_by_id(dup['id'])
                    if dup_lean_path and os.path.exists(dup_lean_path):
                        self.logger.info(f"[*] Удаление дублирующего Lean файла: {dup_lean_path}")
                        os.remove(dup_lean_path)
            else:
                unique_entities.append(group[0])

        # Фаза 2: Семантическая дедупликация на основе косинусного сходства
        entities = unique_entities
        if len(entities) < 2:
            self.logger.info("Успешно завершено: семантическое сравнение не требуется (все сущности уникальны).")
            # Запускаем актуализацию Lean файлов
            self.actualize_lean_files()
            return

        self.logger.info("Построение векторного пространства для оставшихся уникальных сущностей...")
        embeddings = [self.get_embedding(e["formulation"]) for e in entities]
        
        n = len(entities)
        pairs_to_check = []
        similarity_threshold = 0.90  # Строгий порог для точных дубликатов
        
        # Находим пары сущностей с высокой схожестью в одной категории
        for i in range(n):
            for j in range(i + 1, n):
                if entities[i]['true_role'] == entities[j]['true_role']:
                    sim = self.cosine_similarity(embeddings[i], embeddings[j])
                    self.logger.debug(f"Сравнение [{entities[i]['id']}] <-> [{entities[j]['id']}]: семантическое сходство = {sim:.4f}")
                    if sim > similarity_threshold:
                        pairs_to_check.append((entities[i], entities[j], sim))

        if not pairs_to_check:
            self.logger.info("Семантических дубликатов в категориях (obj, prop, oper, thm, lem) не обнаружено.")
            # Запускаем актуализацию Lean файлов
            self.actualize_lean_files()
            return

        self.logger.info(f"Обнаружено {len(pairs_to_check)} пар-кандидатов с высоким сходством. Запуск Goedel верификации...")
        
        merged_ids = set() # Чтобы не обрабатывать уже удаленные сущности
        
        for e1, e2, sim in pairs_to_check:
            if e1['id'] in merged_ids or e2['id'] in merged_ids:
                continue
                
            self.logger.info(f"[!] Проверка пары [{e1['id']}] <-> [{e2['id']}] (схожесть: {sim:.4f})...")
            is_equiv, lean_code = self.ask_goedel_for_lean(e1, e2)
            
            if is_equiv:
                self.logger.info(f"[*] Goedel подтвердил эквивалентность! Запуск слияния {e2['id']} -> {e1['id']}...")
                
                # Физическое N-to-1 слияние LaTeX
                if os.path.exists(e2['path']):
                    os.remove(e2['path'])
                    
                # Физическое удаление Lean файла дубликата
                e2_lean_path = self.find_lean_file_by_id(e2['id'])
                if e2_lean_path and os.path.exists(e2_lean_path):
                    os.remove(e2_lean_path)
                
                # Запись теоремы эквивалентности в Validated
                clean_equiv_name = f"equiv_{e1['id'].replace('-','_')}_{e2['id'].replace('-','_')}"
                lean_path = os.path.join("lean_validator", "Validated", f"{clean_equiv_name}.lean")
                os.makedirs(os.path.dirname(lean_path), exist_ok=True)
                with open(lean_path, 'w', encoding='utf-8') as f:
                    f.write(lean_code)
                self.logger.info(f"[*] Сгенерирован Lean 4 файл эквивалентности: {lean_path}")
                
                # Очистка базы данных
                self.cleanup_database(e1['id'], e2['id'])
                
                # Удаление из SuccessfulEntities
                self.remove_entity_from_successful_entities(e2['id'])
                
                # Заменяем ссылки в LaTeX
                self.replace_references([e2['id']], e1['id'])
                merged_ids.add(e2['id'])
            else:
                self.logger.info(f"[-] Goedel отклонил эквивалентность для пары {e1['id']} <-> {e2['id']}.")

        # Запускаем актуализацию Lean файлов в самом конце
        self.actualize_lean_files()
        self.logger.info("Постпроцессинг математического графа успешно завершен.")

if __name__ == "__main__":
    import argparse
    # На Windows настраиваем кодировку вывода, чтобы не падать на символах ℝ, ↔ и др.
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8')

    parser = argparse.ArgumentParser(description="Mathesis Semantic Merger")
    parser.add_argument("--provider", type=str, default=None)
    parser.add_argument("--model", type=str, default=None)
    parser.add_argument("--api-key", type=str, default=None)
    parser.add_argument("--extract-provider", type=str, default=None)
    parser.add_argument("--extract-model", type=str, default=None)
    parser.add_argument("--extract-api-key", type=str, default=None)
    parser.add_argument("--lean-provider", type=str, default=None)
    parser.add_argument("--lean-model", type=str, default=None)
    parser.add_argument("--lean-api-key", type=str, default=None)
    args = parser.parse_args()
    
    merger = MathesisSemanticMerger(cli_args=args)
    merger.process()