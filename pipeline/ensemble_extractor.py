"""
Ensemble Extractor v2 — Global PDF Search
==========================================
Scans ALL PDFs in Books/ directory (no registry dependency).
Two-phase search: ToC index → full-text fallback.
Uses LLM for structured extraction from raw text.
"""
import sqlite3
import argparse
import re
import sys
import json
import urllib.request
import time
from pathlib import Path
import fitz  # PyMuPDF

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.export_to_lean import query_llm, setup_provider, setup_lean_provider, _LLM_PROVIDER
from pipeline.config import PROVIDERS, resolve_module_config


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "mathesis_index.db"
BOOKS_DIR = PROJECT_ROOT / "Books"
TOC_CACHE_PATH = PROJECT_ROOT / "pipeline" / "book_toc_cache.json"

# ── Mathematical Stem Dictionary ──────────────────────────────────────────────
# Maps common inflected forms to stable roots for search.
# Falls back to suffix-trimming for unknown words.
MATH_STEMS_RU = {
    "предел": "предел", "пределом": "предел", "предела": "предел",
    "пределу": "предел", "пределе": "предел", "пределы": "предел",
    "последовательность": "последовательн", "последовательности": "последовательн",
    "последовательностью": "последовательн", "последовательностей": "последовательн",
    "функция": "функц", "функции": "функц", "функцию": "функц", "функций": "функц",
    "ограниченная": "огранич", "ограниченной": "огранич", "ограниченность": "огранич",
    "непрерывность": "непрерывн", "непрерывная": "непрерывн", "непрерывной": "непрерывн",
    "непрерывна": "непрерывн",
    "интеграл": "интеграл", "интеграла": "интеграл", "интегралу": "интеграл",
    "интегрирование": "интеграл", "интегрируемая": "интеграл",
    "производная": "производн", "производной": "производн", "производных": "производн",
    "теорема": "теорем", "теоремы": "теорем", "теореме": "теорем",
    "лемма": "лемм", "леммы": "лемм",
    "множество": "множеств", "множества": "множеств", "множеств": "множеств",
    "сходимость": "сходим", "сходится": "сходим", "сходящаяся": "сходим",
    "числовая": "числов", "числовой": "числов",
    "вещественных": "вещественн", "вещественные": "вещественн",
    "определение": "определен", "определения": "определен",
    "доказательство": "доказательств", "доказательства": "доказательств",
    "аксиома": "аксиом", "аксиомы": "аксиом",
}

MATH_STEMS_EN = {
    "convergence": "convergence", "convergent": "convergence", "converges": "convergence",
    "bounded": "bounded", "boundedness": "bounded",
    "continuous": "continuous", "continuity": "continuous",
    "derivative": "derivative", "derivatives": "derivative", "differentiation": "derivative",
    "integral": "integral", "integration": "integral", "integrable": "integral",
    "integrals": "integral",
    "sequence": "sequence", "sequences": "sequence",
    "function": "function", "functions": "function",
    "theorem": "theorem", "theorems": "theorem",
    "limit": "limit", "limits": "limit",
    "definition": "definition", "definitions": "definition",
    "proof": "proof", "proofs": "proof",
    "set": "set", "sets": "set",
    "axiom": "axiom", "axioms": "axiom",
    "sum": "sum", "sums": "sum",
    "riemann": "riemann",
}

PROOF_END_MARKERS = ["∎", "□", "Q.E.D.", "q.e.d.", "Доказательство завершено",
                     "Теорема доказана", "что и требовалось доказать", "ч.т.д.",
                     "\\blacksquare", "\\qed"]


# ── Book Discovery ───────────────────────────────────────────────────────────

def get_all_books():
    """Scans Books/ directory for all PDFs. No registry dependency."""
    if not BOOKS_DIR.exists():
        print(f"[-] Директория Books/ не найдена: {BOOKS_DIR}")
        return []
    pdfs = sorted(BOOKS_DIR.glob("*.pdf"))
    print(f"[*] Обнаружено {len(pdfs)} книг в библиотеке.")
    return pdfs


