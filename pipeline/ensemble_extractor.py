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
from pathlib import Path
import fitz  # PyMuPDF

# Fix Windows console encoding
if sys.platform == 'win32':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
        sys.stderr.reconfigure(encoding='utf-8')
    except AttributeError:
        pass

PROJECT_ROOT = Path(__file__).resolve().parent.parent
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.model_manager import ModelManager
from pipeline.config import PROVIDERS, resolve_module_config
from pipeline import pdf_text


PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "db/mathesis_index.db"
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
    clean = re.sub(r'[^\w\s\-]', '', query)
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

def search_fulltext(pdf_path: Path, roots: list, max_pages=None) -> list:
    """Scans all pages for root co-occurrence. Returns list of matching page indices (all matches by default)."""
    if not roots:
        return []

    # Текст страниц извлекается один раз и кэшируется (переиспользуется всеми фазами).
    page_texts = pdf_text.get_page_texts(pdf_path)
    if not page_texts:
        return []

    scored_results = []
    roots_lower = [r.lower() for r in roots]
    last_root = roots_lower[-1]

    for i, text in enumerate(page_texts):
        matched_roots = [r for r in roots_lower if r in text]

        if matched_roots:
            score = len(matched_roots)
            # Bonus for full match
            if score == len(roots_lower):
                score += 5
            # Bonus for the last word (user's priority anchor)
            if last_root in matched_roots:
                score += 2

            scored_results.append((score, i, matched_roots))

    # Sort by score descending, then by page ascending
    scored_results.sort(key=lambda x: (-x[0], x[1]))

    results = []
    iter_list = scored_results if max_pages is None else scored_results[:max_pages]
    for score, page, matched in iter_list:
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
    """Uses LLM to extract structured formulation from raw PDF text. MUST return a JSON object including a 'deps' array."""
    prompt = f"""Ты — математический редактор. Извлеки из сырого текста учебника формулировку для термина: "{query}".
Тип: {entity_type}.

Текст из учебника:
{raw_text[:6000]}

ИНСТРУКЦИИ:
1. "context": Вводные условия (например: "Пусть f — функция...").
2. "statement": Полная формулировка определения или теоремы.
3. "proof": Текст доказательства (только для теорем, иначе null).
4. "deps": Список коротких строк — имена/фразы зависимостей (пример: ["limit of a function", "point"]). Если зависимостей нет — верни пустой массив [].
5. "found": Если в тексте НЕТ именно этого объекта — false.
6. "page_ref": Номер страницы из заголовков "--- PAGE N ---".

Верни СТРОГО JSON:
{{ "found": true, "context": "...", "statement": "...", "proof": "...", "deps": [], "page_ref": 0 }}
}}
"""
    mgr = ModelManager.get_instance()
    response = mgr.query_llm(prompt, json_mode=True, role="extract")

    # Strip markdown JSON wrappers if present
    response = re.sub(r'^```json\s*', '', response.strip(), flags=re.MULTILINE)
    response = re.sub(r'^```\s*$', '', response.strip(), flags=re.MULTILINE).strip()

    try:
        result = json.loads(response)
        # Some models return a list instead of a dict
        if isinstance(result, list):
            result = result[0] if result else {"found": False, "deps": []}
        if not isinstance(result, dict):
            return {"found": False, "deps": []}
        # Ensure deps key exists
        if 'deps' not in result:
            result['deps'] = []
        return result
    except (json.JSONDecodeError, ValueError):
        return {"found": False, "deps": []}


# ── Main Pipeline ────────────────────────────────────────────────────────────

