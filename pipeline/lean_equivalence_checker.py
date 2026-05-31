import os
import re
import sys
import glob
import logging
import argparse
from pathlib import Path

# Добавляем корень проекта в пути импорта
PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.config import resolve_module_config
from pipeline.export_to_lean import setup_lean_provider, query_llm
from pipeline import lean_text_utils

class ProverEquivalenceVerifier:
    def __init__(self, content_dir="content", cli_args=None):
        self.content_dir = content_dir
        self.setup_logging()

        # Конфигурация для Lean-Prover
        self.prover_provider, self.prover_model, self.prover_api_key = resolve_module_config(
            module="prover",
            global_provider=getattr(cli_args, 'provider', None),
            global_model=getattr(cli_args, 'model', None),
            global_api_key=getattr(cli_args, 'api_key', None),
            module_provider=getattr(cli_args, 'prover_provider', None),
            module_model=getattr(cli_args, 'prover_model', None),
            module_api_key=getattr(cli_args, 'prover_api_key', None)
        )

        # Если модель не задана явно в CLI, по умолчанию используем "goedel-prover" с провайдером "ollama"
        has_explicit_model = cli_args and (getattr(cli_args, 'prover_model', None) or getattr(cli_args, 'model', None))
        if not has_explicit_model:
            self.prover_model = "goedel-prover"
            self.prover_provider = "ollama"

        self.logger.info(f"Инициализация Prover (Провайдер: {self.prover_provider.upper()}, Модель: {self.prover_model})")
        setup_lean_provider(self.prover_provider, api_key=self.prover_api_key, model=self.prover_model)

    def setup_logging(self):
        os.makedirs("logs", exist_ok=True)
        self.logger = logging.getLogger("ProverVerifier")
        self.logger.setLevel(logging.DEBUG)
        if self.logger.hasHandlers():
            self.logger.handlers.clear()

        fh = logging.FileHandler("logs/verify_equivalence.log", encoding='utf-8', mode='a')
        fh.setLevel(logging.DEBUG)
        fh.setFormatter(logging.Formatter('%(asctime)s [%(levelname)s] %(message)s'))
        self.logger.addHandler(fh)

        sh = logging.StreamHandler()
        sh.setLevel(logging.INFO)
        sh.setFormatter(logging.Formatter('[*] %(message)s'))
        self.logger.addHandler(sh)

    def _content_lean_map(self):
        """Ленивый индекс entity_id -> путь к .lean в content/ (один рекурсивный
        glob вместо glob на каждую пару). Кэшируется на время жизни объекта."""
        cache = getattr(self, "_content_lean_index", None)
        if cache is not None:
            return cache
        cache = {}
        for path in glob.glob(os.path.join(self.content_dir, '**', '*.lean'), recursive=True):
            m = re.search(r'\[([^\]]+)\]', os.path.basename(path))
            if m:
                cache.setdefault(m.group(1).strip(), path)
        self._content_lean_index = cache
        return cache

    def find_lean_file_by_id(self, entity_id):
        """Ищет .lean файл в lean_validator/Validated или в контенте (через кэш)."""
        # 1. Сначала ищем в lean_validator/Validated ({entity_id}.lean).
        validated_path = os.path.join("lean_validator", "Validated", f"{entity_id}.lean")
        if os.path.exists(validated_path):
            return validated_path
        # 2. Иначе — O(1) поиск по предпостроенному индексу content/.
        return self._content_lean_map().get(entity_id)

    def extract_lean_statement(self, lean_filepath):
        """Извлекает строгую формулировку сущности (см. pipeline.lean_text_utils)."""
        return lean_text_utils.extract_lean_statement(lean_filepath)

    def get_lean_name(self, statement):
        """Извлекает имя теоремы/определения (см. pipeline.lean_text_utils)."""
        return lean_text_utils.get_lean_name(statement)

    def determine_operator(self, entity_id):
        """Оператор эквивалентности по префиксу ID (см. pipeline.lean_text_utils)."""
        return lean_text_utils.determine_operator(entity_id)

    def verify_pair(self, id1, id2):
        """Основной метод проверки пары ID."""
        self.logger.info(f"Запуск формальной проверки: [{id1}] <-> [{id2}]")

        path1 = self.find_lean_file_by_id(id1)
        path2 = self.find_lean_file_by_id(id2)

        if not path1 or not path2:
            self.logger.error(f"Не найдены .lean файлы для пары {id1} и {id2}.")
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
Choose an appropriate name for the theorem, for example: `equiv_{id1.replace('-','_')}_{id2.replace('-','_')}`.
Generate the tactical proof. Use powerful Mathlib tactics like `aesop`, `tauto`, `ext`, or `simp`.
If the equivalence requires complex intermediate lemmas not present in the context, gracefully close the goal with `sorry`.

Do not provide conversational text. Output ONLY the valid Lean 4 code block.
"""
        try:
            reply = query_llm(prompt=prompt, model=self.prover_model, provider=self.prover_provider)

            # Логируем работу прувера
            goedel_log_dir = os.path.join("logs", "postprocess_prover")
            os.makedirs(goedel_log_dir, exist_ok=True)
            log_filepath = os.path.join(goedel_log_dir, f"{id1}_vs_{id2}.txt")
            with open(log_filepath, 'w', encoding='utf-8') as lf:
                lf.write(f"=== PROMPT ===\n{prompt}\n\n=== REPLY ===\n{reply}\n")

            lean_matches = re.findall(r'```lean(.*?)```', reply, re.DOTALL)
            if lean_matches:
                # Ищем блок кода, который не содержит "sorry"
                best_code = None
                for match in lean_matches:
                    code_candidate = match.strip()
                    if "sorry" not in code_candidate:
                        best_code = code_candidate
                        break
                    elif best_code is None:
                        best_code = code_candidate

                if "sorry" not in best_code:
                    self.logger.info("[+] УСПЕХ: Goedel-Prover доказал эквивалентность!")
                    return True, best_code
                else:
                    self.logger.info("[-] ПРОВАЛ: Prover использовал 'sorry'. Эквивалентность не доказана.")
                    return False, best_code
            else:
                self.logger.warning("Не найден блок кода в ответе модели.")
        except Exception as e:
            self.logger.error(f"Ошибка при вызове Prover: {e}")

        return False, None

if __name__ == "__main__":
    # На Windows настраиваем кодировку вывода, чтобы не падать на символах ℝ, ↔ и др.
    if hasattr(sys.stdout, 'reconfigure'):
        sys.stdout.reconfigure(encoding='utf-8')
    if hasattr(sys.stderr, 'reconfigure'):
        sys.stderr.reconfigure(encoding='utf-8')

    parser = argparse.ArgumentParser(description="Standalone Lean Equivalence Prover")
    parser.add_argument("id1", type=str, help="ID первой сущности (например, thm-rolle)")
    parser.add_argument("id2", type=str, help="ID второй сущности (например, thm-rolle-dup)")
    parser.add_argument("--provider", type=str, default=None)
    parser.add_argument("--model", type=str, default=None)
    parser.add_argument("--api-key", type=str, default=None)
    parser.add_argument("--prover-provider", type=str, default=None)
    parser.add_argument("--prover-model", type=str, default=None)
    parser.add_argument("--prover-api-key", type=str, default=None)
    args = parser.parse_args()

    verifier = ProverEquivalenceVerifier(cli_args=args)
    is_equiv, code = verifier.verify_pair(args.id1, args.id2)

    if is_equiv:
        print("\nУтверждения математически эквивалентны. Сгенерированный код:")
        print(code)
    else:
        print("\nДоказать эквивалентность не удалось (см. логи).")