def extract_book_id(pdf_path: Path) -> str:
    """Derives a short book_id from filename. E.g. 'Zorich, V.A. - ...' → 'zorich'."""
    name = pdf_path.stem
    # Take the first author's surname, lowercase
    author_part = name.split(" - ")[0] if " - " in name else name
    surname = author_part.split(",")[0].split(" ")[0].strip()
    return surname.lower().replace(".", "")


# ── ToC Index ────────────────────────────────────────────────────────────────

def load_toc_cache() -> dict:
    if TOC_CACHE_PATH.exists():
        try:
            return json.loads(TOC_CACHE_PATH.read_text(encoding="utf-8"))
        except Exception:
            pass
    return {}


def save_toc_cache(cache: dict):
    TOC_CACHE_PATH.write_text(json.dumps(cache, ensure_ascii=False, indent=2), encoding="utf-8")


def build_toc_index(pdf_path: Path) -> list:
    """
    Extracts Table of Contents from PDF.
    Returns list of {"title": str, "page": int, "level": int}.
    Caches result in book_toc_cache.json.
    """
    cache = load_toc_cache()
    key = pdf_path.name

    if key in cache:
        return cache[key]

    try:
        doc = fitz.open(pdf_path)
        raw_toc = doc.get_toc()  # [[level, title, page], ...]
        doc.close()
    except Exception as e:
        print(f"  [!] Не удалось извлечь оглавление из {pdf_path.name}: {e}")
        cache[key] = []
        save_toc_cache(cache)
        return []

    toc = []
    for level, title, page in raw_toc:
        toc.append({"title": title.strip(), "page": page, "level": level})

    cache[key] = toc
    save_toc_cache(cache)

    if toc:
        print(f"  [ToC] {pdf_path.name}: {len(toc)} разделов проиндексировано.")
    return toc


# ── Stemming ─────────────────────────────────────────────────────────────────

def stem_word(word: str, lang: str = "ru") -> str:
    """Stems a single word using the math dictionary, with fallback to suffix trimming for RU only."""
    w = word.lower().strip()
    if lang == "ru":
        if w in MATH_STEMS_RU:
            return MATH_STEMS_RU[w]
        # Fallback: trim suffix for RU
        if len(w) > 6:
            return w[:-3]
        elif len(w) > 4:
            return w[:-2]
        elif len(w) > 2:
            return w[:-1]
    else:
        if w in MATH_STEMS_EN:
            return MATH_STEMS_EN[w]
        return w
    return w


def get_search_roots(query: str, lang: str = "ru") -> list:
    """Extracts stemmed search roots from query, filtering stop-words."""
    stop_words = {
        # RU
        "что", "как", "это", "такое", "называется", "является", "для",
        "и", "или", "в", "на", "от", "до", "при", "по", "из", "к", "о", "с",
        "через", "про", "за", "не", "ни", "все", "если", "то", "его", "ее",
        "когда", "бы", "тоже", "еще", "уже", "ну", "расскажи",
        "определение", "понятие", "объясни",
        # EN
        "the", "what", "is", "a", "an", "of", "for", "in", "by", "to",
        "via", "using", "with", "and", "or", "not", "that", "this",
        "from", "on", "at", "be", "as", "it", "its", "are", "was",
        "definition", "theorem", "proof", "show", "about", "through",
    }
    clean = re.sub(r'[^\w\s]', '', query)
    words = [w for w in clean.lower().split() if w not in stop_words and len(w) > 1]
    roots = list(set(stem_word(w, lang) for w in words))
    return roots


# ── Entity Type Detection ────────────────────────────────────────────────────

def detect_entity_type(query: str) -> str:
    q = query.lower()
    if any(kw in q for kw in ["теорема", "лемма", "следствие", "theorem", "lemma", "corollary"]):
        return "theorem"
    return "definition"