def preview_scan(pdf_path: Path, query: str, preview_provider: str, preview_model: str, candidate_pages: list | None = None, entity_type: str = "definition") -> list:
    """Scan selected pages using preview LLM or Hybrid Search Cross-Encoder to find candidate pages.

    If candidate_pages is provided, only those pages are scanned. Otherwise all pages are scanned.
    Returns list of (page_index, score) tuples sorted by score descending.
    """
    if not preview_model or not preview_provider:
        return []

    import fitz

    doc = fitz.open(pdf_path)
    pages_to_scan = list(candidate_pages) if candidate_pages is not None else list(range(len(doc)))

    # Check if the preview configuration targets a Cross-Encoder Reranker
    is_cross_encoder = (
        preview_provider == "llama_cpp" or
        "reranker" in preview_model.lower() or
        "gte-multilingual" in preview_model.lower()
    )

    if is_cross_encoder:
        print(f"  [Preview] Using Two-Stage Cross-Encoder Reranker ({preview_model})...")
        try:
            from pipeline.hybrid_search import HybridSearchPipeline

            # Resolve backend and model name/REST api URL
            backend = "local"
            model_name = "BAAI/bge-reranker-v2-m3"
            api_url = None
            server_model_path = None

            if preview_provider == "llama_cpp":
                # Check for running local server at standard ports (e.g. native llama-server)
                import urllib.request
                server_urls = [
                    "http://localhost:8080/rerank",
                    "http://localhost:8080/v1/rerank",
                    "http://localhost:8000/v1/rerank"
                ]
                for url in server_urls:
                    try:
                        req = urllib.request.Request(url, data=b"{}", headers={'Content-Type': 'application/json'})
                        with urllib.request.urlopen(req, timeout=0.3):
                            pass
                        api_url = url
                        backend = "rest"
                        print(f"  [Preview] Detected active local reranker server at {url}. Using REST backend.")
                        break
                    except Exception:
                        continue

                # If no running server is found, instead of spawning a buggy background server,
                # we run in-process using PyTorch CPU in-memory! This completely avoids port conflicts,
                # deadlocks, and FastAPI 404 routing errors.
                if backend == "local":
                    print("  [Preview] No active local reranker REST server found. Running Cross-Encoder in-process (in-memory PyTorch CPU)...")
                    if ".gguf" in preview_model.lower() or "/" in preview_model or "\\" in preview_model:
                        # Map local GGUF path to public model name for PyTorch execution
                        if "bge-reranker-v2-m3" in preview_model.lower():
                            model_name = "BAAI/bge-reranker-v2-m3"
                        elif "gte-multilingual" in preview_model.lower():
                            model_name = "Alibaba-NLP/gte-multilingual-reranker-base"
                        else:
                            model_name = "BAAI/bge-reranker-v2-m3"
                    else:
                        model_name = preview_model
            else:
                if not ("/" in preview_model or "\\" in preview_model or ".gguf" in preview_model):
                    model_name = preview_model

            # Prepare page data as list of (page_num, text)
            page_data = []
            for i in pages_to_scan:
                if 0 <= i < len(doc):
                    page_data.append((i, doc[i].get_text("text")))


            # Execute with context manager to automatically start and stop the server
            with HybridSearchPipeline(
                backend=backend,
                model_name=model_name,
                api_url=api_url,
                server_model_path=server_model_path
            ) as pipeline:
                # Run the hybrid search
                top_results = pipeline.search(query, entity_type, page_data, top_k=10)

            # Map back to expected output: [(page_index, score), ...]
            candidates = [(res["page_num"], res["score"]) for res in top_results]
            print(f"  [Preview] Cross-Encoder Reranker completed. Found {len(candidates)} candidate pages.", flush=True)
            return candidates
        except Exception as e:
            print(f"  [Preview] Cross-Encoder initialization/search failed: {e}. Returning empty candidate list.")
            return []

    # Standard Generative Prompt (Old Fallback logic)
    candidates = []

    print(f"  [Preview] Scanning {len(pages_to_scan)} pages (generative prompt)...")
    consecutive_failures = 0
    for i in pages_to_scan:
        if i < 0 or i >= len(doc):
            continue
        max_text_len = 1000 if preview_provider == "llama_cpp" else 4000
        text = doc[i].get_text("text").replace('\n', ' ')[:max_text_len]
        prompt = (
            "Задача: определить, содержит ли эта страница вводящую формулировку для термина '%s', где сущность непосредственно задаётся. "
            "ИЩИ явные маркеры: заголовки \"Определение\"/\"Definition\", вводные фразы \"называется\", \"будем называть\", \"определяется как\", \"обозначим\", записи вида \"X := ...\" или конструкции \"X - это ...\". "
            "Верни ТОЛЬКО корректный JSON: {\"found\": true, \"confidence\": 0.0-1.0, \"reason\": \"короткое объяснение, например 'заголовок + называется'\", \"snippet\": \"до 400 символов\", \"page_ref\": N}.\n\n"
            "Page text:\n%s"
        ) % (query, text)

        try:
            mgr = ModelManager.get_instance()
            resp = mgr.query_llm(prompt, json_mode=True, role="preview")
            if not resp:
                consecutive_failures += 1
                if consecutive_failures >= 3:
                    print(f"  [Preview] WARNING: Preview model '{preview_model}' is returning empty responses. Is it pulled/running?")
                    break
                continue

            parsed = json.loads(resp)
            consecutive_failures = 0
            if isinstance(parsed, dict) and parsed.get('found'):
                try:
                    score = float(parsed.get('confidence', 0.5))
                except Exception:
                    score = 0.5
                candidates.append((i, score))
                print(f"  [Preview] Page {i+1}: MATCH (confidence: {score:.2f})")
        except Exception as e:
            consecutive_failures += 1
            if consecutive_failures >= 3:
                print(f"  [Preview] WARNING: Preview scan failing repeatedly: {e}. Aborting scan.")
                break

    doc.close()

    candidates.sort(key=lambda x: x[1], reverse=True)
    print(f"  [Preview] Found {len(candidates)} candidate pages.")
    return candidates


