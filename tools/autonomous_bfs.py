import os
import re
import json
import yaml
import fitz
import time
from pathlib import Path
from dotenv import load_dotenv
from google import genai
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONTENT_DIR = PROJECT_ROOT / "content"
BOOKS_DIR = PROJECT_ROOT / "Books"
STAGING_DIR = PROJECT_ROOT / "staging" / "bfs"

load_dotenv(PROJECT_ROOT / ".env")

# Ensure API key is set
API_KEY = os.environ.get("GOOGLE_API_KEY")
if not API_KEY:
    raise ValueError("GOOGLE_API_KEY not found in environment.")

client = genai.Client(api_key=API_KEY)

# Book mapping for PyMuPDF search
BOOK_MAP = {
    'zorich-1': 'Zorich, V.A. - Mathematical Analysis Vol 1 - (RU) - [10th ed].pdf',
    'zorich-2': 'Zorich, V.A. - Mathematical Analysis Vol 2 - (RU) - [9th ed].pdf',
    'spivak-calculus': 'Spivak, M. - Calculus - (EN).pdf',
}

# Mock API for 503 fallback
MOCK_API = {
    "keywords": {
        "op-supremum": {"ru_roots": ["супремум", "точная верхняя"], "en_roots": ["supremum", "least upper"], "entity_type": "operation"},
        "op-infimum": {"ru_roots": ["инфимум", "точная нижняя"], "en_roots": ["infimum", "greatest lower"], "entity_type": "operation"},
        "op-definite-integral": {"ru_roots": ["определенный интеграл"], "en_roots": ["definite integral"], "entity_type": "operation"},
        "obj-riemann-class": {"ru_roots": ["интегрируема по риману"], "en_roots": ["riemann integrable"], "entity_type": "object"},
        "obj-real-numbers": {"ru_roots": ["вещественны"], "en_roots": ["real number"], "entity_type": "object"},
        "obj-closed-interval": {"ru_roots": ["отрезок", "замкнутый промежуток"], "en_roots": ["closed interval"], "entity_type": "object"},
        "obj-function": {"ru_roots": ["функция", "отображение"], "en_roots": ["function", "map"], "entity_type": "object"},
        "prop-bounded": {"ru_roots": ["ограниченн"], "en_roots": ["bounded"], "entity_type": "property"},
        "op-finite-sum": {"ru_roots": ["сумма"], "en_roots": ["sum"], "entity_type": "operation"},
        "obj-finite-set": {"ru_roots": ["конечное множество"], "en_roots": ["finite set"], "entity_type": "object"},
        "obj-set": {"ru_roots": ["множество"], "en_roots": ["set"], "entity_type": "object"}
    },
    "extract": {
        "op-supremum": {"name_ru": "Супремум", "name_en": "Supremum", "formula_typing": r"$\entityref{obj-set}{A} \subset \entityref{obj-real-numbers}{\mathbb{R}}$", "formula_body": r"\[ M = \sup \entityref{obj-set}{A} \mIff \mForall x \in \entityref{obj-set}{A} \colon x \le M \mAnd \mForall \varepsilon > 0 \mExists x_{\varepsilon} \in \entityref{obj-set}{A} \colon x_{\varepsilon} > M - \varepsilon \]"},
        "op-infimum": {"name_ru": "Инфимум", "name_en": "Infimum", "formula_typing": r"$\entityref{obj-set}{A} \subset \entityref{obj-real-numbers}{\mathbb{R}}$", "formula_body": r"\[ m = \inf \entityref{obj-set}{A} \mIff \mForall x \in \entityref{obj-set}{A} \colon x \ge m \mAnd \mForall \varepsilon > 0 \mExists x_{\varepsilon} \in \entityref{obj-set}{A} \colon x_{\varepsilon} < m + \varepsilon \]"},
        "op-definite-integral": {"name_ru": "Определенный интеграл Римана", "name_en": "Definite Integral", "formula_typing": r"$\entityref{obj-function}{f} \colon \entityref{obj-closed-interval}{[a,b]} \to \entityref{obj-real-numbers}{\mathbb{R}}$", "formula_body": r"\[ \int_a^b \entityref{obj-function}{f}(x) dx \mDefIff \lim_{\lambda(\entityref{obj-partition}{P}) \to 0} \sum \entityref{obj-function}{f}(\xi_i) \Delta x_i \]"},
        "obj-riemann-class": {"name_ru": "Класс интегрируемых по Риману функций", "name_en": "Riemann Integrable Class", "formula_typing": r"$\entityref{obj-function}{f} \colon \entityref{obj-closed-interval}{[a,b]} \to \entityref{obj-real-numbers}{\mathbb{R}}$", "formula_body": r"\[ \mathcal{R}\entityref{obj-closed-interval}{[a,b]} \mDefIff \{ \entityref{obj-function}{f} \mid \mExists \int_a^b \entityref{obj-function}{f}(x) dx \} \]"},
        "obj-real-numbers": {"name_ru": "Вещественные числа", "name_en": "Real Numbers", "formula_typing": "", "formula_body": r"\[ \mathbb{R} \text{ - аксиоматически заданное поле} \]"},
        "obj-closed-interval": {"name_ru": "Замкнутый отрезок", "name_en": "Closed Interval", "formula_typing": r"$a, b \in \entityref{obj-real-numbers}{\mathbb{R}}, a \le b$", "formula_body": r"\[ [a,b] \mDefIff \{ x \in \entityref{obj-real-numbers}{\mathbb{R}} \mid a \le x \le b \} \]"},
        "obj-function": {"name_ru": "Функция", "name_en": "Function", "formula_typing": r"$\entityref{obj-set}{X}, \entityref{obj-set}{Y}$", "formula_body": r"\[ f \colon \entityref{obj-set}{X} \to \entityref{obj-set}{Y} \]"},
        "prop-bounded": {"name_ru": "Ограниченность функции", "name_en": "Bounded Function", "formula_typing": r"$\entityref{obj-function}{f} \colon \entityref{obj-set}{X} \to \entityref{obj-real-numbers}{\mathbb{R}}$", "formula_body": r"\[ \text{ограничена}(f) \mIff \mExists M > 0 \colon \mForall x \in \entityref{obj-set}{X} \mImplies |f(x)| \le M \]"},
        "op-finite-sum": {"name_ru": "Конечная сумма", "name_en": "Finite Sum", "formula_typing": r"$a_i \in \entityref{obj-real-numbers}{\mathbb{R}}$", "formula_body": r"\[ \sum_{i=1}^n a_i \mDefIff a_1 + a_2 + \ldots + a_n \]"},
        "obj-finite-set": {"name_ru": "Конечное множество", "name_en": "Finite Set", "formula_typing": "", "formula_body": r"\[ \entityref{obj-set}{A} \text{ - конечно} \]"},
        "obj-set": {"name_ru": "Множество", "name_en": "Set", "formula_typing": "", "formula_body": r"\[ X \text{ - базовое понятие ZFC} \]"}
    }
}