# ── Phase 1: ToC-Based Search ────────────────────────────────────────────────

def search_toc(toc: list, roots: list) -> list:
    """
    Finds ToC entries matching roots and ranks them by match count.
    Returns list of (page, title) tuples sorted by relevance.
    """
    scored_results = []
    last_root = roots[-1] if roots else ""
    
    for entry in toc:
        title_lower = entry["title"].lower()
        matched_roots = [root for root in roots if root in title_lower]
        
        if matched_roots:
            score = len(matched_roots)
            # Bonus for full match
            if score == len(roots):
                score += 5
            # Bonus for the last word (user's priority anchor)
            if last_root in matched_roots:
                score += 2
                
            scored_results.append((score, entry["page"] - 1, entry["title"]))  # 0-indexed
            
    # Sort by score (descending)
    scored_results.sort(key=lambda x: x[0], reverse=True)
    
    return [(page, title) for score, page, title in scored_results]


def get_section_page_range(toc: list, target_page: int) -> tuple:
    """Returns (start_page, end_page) for the section containing target_page."""
    pages = sorted(set(e["page"] - 1 for e in toc))  # 0-indexed
    start = target_page
    end = None
    for i, p in enumerate(pages):
        if p == target_page:
            end = pages[i + 1] if i + 1 < len(pages) else None
            break
    return start, end


# ── Phase 2: Full-Text Search ────────────────────────────────────────────────

def search_fulltext(pdf_path: Path, roots: list, max_pages=5) -> list:
    """Scans all pages for root co-occurrence. Ranks pages by number of matching roots."""
    try:
        doc = fitz.open(pdf_path)
    except Exception:
        return []

    if not roots:
        doc.close()
        return []

    scored_results = []
    last_root = roots[-1]

    for i in range(len(doc)):
        text = doc[i].get_text("text").lower().replace('\n', ' ')
        matched_roots = [r for r in roots if r in text]
        
        if matched_roots:
            score = len(matched_roots)
            # Bonus for full match
            if score == len(roots):
                score += 5
            # Bonus for the last word (user's priority anchor)
            if last_root in matched_roots:
                score += 2
                
            scored_results.append((score, i, matched_roots))

    doc.close()
    
    # Sort by score descending, then by page ascending
    scored_results.sort(key=lambda x: (-x[0], x[1]))
    
    results = []
    for score, page, matched in scored_results[:max_pages]:
        print(f"  [fulltext] стр.{page+1}: совпали {len(matched)}/{len(roots)} — {matched} (score: {score})")
        results.append(page)

    return results


# ── Context Extraction ───────────────────────────────────────────────────────

def extract_context_window(pdf_path: Path, center_page: int, entity_type: str) -> str:
    """
    Extracts text around the target page.
    - Definitions: ±1 page (3 pages total)
    - Theorems: up to ±3 pages (searches for proof-end markers)
    """
    doc = fitz.open(pdf_path)
    max_page = len(doc) - 1

    if entity_type == "theorem":
        start = max(0, center_page - 1)
        # Scan forward for proof end markers
        end = min(max_page, center_page + 3)
        for i in range(center_page, min(center_page + 4, max_page + 1)):
            page_text = doc[i].get_text("text")
            if any(marker in page_text for marker in PROOF_END_MARKERS):
                end = i
                break
    else:
        start = max(0, center_page - 1)
        end = min(max_page, center_page + 1)

    window_text = ""
    for i in range(start, end + 1):
        window_text += f"\n--- PAGE {i + 1} ---\n{doc[i].get_text('text')}"

    doc.close()
    return window_text


# ── LLM Parsing ──────────────────────────────────────────────────────────────

