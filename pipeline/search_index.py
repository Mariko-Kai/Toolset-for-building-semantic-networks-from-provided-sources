import argparse
import json
import re
import os
from pathlib import Path
import yaml
import fitz  # PyMuPDF
from google import genai
from dotenv import load_dotenv

PROJECT_ROOT = Path(__file__).resolve().parent.parent
BOOKS_DIR = PROJECT_ROOT / "Books"
INDEX_FILE = PROJECT_ROOT / "pipeline" / "book_index_cache.json"
REGISTRY_FILE = PROJECT_ROOT / "sources" / "_registry.yaml"

# Need to import BOOK_REGISTRY to map id -> filename
import sys
sys.path.append(str(PROJECT_ROOT))
from pipeline.pdftoimages.pdf_to_images import BOOK_REGISTRY

load_dotenv(PROJECT_ROOT / ".env")

def get_ranked_books(discipline="mathematical_analysis"):
    """Reads registry and returns ordered list of book keys."""
    with open(REGISTRY_FILE, "r", encoding="utf-8") as f:
        registry = yaml.safe_load(f)
    
    books = registry.get("disciplines", {}).get(discipline, {}).get("reading_list", [])
    # Sort by priority
    books.sort(key=lambda x: x.get("priority", 999))
    return [b["id"] for b in books]

def translate_term(term: str, model_name: str = "gemini-2.5-flash") -> dict:
    """Uses LLM to translate term to English and provide root words for partial matching."""
    api_key = os.getenv("GOOGLE_API_KEY")
    if not api_key:
        print("Warning: GOOGLE_API_KEY not found. Using naive translation/roots.")
        return {"ru_roots": term.lower().split(), "en_roots": [term.lower()]}

    client = genai.Client(api_key=api_key)
    prompt = f"""
    Given the mathematical term: "{term}"
    1. If it's in Russian, translate it to English. If it's in English, translate to Russian.
    2. Provide the word roots (stems) for both the Russian and English versions to allow partial regex matching in text where the words might be in different grammatical cases.
    Output JSON format strictly:
    {{
        "ru_roots": ["root1", "root2"],
        "en_roots": ["root1", "root2"]
    }}
    Example for "аналитическая функция":
    {{
        "ru_roots": ["аналитическ", "функци"],
        "en_roots": ["analytic", "function"]
    }}
    """
    
    try:
        response = client.models.generate_content(
            model=model_name,
            contents=prompt,
            config={"response_mime_type": "application/json"}
        )
        data = json.loads(response.text)
        return data
    except Exception as e:
        print(f"Error calling LLM or parsing response (using fallback): {e}")
        # Naive fallback for "аналитическая функция"
        if "аналитическая" in term.lower() and "функция" in term.lower():
            return {"ru_roots": ["аналитическ", "функци"], "en_roots": ["analytic", "function"]}
        return {"ru_roots": term.lower().split(), "en_roots": [term.lower()]}

def build_or_load_index(pdf_path: Path, force_rebuild: bool = False):
    """Builds a simple full-text cache for the book to speed up regex searches."""
    cache_key = pdf_path.name
    
    if not force_rebuild and INDEX_FILE.exists():
        with open(INDEX_FILE, "r", encoding="utf-8") as f:
            cache = json.load(f)
            if cache_key in cache:
                return cache[cache_key]
    else:
        cache = {}

    print(f"  Building index for {pdf_path.name}...")
    doc = fitz.open(str(pdf_path))
    pages_text = []
    for i in range(len(doc)):
        text = doc[i].get_text("text").lower()
        text = re.sub(r'\s+', ' ', text)
        pages_text.append(text)
    doc.close()
    
    cache[cache_key] = pages_text
    with open(INDEX_FILE, "w", encoding="utf-8") as f:
        json.dump(cache, f, ensure_ascii=False)
    return pages_text

def search_in_book(pdf_path: Path, roots: list[str]) -> list[int]:
    pages_text = build_or_load_index(pdf_path)
    results = []
    
    for i, text in enumerate(pages_text):
        if all(root in text for root in roots):
            results.append(i + 1)
            
    return results

def main():
    parser = argparse.ArgumentParser(description="Search for a math term across ranked textbooks")
    parser.add_argument("--query", type=str, required=True, help="Term to search for")
    parser.add_argument("--discipline", type=str, default="mathematical_analysis", help="Discipline key from registry")
    parser.add_argument("--model", type=str, default="gemini-2.5-flash", choices=["gemini-2.5-pro", "gemini-2.5-flash", "gemini-1.5-pro", "gemini-1.5-flash"], help="Gemini model to use for query translation")
    
    args = parser.parse_args()
    
    print(f"Translating and analyzing roots for: '{args.query}' (using {args.model})...")
    term_data = translate_term(args.query, args.model)
    print(f"  Russian roots: {term_data.get('ru_roots')}")
    print(f"  English roots: {term_data.get('en_roots')}\n")
    
    ranked_books = get_ranked_books(args.discipline)
    print(f"Searching in ranked order for discipline '{args.discipline}':")
    
    found_pages = {}
    
    for book_id in ranked_books:
        book_info = BOOK_REGISTRY.get(book_id)
        if not book_info or not book_info.get("file"):
            continue
            
        filename = book_info["file"]
        lang = book_info.get("lang", "ru").lower()
        pdf_path = BOOKS_DIR / filename
        
        if not pdf_path.exists():
            print(f"  [MISSING] {filename}")
            continue
            
        print(f"  Checking {filename}...")
        roots = term_data.get("ru_roots") if "ru" in lang else term_data.get("en_roots")
        
        pages = search_in_book(pdf_path, roots)
        if pages:
            print(f"    => Found on pages: {pages}")
            found_pages[book_id] = pages
            # We can stop at the highest priority book that has the term, or continue.
            # Let's break after the first successful book to get the most authoritative definition.
            print(f"\nTerm found in highest priority available book ({book_id}). Stopping search.")
            break

if __name__ == "__main__":
    main()