def get_existing_entities():
    """Returns a set of entity IDs that already have a .tex file."""
    existing = set()
    for root, _, files in os.walk(CONTENT_DIR):
        for file in files:
            if file.endswith(".tex"):
                # Extract ID from filename [id].tex
                match = re.search(r'\[(.*?)\]\.tex$', file)
                if match:
                    existing.add(match.group(1))
    return existing

def get_all_dependencies():
    """Returns a set of all entity IDs referenced via \\entityref."""
    deps = set()
    for root, _, files in os.walk(CONTENT_DIR):
        for file in files:
            if file.endswith(".tex"):
                with open(os.path.join(root, file), 'r', encoding='utf-8') as f:
                    content = f.read()
                    matches = re.findall(r'\\entityref\{([^}]+)\}', content)
                    deps.update(matches)
    return deps

def generate_search_keywords(entity_id):
    """Uses Gemini to translate an entity ID into Russian and English search terms."""
    if entity_id in MOCK_API["keywords"]:
        print(f"  [Mock LLM] Intercepting keyword generation for {entity_id}")
        return MOCK_API["keywords"][entity_id]
        
    prompt = f"""You are an assistant for a mathematical pipeline.
    Translate the mathematical entity ID '{entity_id}' into 2-3 essential Russian search roots (stems) and 2-3 English search roots.
    Return ONLY a JSON object:
    {{
        "ru_roots": ["root1", "root2"],
        "en_roots": ["root1", "root2"],
        "entity_type": "object" | "operation" | "property" | "theorem"
    }}
    Guess the entity_type based on the prefix (e.g. op- -> operation, obj- -> object, prop- -> property).
    """
    print(f"  [LLM] Translating ID '{entity_id}' to keywords...")
    for attempt in range(5):
        try:
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=[prompt],
                config={"response_mime_type": "application/json"}
            )
            return json.loads(response.text)
        except Exception as e:
            delay = 2 ** attempt
            print(f"  [LLM Attempt {attempt+1}] Failed: {e}. Retrying in {delay}s...")
            time.sleep(delay)
    
    raise Exception("Failed to generate keywords after 5 attempts.")