def parse_with_llm(raw_text: str, query: str, entity_type: str, model="llama3.1:8b") -> dict:
    """Uses LLM to extract structured formulation from raw PDF text."""
    prompt = f"""Ты — математический редактор. Извлеки из сырого текста учебника формулировку для термина: "{query}".
Тип: {entity_type}.

Текст из учебника:
{raw_text[:6000]}

ИНСТРУКЦИИ:
1. СОХРАНИ ключевые слова "{query}" в поле statement.
2. "context": Вводные условия (например: "Пусть f — функция...").
3. "statement": Полная формулировка определения или теоремы.
4. "proof": Текст доказательства (только для теорем, иначе null).
5. "found": Если в тексте НЕТ именно этого объекта — false.
6. "page_ref": Номер страницы из заголовков "--- PAGE N ---".

Верни СТРОГО JSON:
{{ "found": true, "context": "...", "statement": "...", "proof": "...", "page_ref": 0 }}
"""
    response = query_llm(prompt, model=model, json_mode=True)
    try:
        return json.loads(response)
    except (json.JSONDecodeError, ValueError):
        return {"found": False}


# ── Main Pipeline ────────────────────────────────────────────────────────────

def process_single_book(pdf_path: Path, query: str, entity_type: str, roots: list,
                        model: str) -> list:
    """
    Two-phase search on a single PDF.
    Returns list of extracted formulations.
    """
    if not pdf_path.exists():
        print(f"  [SKIP] Файл {pdf_path.name} не найден (перемещен/удален).")
        return []

    book_id = extract_book_id(pdf_path)
    print(f"\n  ── {book_id} ({pdf_path.name}) ──")

    # Phase 1: ToC search
    toc = build_toc_index(pdf_path)
    target_pages = []

    if toc:
        toc_hits = search_toc(toc, roots)
        if toc_hits:
            print(f"  [ToC] Совпадения в оглавлении: {[t[1] for t in toc_hits[:3]]}")
            for page, title in toc_hits[:3]:
                # Get section range for more targeted extraction
                start, end = get_section_page_range(toc, page)
                target_pages.append(page)

    # Phase 2: Full-text fallback
    if not target_pages:
        print(f"  [*] ToC не дал результатов, полнотекстовый поиск по корням {roots}...")
        target_pages = search_fulltext(pdf_path, roots, max_pages=3)

    if not target_pages:
        print(f"  [SKIP] Термин не найден.")
        return []

    print(f"  [+] Целевые страницы: {[p + 1 for p in target_pages]}")

    # Extract and parse
    results = []
    seen_pages = set()
    for page_idx in target_pages:
        if page_idx in seen_pages:
            continue
        seen_pages.add(page_idx)

        raw_text = extract_context_window(pdf_path, page_idx, entity_type)
        print(f"  [*] LLM-анализ стр. {page_idx + 1}...")
        parsed = parse_with_llm(raw_text, query, entity_type, model=model)

        if parsed.get("found"):
            page_ref = parsed.get("page_ref", page_idx + 1)
            results.append({
                "context": parsed.get("context", ""),
                "statement": parsed.get("statement", ""),
                "proof": parsed.get("proof"),
                "source": book_id,
                "page_ref": page_ref,
            })
            print(f"  [OK] Извлечено (стр. {page_ref}).")
        else:
            print(f"  [SKIP] LLM: нерелевантный фрагмент.")

    return results


