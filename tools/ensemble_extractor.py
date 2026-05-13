import yaml
import sqlite3
import argparse
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "mathesis_index.db"
REGISTRY_PATH = PROJECT_ROOT / "sources" / "_registry.yaml"

def load_registry():
    with open(REGISTRY_PATH, 'r', encoding='utf-8') as f:
        return yaml.safe_load(f)

def extract_from_source(book_id, query):
    print(f"Extracting '{query}' from {book_id}...")
    
    # Mocking text extraction for testing purposes, now including context up to the start of the section
    query_lower = query.lower()
    if "интеграл" in query_lower:
        if "zorich" in book_id:
            return f"[КОНТЕКСТ АБЗАЦА]: Рассмотрим ограниченную функцию f, заданную на замкнутом промежутке [a,b]...\n[ОПРЕДЕЛЕНИЕ]: Пусть задано разбиение отрезка. Предел интегральных сумм при стремлении мелкости к нулю называется определенным интегралом. Источник: {book_id}"
        elif "fichtenholz" in book_id:
            return f"[КОНТЕКСТ АБЗАЦА]: Если функция f(x) ограничена на отрезке [a,b]...\n[ОПРЕДЕЛЕНИЕ]: Определенным интегралом от функции f(x) на [a,b] мы назовем общий предел всех интегральных сумм. Источник: {book_id}"
        elif "rudin" in book_id:
            return f"[КОНТЕКСТ АБЗАЦА]: Let f be a bounded real function defined on [a,b]...\n[ОПРЕДЕЛЕНИЕ]: If upper and lower Riemann integrals are equal, we say f is Riemann integrable on [a,b]. Source: {book_id}"
    elif "предел" in query_lower:
        if "zorich" in book_id:
            return f"[КОНТЕКСТ АБЗАЦА]: Пусть дана числовая последовательность...\n[ОПРЕДЕЛЕНИЕ]: Число a называется пределом последовательности x_n, если для любого эпсилон больше нуля найдется номер N... Источник: {book_id}"
        elif "rudin" in book_id:
            return f"[КОНТЕКСТ АБЗАЦА]: Suppose X is a metric space...\n[ОПРЕДЕЛЕНИЕ]: A sequence p_n in a metric space X is said to converge if there is a point p in X with... Source: {book_id}"

    return f"[КОНТЕКСТ АБЗАЦА]: (предшествующий текст)\n[ОПРЕДЕЛЕНИЕ]: Сырое определение для '{query}' из учебника {book_id}."

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

    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()

    count = 0
    for book in discipline_info.get("reading_list", []):
        book_id = book["id"]
        raw_text = extract_from_source(book_id, args.query)
        
        cursor.execute("""
            INSERT INTO formulation_raw_cache (discipline, source_book, raw_text)
            VALUES (?, ?, ?)
        """, (args.discipline, book_id, raw_text))
        count += 1

    conn.commit()
    conn.close()
    print(f"Ensemble extraction complete. Saved {count} raw formulations to cache.")

if __name__ == "__main__":
    main()
