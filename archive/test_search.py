import sys
import os
from pathlib import Path

# Add project root to path
PROJECT_ROOT = Path(__file__).resolve().parent.parent
sys.path.append(str(PROJECT_ROOT))

from pipeline.search_index import translate_term, search_in_book, get_ranked_books, build_or_load_index
from pipeline.pdftoimages.pdf_to_images import BOOK_REGISTRY

def test():
    query = "аналитическая функция"
    discipline = "mathematical_analysis"
    
    # Bypass translation/encoding issues for this specific test
    term_data = {
        "ru_roots": ["\u0430\u043d\u0430\u043b\u0438\u0442\u0438\u0447\u0435\u0441\u043a", "\u0444\u0443\u043d\u043a\u0446\u0438"],
        "en_roots": ["analytic", "function"]
    }
    print(f"Russian roots: {term_data.get('ru_roots')}")
    print(f"English roots: {term_data.get('en_roots')}\n")
    
    ranked_books = get_ranked_books(discipline)
    
    for book_id in ranked_books:
        book_info = BOOK_REGISTRY.get(book_id)
        if not book_info or not book_info.get("file"):
            continue
            
        filename = book_info["file"]
        lang = book_info.get("lang", "ru").lower()
        pdf_path = PROJECT_ROOT / "Books" / filename
        
        if not pdf_path.exists():
            continue
            
        print(f"Checking {filename}...")
        roots = term_data.get("ru_roots") if "ru" in lang else term_data.get("en_roots")
        
        pages = search_in_book(pdf_path, roots)
        if pages:
            print(f"  => Found on pages: {pages}")
            break

if __name__ == "__main__":
    test()
