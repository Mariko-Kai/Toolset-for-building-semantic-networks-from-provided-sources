import os
import re
import json
import yaml
import fitz
import time
from pathlib import Path
import urllib.request
from PIL import Image

PROJECT_ROOT = Path(__file__).resolve().parent.parent
CONTENT_DIR = PROJECT_ROOT / "content"
BOOKS_DIR = PROJECT_ROOT / "Books"
STAGING_DIR = PROJECT_ROOT / "staging" / "bfs"

# load_dotenv(PROJECT_ROOT / ".env")

def query_ollama(prompt, model="llama3.1:8b", json_mode=False):
    """Sends a request to the local Ollama API."""
    url = "http://localhost:11434/api/generate"
    data = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "options": {
            "temperature": 0.2,
        }
    }
    if json_mode:
        data["format"] = "json"
    
    try:
        req = urllib.request.Request(url, json.dumps(data).encode('utf-8'), headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=120) as response:
            result = json.loads(response.read().decode('utf-8'))
            return result.get('response', '').strip()
    except Exception as e:
        print(f"  [Ollama Error] Check if Ollama is running: {e}")
        return ""

# Book mapping for PyMuPDF search
BOOK_MAP = {
    'zorich-1': 'Zorich, V.A. - Mathematical Analysis Vol 1 - (RU) - [10th ed].pdf',
    'zorich-2': 'Zorich, V.A. - Mathematical Analysis Vol 2 - (RU) - [9th ed].pdf',
    'spivak-calculus': 'Spivak, M. - Calculus - (EN).pdf',
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
    """Uses LLM to translate an entity ID into Russian and English search terms."""
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
            response_text = query_ollama(prompt, json_mode=True)
            if not response_text:
                raise Exception("Empty response from Ollama")
            return json.loads(response_text)
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
        "module": "The module this entity belongs to (e.g., 'operations', 'foundations', 'objects')",
        "formula_typing": "Strict Typing Block in pure LaTeX (e.g., $\mForall x \mIn \entityref{{obj-real-numbers}}{{\mReal}}$)",
        "formula_body": "Definitional Body in pure LaTeX block (e.g., \[\entityref{{op-abs-abstract}}{{\mathrm{{abs}}}}(x) \mDefIff ...\])",
        "nl_desc": "Natural language explanation of the entity in Russian."
    }}
    NO natural language in formulas! Use only math mode.
    All operations with paired symbols MUST use functional notation, e.g. \entityref{{op-abs-abstract}}{{\mathrm{{abs}}}}(x) instead of raw |x|, and \entityref{{op-norm-abstract}}{{\mathrm{{norm}}}}(x) instead of \|x\|.
    """
    
    user_prompt = f"Target Entity ID: {entity_id}\n\nExtracted Textbook Text:\n{extracted_text}"
    
    print(f"  [LLM-Text] Calling Ollama for {entity_id} on pages {pages}...")
    result_data = None
    for attempt in range(5):
        try:
            response_text = query_ollama(system_prompt + "\n\n" + user_prompt, json_mode=True)
            if not response_text:
                raise Exception("Empty response from Ollama")
            result_data = json.loads(response_text)
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
% module: {data.get('module', 'foundations')}

\\section{{{data['name_ru']} ({data['name_en']})}}

\\begin{{{expected_type}}}[{entity_id}]
\\label{{entity:{entity_id}}}
% 1. ОБЪЯВЛЕНИЕ ТИПОВ
{data['formula_typing']}

% 2. ТЕЛО ОПРЕДЕЛЕНИЯ
{data['formula_body']}
\\end{{{expected_type}}}
"""
    if data.get('nl_desc'):
        content += f"\n\\textbf{{Естественный язык:}}\n{data['nl_desc']}\n"

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(content)
    print(f"  [Success] Saved to {filepath.relative_to(PROJECT_ROOT)}")

    # Add to master.tex
    master_path = CONTENT_DIR / "master.tex"
    if master_path.exists():
        with open(master_path, "r", encoding="utf-8") as f:
            master_content = f.read()
        
        rel_path = filepath.relative_to(PROJECT_ROOT).as_posix()
        input_line = f"\\input{{{rel_path}}}"
        
        if input_line not in master_content:
            master_content = master_content.replace("\\end{document}", f"{input_line}\n\\end{{document}}")
            with open(master_path, "w", encoding="utf-8") as f:
                f.write(master_content)
            print(f"  [Success] Added to master.tex: {input_line}")

def expand_missing_entity(target_id):
    """Dynamically generates a missing entity using LLM and textbooks."""
    print(f"\n--- [Auto-Expansion] Processing: {target_id} ---")
    try:
        kw_data = generate_search_keywords(target_id)
        ru_roots = kw_data.get('ru_roots', [])
        en_roots = kw_data.get('en_roots', [])
        expected_type = kw_data.get('entity_type', 'object')
        print(f"  Keywords: RU {ru_roots}, EN {en_roots}")
        
        # Use book/pages found in search
        book_id, pdf_path, pages = search_textbooks(ru_roots, en_roots)
        
        if not pages:
            print(f"  [Warning] Could not find '{target_id}' in sources.")
            return False
            
        print(f"  Found in {book_id} on pages {pages}")
        
        def_data = extract_definition(target_id, expected_type, book_id, pdf_path, pages)
        
        save_canonical_record(target_id, expected_type, book_id, pages, def_data)
        return True
        
    except Exception as e:
        print(f"  [ERROR] Processing {target_id} failed: {e}")
        return False

def main():
    print("=== AUTONOMOUS BFS AGENT ===")
    
    while True:
        existing = get_existing_entities()
        all_deps = get_all_dependencies()
        
        missing = all_deps - existing
        
        if not missing:
            print("No missing dependencies found! Graph is complete.")
            break
            
        print(f"\nFound {len(missing)} missing dependencies: {missing}")
        
        target_id = list(missing)[0]
        success = expand_missing_entity(target_id)
        if not success:
            break


if __name__ == "__main__":
    main()