def main():
    parser = argparse.ArgumentParser(description="Ensemble PDF Extractor v2 — Global Search")
    parser.add_argument("query", type=str, help="Математический термин для поиска (может быть в формате 'ru|en')")
    parser.add_argument("--cv-model", type=str, default="glm-ocr", help="Модель CV/OCR")

    # ── Глобальные аргументы (оверрайдят все модули) ─────────────────────────
    parser.add_argument("--provider", type=str, default=None, choices=PROVIDERS,
                        help="Глобальный LLM провайдер (оверрайдит --extract-provider)")
    parser.add_argument("--model",    type=str, default=None,
                        help="Глобальная модель (оверрайдит --extract-model)")
    parser.add_argument("--api-key",  type=str, default=None,
                        help="Глобальный API ключ (оверрайдит --extract-api-key)")

    # ── Per-module аргументы для extraction ──────────────────────────────────
    parser.add_argument("--extract-provider", type=str, default=None, choices=PROVIDERS,
                        help="Провайдер LLM для модуля извлечения")
    parser.add_argument("--extract-model",    type=str, default=None,
                        help="Модель LLM для модуля извлечения")
    parser.add_argument("--extract-api-key",  type=str, default=None,
                        help="API ключ для модуля извлечения")

    # ── Lean-аргументы (для консистентности при запуске через ollama_wrapper) -
    parser.add_argument("--lean-provider", type=str, default=None, choices=PROVIDERS, help="Игнорируется в этом модуле")
    parser.add_argument("--lean-api-key",  type=str, default=None, help="Игнорируется в этом модуле")
    parser.add_argument("--lean-model",    type=str, default=None, help="Игнорируется в этом модуле")

    args = parser.parse_args()

    # Разрешаем итоговую конфигурацию модуля extraction
    provider, model, api_key = resolve_module_config(
        module="extract",
        global_provider=args.provider,
        global_model=args.model,
        global_api_key=args.api_key,
        module_provider=args.extract_provider,
        module_model=args.extract_model,
        module_api_key=args.extract_api_key,
    )

    # Initialize LLM provider via shared logic
    setup_provider(provider, api_key=api_key, model=model)


    from pipeline.export_to_lean import _LLM_PROVIDER
    active_provider_name = (_LLM_PROVIDER or "OLLAMA").upper()
    print(f"[*] Провайдер: {active_provider_name} ({model})")

    # Parse dual-language query if provided
    if "|" in args.query:
        query_ru, query_en = args.query.split("|", 1)
    else:
        query_ru = args.query
        query_en = args.query

    print(f"[*] Глобальный поиск: RU='{query_ru}', EN='{query_en}'")

    entity_type = detect_entity_type(query_ru)
    roots_ru = get_search_roots(query_ru, lang="ru")
    roots_en = get_search_roots(query_en, lang="en")
    print(f"[*] Тип: {entity_type} | Корни RU: {roots_ru} | Корни EN: {roots_en}")

    all_books = get_all_books()
    if not all_books:
        print("[-] Нет книг для поиска.")
        sys.exit(1)

    # Init DB
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
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

    total_count = 0
    for pdf_path in all_books:
        # Route term based on book language tag in filename
        filename = pdf_path.name.upper()
        if "(EN)" in filename:
            active_query = query_en
            active_roots = roots_en
        elif "(RU)" in filename:
            active_query = query_ru
            active_roots = roots_ru
        else:
            # Fallback based on alphabet detection
            if any("\u0400" <= c <= "\u04FF" for c in query_ru):
                active_query = query_ru
                active_roots = roots_ru
            else:
                active_query = query_en
                active_roots = roots_en

        results = process_single_book(pdf_path, active_query, entity_type, active_roots, model)

        for res in results:
            text_parts = []
            if res["context"]:
                text_parts.append(f"[КОНТЕКСТ]: {res['context']}")
            text_parts.append(f"[ФОРМУЛИРОВКА]: {res['statement']}")

            has_proof = 0
            if res.get("proof"):
                text_parts.append(f"[ДОКАЗАТЕЛЬСТВО]: {res['proof']}")
                has_proof = 1

            # Skip theorems without proofs
            if entity_type == "theorem" and not has_proof:
                print(f"  [SKIP] Теорема из {res['source']} без доказательства.")
                continue

            full_text = "\n\n".join(text_parts)
            cursor.execute(
                "INSERT INTO formulation_raw_cache (discipline, source_book, raw_text, entity_type, has_proof) "
                "VALUES (?, ?, ?, ?, ?)",
                ("global", res["source"], full_text, entity_type, has_proof)
            )
            total_count += 1

    conn.commit()
    conn.close()
    print(f"\n[*] Ensemble extraction complete. Извлечено формулировок: {total_count}")


if __name__ == "__main__":
    main()