def process_single_book(pdf_path: Path, query: str, entity_type: str, roots: list,
                        model: str, preview_provider: str = None, preview_model: str = None) -> list:
    """
    Two-phase search on a single PDF.
    Returns list of extracted formulations.
    """
    if not pdf_path.exists():
        print(f"  [SKIP] Файл {pdf_path.name} не найден (перемещен/удален).")
        return []

    book_id = extract_book_id(pdf_path)
    print(f"\n  ── {book_id} ({pdf_path.name}) ──")

    target_pages = []

    # Preview: build candidate pages from top-scored fitz matches and sample 20 random from them
    candidate_pages = None
    if preview_model and preview_provider:
        print("  [Preview] Building candidate page set from fitz matches...")
        try:
            # Переиспользуем кэш текста страниц (без повторного открытия/парсинга PDF).
            page_texts = pdf_text.get_page_texts(pdf_path)
            roots_lower = [r.lower() for r in roots]
            scored_pages = []

            for i, text in enumerate(page_texts):
                matched_roots = [r for r in roots_lower if r in text]
                if matched_roots:
                    scored_pages.append((len(matched_roots), i))

            if scored_pages:
                # Sort by score descending then page ascending
                scored_pages.sort(key=lambda x: (-x[0], x[1]))
                # Include ALL matched pages (no sampling) per user request
                candidate_pages = [p for s, p in scored_pages]
                print(f"  [Preview] {len(scored_pages)} pages matched roots; including all {len(candidate_pages)} pages for preview.")
            else:
                candidate_pages = list(range(len(page_texts)))
                print(f"  [Preview] No root matches; scanning all {len(page_texts)} pages.")

            print("  [Preview] Running preview scan on sampled pages...", flush=True)
            try:
                preview_hits = preview_scan(pdf_path, query, preview_provider, preview_model, candidate_pages=candidate_pages, entity_type=entity_type)
                if preview_hits:
                    # preview_hits is list of (page, score) tuples sorted by score desc
                    top_n = 10
                    print(f"  [Preview] Candidate pages (top {top_n} by confidence): {[ (p+1, f'{s:.2f}') for p,s in preview_hits[:top_n]]}", flush=True)
                    target_pages = [p for p, s in preview_hits[:top_n]]
            except Exception as e:
                print(f"  [Preview] Error during preview scan: {e}", flush=True)
        except Exception as e:
            print(f"  [Preview] Error building candidates: {e}", flush=True)

    # Fallback to ToC/fulltext only if preview is disabled or returned nothing
    if not target_pages:
        print("  [Search] Using traditional search (ToC + fulltext)...")
        toc = build_toc_index(pdf_path)

        if toc:
            toc_hits = search_toc(toc, roots)
            if toc_hits:
                print(f"  [ToC] Совпадения в оглавлении: {[t[1] for t in toc_hits]}")
                for page, title in toc_hits:
                    target_pages.append(page)

        # Fallback to fulltext if still empty
        if not target_pages:
            print(f"  [Fulltext] Searching by roots {roots}...")
            target_pages = search_fulltext(pdf_path, roots, max_pages=7)

    if not target_pages:
        print("  [SKIP] Термин не найден.", flush=True)
        return []

    print(f"  [+] Целевые страницы: {[p + 1 for p in target_pages]}", flush=True)

    # Extract and parse
    results = []
    seen_pages = set()
    for page_idx in target_pages:
        if page_idx in seen_pages:
            continue
        seen_pages.add(page_idx)

        raw_text = extract_context_window(pdf_path, page_idx, entity_type)
        print(f"  [*] LLM-анализ стр. {page_idx + 1}...", flush=True)
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
            print(f"  [OK] Извлечено (стр. {page_ref}).", flush=True)
        else:
            print("  [SKIP] LLM: нерелевантный фрагмент.", flush=True)

    return results