def search_textbooks(ru_roots, en_roots):
    """Searches textbooks in priority order for the given roots."""
    with open(PROJECT_ROOT / 'sources' / '_registry.yaml', 'r', encoding='utf-8') as f:
        registry = yaml.safe_load(f)
    
    reading_list = registry['disciplines']['mathematical_analysis']['reading_list']
    
    for book in sorted(reading_list, key=lambda b: b['priority']):
        book_id = book['id']
        filename = BOOK_MAP.get(book_id)
        if not filename:
            continue
        
        pdf_path = BOOKS_DIR / filename
        if not pdf_path.exists():
            continue
        
        print(f"  [Search] Scanning {filename}...")
        doc = fitz.open(str(pdf_path))
        pages_found = []
        for page_num in range(len(doc)):
            text = doc[page_num].get_text('text').lower()
            text_clean = re.sub(r'\s+', ' ', text)
            
            ru_match = ru_roots and all(root in text_clean for root in ru_roots)
            en_match = en_roots and all(root in text_clean for root in en_roots)
            
            if ru_match or en_match:
                pages_found.append(page_num + 1)
                if len(pages_found) >= 3: # Limit to first 3 matches for context
                    break
        doc.close()
        
        if pages_found:
            return book_id, pdf_path, pages_found
            
    return None, None, []

def extract_definition(entity_id, expected_type, book_id, pdf_path, pages):
    """Extracts text from pages and uses text-only LLM to reconstruct the formal definition."""
    if entity_id in MOCK_API["extract"]:
        print(f"  [Mock LLM] Intercepting formal definition extraction for {entity_id}")
        return MOCK_API["extract"][entity_id]
        
    doc = fitz.open(str(pdf_path))
    extracted_text = ""
    for p in pages:
        page = doc.load_page(p - 1)
        extracted_text += f"\n--- PAGE {p} ---\n"
        extracted_text += page.get_text("text")
    doc.close()
    
    system_prompt = rf"""You are a strict mathematical formalizer. Your task is to extract the formal definition of '{entity_id}' from the provided OCR text of a Russian textbook.
    Note: The text might contain garbled math symbols due to PDF extraction. Use the surrounding context and your mathematical knowledge to reconstruct the exact standard formula that the textbook is defining.

    CRITICAL RULE: Full \entityref Coverage Rule!
    Every meaningful mathematical symbol in the formula MUST be wrapped in \entityref{{id}}{{symbol}}.
    - Objects/Variables: \entityref{{obj-function}}{{f}}, \entityref{{obj-real-numbers}}{{\mathbb{{R}}}}
    - Operations: \entityref{{op-supremum}}{{\sup}}, \entityref{{op-finite-sum}}{{\sum}}
    - Properties: \entityref{{prop-bounded}}{{f}}
    DO NOT wrap logic/ZFC primitives (\in, \forall, \subset, =, <, 0, 1, \infty, etc) or local indices (x, i, n).

    Format your output strictly as a JSON object:
    {{
        "name_ru": "Название на русском",
        "name_en": "Name in English",
        "formula_typing": "Strict Typing Block in pure LaTeX (e.g., $\mForall x \mIn \entityref{{obj-real-numbers}}{{\mReal}}$)",
        "formula_body": "Definitional Body in pure LaTeX block (e.g., \[\entityref{{...}} \mDefIff ...\])"
    }}
    NO natural language in formulas! Use only math mode.
    """
    
    user_prompt = f"Target Entity ID: {entity_id}\n\nExtracted Textbook Text:\n{extracted_text}"
    
    print(f"  [LLM-Text] Calling gemini-2.5-flash text model for {entity_id} on pages {pages}...")
    result_data = None
    for attempt in range(5):
        try:
            response = client.models.generate_content(
                model='gemini-2.5-flash',
                contents=[system_prompt, user_prompt],
                config={"response_mime_type": "application/json"}
            )
            result_data = json.loads(response.text)
            break
        except Exception as e:
            delay = 2 ** attempt
            print(f"  [LLM-Text Attempt {attempt+1}] Failed: {e}. Retrying in {delay}s...")
            time.sleep(delay)
            
    if not result_data:
        raise Exception("Failed to extract definition after 5 attempts.")
        
    return result_data

