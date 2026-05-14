import yaml
import sqlite3
import argparse
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "mathesis_index.db"
REGISTRY_PATH = PROJECT_ROOT / "sources" / "_registry.yaml"

# Маркеры, которые указывают на конец доказательства в тексте учебника
PROOF_END_MARKERS = [
    r"\blacksquare",
    r"\qed",
    "Доказательство завершено",
    "Теорема доказана",
    "что и требовалось доказать",
    "Q.E.D.",
]

def load_registry():
    with open(REGISTRY_PATH, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def detect_entity_type(query):
    """Определяет тип сущности по ключевым словам в запросе."""
    query_lower = query.lower()
    theorem_keywords = ["теорема", "лемма", "следствие", "theorem", "lemma", "corollary"]
    for kw in theorem_keywords:
        if kw in query_lower:
            return "theorem"
    return "definition"

def extract_from_source(book_id, query, entity_type):
    """
    Извлекает текст из учебника.
    Для теорем применяет Forward Sliding Window — захватывает доказательство
    после формулировки. Если доказательство не найдено, возвращает None (skip).
    """
    print(f"  Extracting '{query}' from {book_id}...")

    query_lower = query.lower()

    # --- Mocked extraction logic ---
    # В реальном пайплайне здесь будет PDF-парсер с поиском по индексу
    if entity_type == "theorem":
        if "вейерштрасс" in query_lower:
            if "zorich" in book_id:
                return {
                    "context": "[КОНТЕКСТ ПАРАГРАФА]: §3.4. Свойства непрерывных функций. "
                               "Пусть f — непрерывная функция на замкнутом ограниченном отрезке [a,b].",
                    "statement": "[ФОРМУЛИРОВКА ТЕОРЕМЫ]: Если f непрерывна на [a,b], то f ограничена и "
                                 "достигает своего супремума и инфимума на [a,b].",
                    "proof": "[ДОКАЗАТЕЛЬСТВО]: Предположим, что f не ограничена сверху. Тогда для каждого "
                             "n ∈ ℕ существует x_n ∈ [a,b] такое, что f(x_n) > n. По теореме "
                             "Больцано-Вейерштрасса, из последовательности {x_n} можно выделить "
                             "сходящуюся подпоследовательность x_{n_k} → c ∈ [a,b]. Но f непрерывна "
                             "в точке c, значит f(x_{n_k}) → f(c), что противоречит f(x_{n_k}) > n_k → ∞. "
                             "Аналогично f ограничена снизу. Пусть M = sup f([a,b]). Существует {y_n} такая, "
                             "что f(y_n) → M. Выделим сходящуюся подпоследовательность y_{n_k} → d ∈ [a,b]. "
                             "По непрерывности f(d) = M. ∎",
                    "source": book_id
                }
            elif "fichtenholz" in book_id:
                # Фихтенгольц содержит формулировку, но без доказательства в данном разделе
                return None  # Пропускаем — нет доказательства
            elif "rudin" in book_id:
                return {
                    "context": "[CONTEXT]: §4. Continuity. Suppose f is continuous on a compact metric space.",
                    "statement": "[THEOREM]: If f is continuous on a compact set K, then f(K) is compact. "
                                 "In particular, f is bounded and attains its maximum and minimum.",
                    "proof": "[PROOF]: Since K is compact and f is continuous, f(K) is compact (Theorem 4.14). "
                             "Since f(K) is a compact subset of R, it is closed and bounded (Theorem 2.41). "
                             "Hence sup f(K) and inf f(K) exist and belong to f(K). ∎",
                    "source": book_id
                }
        # Общая заглушка для других теорем
        return {
            "context": f"[КОНТЕКСТ]: (предшествующий текст параграфа)",
            "statement": f"[ТЕОРЕМА]: Формулировка теоремы '{query}' из {book_id}.",
            "proof": f"[ДОКАЗАТЕЛЬСТВО]: Доказательство теоремы '{query}' из {book_id}. ∎",
            "source": book_id
        }
    else:
        # Для определений — классический Backward Sliding Window (до начала параграфа)
        if "интеграл" in query_lower:
            if "zorich" in book_id:
                return {
                    "context": "[КОНТЕКСТ АБЗАЦА]: Рассмотрим ограниченную функцию f, заданную на замкнутом промежутке [a,b]...",
                    "statement": "[ОПРЕДЕЛЕНИЕ]: Пусть задано разбиение отрезка. Предел интегральных сумм при "
                                 "стремлении мелкости к нулю называется определенным интегралом.",
                    "proof": None,
                    "source": book_id
                }
            elif "rudin" in book_id:
                return {
                    "context": "[CONTEXT]: Let f be a bounded real function defined on [a,b]...",
                    "statement": "[DEFINITION]: If upper and lower Riemann integrals are equal, "
                                 "we say f is Riemann integrable on [a,b].",
                    "proof": None,
                    "source": book_id
                }
        elif "предел" in query_lower:
            if "zorich" in book_id:
                return {
                    "context": "[КОНТЕКСТ АБЗАЦА]: Пусть дана числовая последовательность...",
                    "statement": "[ОПРЕДЕЛЕНИЕ]: Число a называется пределом последовательности x_n, "
                                 "если для любого ε > 0 найдется номер N...",
                    "proof": None,
                    "source": book_id
                }

        return {
            "context": f"[КОНТЕКСТ]: (предшествующий текст)",
            "statement": f"[ОПРЕДЕЛЕНИЕ]: Сырое определение для '{query}' из учебника {book_id}.",
            "proof": None,
            "source": book_id
        }


def main():
    parser = argparse.ArgumentParser(description="Extracts raw formulations from multiple textbooks.")
    parser.add_argument("query", type=str)
    parser.add_argument("--discipline", type=str, default="mathematical_analysis")
    args = parser.parse_args()

    registry = load_registry()
    discipline_info = registry.get("disciplines", {}).get(args.discipline)

    if not discipline_info:
        print(f"Discipline {args.discipline} not found in registry.")
        return

    entity_type = detect_entity_type(args.query)
    print(f"[*] Detected entity type: {entity_type}")

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    # Ensure table exists with necessary columns
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS formulation_raw_cache (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            discipline TEXT,
            source_book TEXT NOT NULL,
            raw_text TEXT NOT NULL,
            entity_type TEXT DEFAULT 'definition',
            has_proof INTEGER DEFAULT 0,
            temp_cluster_id TEXT
        )
    """)

    count = 0
    skipped = 0
    for book in discipline_info.get("reading_list", []):
        book_id = book["id"]
        result = extract_from_source(book_id, args.query, entity_type)

        if result is None:
            print(f"  [SKIP] {book_id} — доказательство не найдено, пропускаем источник.")
            skipped += 1
            continue

        # Собираем полный текст: контекст + формулировка + доказательство (если есть)
        full_text_parts = [result["context"], result["statement"]]
        has_proof = 0
        if result.get("proof"):
            full_text_parts.append(result["proof"])
            has_proof = 1

        # Для теорем без доказательства — пропускаем
        if entity_type == "theorem" and not has_proof:
            print(f"  [SKIP] {book_id} — теорема найдена, но доказательство отсутствует.")
            skipped += 1
            continue

        full_text = "\n".join(full_text_parts)

        cursor.execute("""
            INSERT INTO formulation_raw_cache (discipline, source_book, raw_text, entity_type, has_proof)
            VALUES (?, ?, ?, ?, ?)
        """, (args.discipline, book_id, full_text, entity_type, has_proof))
        count += 1

    conn.commit()
    conn.close()

    print(f"\nEnsemble extraction complete.")
    print(f"  Saved: {count} formulations | Skipped: {skipped} sources (no proof)")


if __name__ == "__main__":
    main()