def gather_implicit_assumptions(book_id: str, page_idx: int, query: str, model="llama3.1:8b") -> str:
    """
    Looks back at previous pages (up to 5 pages) to find implicit type assumptions
    and mathematical context for the current entity (e.g. 'Let f be a continuous function').
    """
    pdf_map = {
        "zorich": "Zorich, V.A. - Mathematical Analysis Vol 1 - (RU) - [10th ed].pdf",
        "apostol": "Apostol, T.M. - Calculus Vol 1 - (EN) - [1991].pdf",
        "spivak": "Spivak, M. - Calculus - (EN).pdf"
    }

    if book_id not in pdf_map:
        return ""

    pdf_path = BOOKS_DIR / pdf_map[book_id]
    if not pdf_path.exists():
        return ""

    start_page = max(0, page_idx - 5)

    import fitz
    doc = fitz.open(pdf_path)
    end_page = min(len(doc) - 1, page_idx)

    text_blocks = []
    for p in range(start_page, end_page + 1):
        page = doc[p]
        text = page.get_text()
        # Very simple heuristic: stop going back if we hit a chapter boundary
        # We process pages forward, so if chapter is found, we truncate earlier pages.
        if re.search(r'\b(Chapter|Глава)\s+\d+', text, re.IGNORECASE):
            text_blocks = [] # Reset, only take from this chapter forward
        text_blocks.append(text)

    doc.close()

    combined_text = "\n".join(text_blocks)
    if not combined_text.strip():
        return ""

    prompt = f"""You are a mathematical context analyzer.
We are trying to formulate a rigorous definition/theorem for: "{query}".
However, the author might have defined variables or conventions earlier in the chapter.

Read the following preceding pages from the textbook:
{combined_text[:8000]}

Task: Extract any IMPLICIT ASSUMPTIONS, TYPE DECLARATIONS, or GLOBAL CONVENTIONS that apply to the current context.
For example: "Throughout this section, f is a continuous function from R to R" or "Let V be a vector space".
Return ONLY the extracted mathematical conditions as plain text. If none are found, return exactly: NONE.
"""
    mgr = ModelManager.get_instance()
    response = mgr.query_llm(prompt, role="extract")

    if not response or response.strip().upper() == "NONE":
        return ""

    return response.strip()

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
    # ── Preview (fast page scan) provider for scanning all pages before full parse
    parser.add_argument("--extract-preview-provider", type=str, default=None, choices=PROVIDERS,
                        help="Провайдер LLM для предпросмотра (быстрая фильтрация страниц)")
    parser.add_argument("--extract-preview-model",    type=str, default=None,
                        help="Модель LLM для предпросмотра")
    parser.add_argument("--extract-preview-api-key",  type=str, default=None,
                        help="API ключ для предпросмотра")

    # ── Lean-аргументы (для консистентности при запуске через ollama_wrapper) -
    parser.add_argument("--lean-provider", type=str, default=None, choices=PROVIDERS, help="Игнорируется в этом модуле")
    parser.add_argument("--lean-api-key",  type=str, default=None, help="Игнорируется в этом модуле")
    parser.add_argument("--lean-model",    type=str, default=None, help="Игнорируется в этом модуле")

    # ── OCR Pages Override ────────────────────────────────────────────────────
    parser.add_argument("--ocr-pages", type=str, default=None,
                        help='Skip search and process only specified pages. Format: JSON {"book": "zorich", "pages": [1, 2, 3]} or comma-separated "1,2,3" (first book)')

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

    # Preview provider config
    preview_provider, preview_model, preview_api_key = resolve_module_config(
        module="preview",
        global_provider=args.provider,
        global_model=args.model,
        global_api_key=args.api_key,
        module_provider=args.extract_preview_provider,
        module_model=args.extract_preview_model,
        module_api_key=args.extract_preview_api_key,
    )

    # Initialize LLM provider via shared logic
    mgr = ModelManager.get_instance()
    mgr.setup_role("extract", provider, model, api_key)
    # Initialize preview provider (separate client) - bypass if it is a Cross-Encoder
    is_cross_encoder = False
    if preview_provider:
        is_cross_encoder = (
            preview_provider == "llama_cpp" or
            (preview_model and "reranker" in preview_model.lower()) or
            (preview_model and "gte-multilingual" in preview_model.lower())
        )

    if preview_provider and not is_cross_encoder:
        mgr.setup_role("preview", preview_provider, preview_model, preview_api_key)

    active_provider_name = (provider or "OLLAMA").upper()
    print(f"[*] Провайдер: {active_provider_name} ({model})")
    if preview_provider:
        print(f"[*] Preview провайдер: {preview_provider.upper()} ({preview_model})")

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
    conn = sqlite3.connect(DB_PATH, timeout=10.0)
    cursor = conn.cursor()
    cursor.execute("""
        CREATE TABLE IF NOT EXISTS formulation_raw_cache (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            discipline TEXT,
            source_book TEXT NOT NULL,
            raw_text TEXT NOT NULL,
            entity_type TEXT DEFAULT 'definition',
            has_proof INTEGER DEFAULT 0,
            page_ref INTEGER,
            raw_deps TEXT,
            temp_cluster_id TEXT
        )
    """)
    # Ensure legacy DBs have the new columns
    cols = [r[1] for r in cursor.execute("PRAGMA table_info(formulation_raw_cache)").fetchall()]
    if 'entity_type' not in cols:
        try:
            cursor.execute("ALTER TABLE formulation_raw_cache ADD COLUMN entity_type TEXT DEFAULT 'definition'")
        except Exception:
            pass
    if 'has_proof' not in cols:
        try:
            cursor.execute("ALTER TABLE formulation_raw_cache ADD COLUMN has_proof INTEGER DEFAULT 0")
        except Exception:
            pass
    if 'page_ref' not in cols:
        try:
            cursor.execute("ALTER TABLE formulation_raw_cache ADD COLUMN page_ref INTEGER")
        except Exception:
            pass
    if 'raw_deps' not in cols:
        try:
            cursor.execute("ALTER TABLE formulation_raw_cache ADD COLUMN raw_deps TEXT")
        except Exception:
            pass

    # Clear stale cache from previous (possibly interrupted) runs
    cursor.execute("DELETE FROM formulation_raw_cache")
    conn.commit()
    print("[*] Кэш формулировок очищен.")

    total_count = 0

    # Parse OCR pages override if provided
    ocr_pages_override = None
    if args.ocr_pages:
        try:
            if args.ocr_pages.startswith('{'):
                # JSON format: {"book": "zorich", "pages": [1, 2, 3]}
                ocr_spec = json.loads(args.ocr_pages)
                target_book = ocr_spec.get("book", "").lower()
                ocr_pages_override = {
                    "book": target_book,
                    "pages": set(ocr_spec.get("pages", []))
                }
            else:
                # Comma-separated format: "1,2,3" (first book)
                page_list = [int(p.strip()) - 1 for p in args.ocr_pages.split(",") if p.strip().isdigit()]  # Convert to 0-indexed
                ocr_pages_override = {
                    "book": extract_book_id(all_books[0]) if all_books else "",
                    "pages": set(page_list)
                }
            if ocr_pages_override:
                print(f"[*] OCR-страницы переопределены: книга '{ocr_pages_override['book']}', страницы: {sorted(ocr_pages_override['pages'])}")
        except Exception as e:
            print(f"[-] Ошибка парсинга --ocr-pages: {e}. Игнорирую и продолжу обычный поиск.")
            ocr_pages_override = None

    for pdf_path in all_books:
        # If OCR pages override is specified, check if this is the target book
        if ocr_pages_override:
            book_id = extract_book_id(pdf_path)
            if book_id != ocr_pages_override["book"]:
                print(f"\n  ── {book_id} ({pdf_path.name}) [SKIP: not in OCR override] ──")
                continue

            # Process only specified pages
            print(f"\n  ── {book_id} ({pdf_path.name}) [OCR override: processing {len(ocr_pages_override['pages'])} pages] ──")
            target_pages = sorted(list(ocr_pages_override["pages"]))
        else:
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

            # Normal search flow (not OCR override)
            results = process_single_book(pdf_path, active_query, entity_type, active_roots, model, preview_provider=preview_provider, preview_model=preview_model)

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
                    "INSERT INTO formulation_raw_cache (discipline, source_book, raw_text, entity_type, has_proof, page_ref, raw_deps) "
                    "VALUES (?, ?, ?, ?, ?, ?, ?)",
                    ("global", res["source"], full_text, entity_type, has_proof, res.get("page_ref", 0), json.dumps(res.get("deps", []), ensure_ascii=False))
                )
                total_count += 1

            continue  # Move to next book (search mode)

        # OCR override mode: process specified pages directly
        if ocr_pages_override:
            for page_idx in target_pages:
                try:
                    import fitz
                    doc = fitz.open(pdf_path)
                    if page_idx < 0 or page_idx >= len(doc):
                        print(f"  [SKIP] Страница {page_idx+1} вне пределов PDF.")
                        continue

                    raw_text = extract_context_window(pdf_path, page_idx, entity_type)
                    result = parse_with_llm(raw_text, query_ru or query_en, entity_type, model=model)

                    if result.get("found"):
                        result["source"] = extract_book_id(pdf_path)
                        print(f"  [OK] Страница {page_idx+1}: извлечено.")

                        text_parts = []
                        if result.get("context"):
                            text_parts.append(f"[КОНТЕКСТ]: {result['context']}")
                        text_parts.append(f"[ФОРМУЛИРОВКА]: {result['statement']}")
                        if result.get("proof"):
                            text_parts.append(f"[ДОКАЗАТЕЛЬСТВО]: {result['proof']}")

                        full_text = "\n\n".join(text_parts)
                        cursor.execute(
                            "INSERT INTO formulation_raw_cache (discipline, source_book, raw_text, entity_type, has_proof, page_ref, raw_deps) "
                            "VALUES (?, ?, ?, ?, ?, ?, ?)",
                            ("global", result["source"], full_text, entity_type, int(bool(result.get("proof"))), result.get("page_ref", page_idx+1), json.dumps(result.get("deps", []), ensure_ascii=False))
                        )
                        total_count += 1
                    else:
                        print(f"  [SKIP] Страница {page_idx+1}: не найдено соответствие.")

                    doc.close()
                except Exception as e:
                    print(f"  [ERROR] Страница {page_idx+1}: {e}")

    conn.commit()
    conn.close()
    print(f"\n[*] Ensemble extraction complete. Извлечено формулировок: {total_count}")


if __name__ == "__main__":
    main()