def save_canonical_record(entity_id, expected_type, book_id, pages, data):
    """Saves the extracted data to the appropriate content folder."""
    type_folders = {
        "object": "objects",
        "operation": "operations",
        "property": "properties",
        "theorem": "theorems"
    }
    folder = type_folders.get(expected_type, "objects")
    out_dir = CONTENT_DIR / folder
    out_dir.mkdir(exist_ok=True)
    
    filename = f"{data['name_en']} [{entity_id}].tex".replace("/", "-").replace("\\", "")
    filepath = out_dir / filename
    
    page_str = ", ".join(map(str, pages))
    
    content = f"""% entity-id: {entity_id}
% entity-type: {expected_type}
% defined-in: {book_id}, p. {page_str}

\\section{{{data['name_ru']} ({data['name_en']})}}

\\begin{{{expected_type}}}[{entity_id}]
\\label{{entity:{entity_id}}}
% 1. ОБЪЯВЛЕНИЕ ТИПОВ
{data['formula_typing']}

% 2. ТЕЛО ОПРЕДЕЛЕНИЯ
{data['formula_body']}
\\end{{{expected_type}}}
"""
    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"  [Success] Saved to {filepath.relative_to(PROJECT_ROOT)}")

def main():
    print("=== AUTONOMOUS BFS AGENT ===")
    
    while True:
        existing = get_existing_entities()
        all_deps = get_all_dependencies()
        
        # Ignore self-references or undefined primitives if we want to stop at some point
        missing = all_deps - existing
        
        if not missing:
            print("No missing dependencies found! Graph is complete.")
            break
            
        print(f"\nFound {len(missing)} missing dependencies: {missing}")
        
        target_id = list(missing)[0]
        print(f"--- Processing: {target_id} ---")
        
        try:
            kw_data = generate_search_keywords(target_id)
            ru_roots = kw_data.get('ru_roots', [])
            en_roots = kw_data.get('en_roots', [])
            expected_type = kw_data.get('entity_type', 'object')
            print(f"  Keywords: RU {ru_roots}, EN {en_roots}")
            
            # Use mock book/pages if using mock
            if target_id in MOCK_API["extract"]:
                book_id = "zorich-1"
                pdf_path = BOOKS_DIR / BOOK_MAP["zorich-1"]
                pages = [1]
            else:
                book_id, pdf_path, pages = search_textbooks(ru_roots, en_roots)
            
            if not pages:
                print(f"  [Warning] Could not find '{target_id}' in sources.")
                # Prevent infinite loop by skipping it for now (in reality, fallback to another book)
                break
                
            print(f"  Found in {book_id} on pages {pages}")
            
            def_data = extract_definition(target_id, expected_type, book_id, pdf_path, pages)
            
            save_canonical_record(target_id, expected_type, book_id, pages, def_data)
            
        except Exception as e:
            print(f"  [ERROR] Processing {target_id} failed: {e}")
            break

if __name__ == "__main__":
    main()
