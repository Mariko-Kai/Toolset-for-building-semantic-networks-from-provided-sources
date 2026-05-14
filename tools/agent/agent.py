import os
import sys
import re
import json
import argparse
import subprocess
from pathlib import Path
from dotenv import load_dotenv

import base64
import urllib.request
from PIL import Image

# Setup Paths
PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
sys.path.append(str(PROJECT_ROOT))
from tools.pdftoimages.pdf_to_images import BOOK_REGISTRY, BOOKS_DIR, render_pages, parse_page_range

CONTENT_DIR = PROJECT_ROOT / "content"
DOCS_DIR = PROJECT_ROOT / "docs"
TODO_QUEUE_FILE = Path(__file__).resolve().parent / "todo_queue.json"
MASTER_TEX_PATH = CONTENT_DIR / "master.tex"

TYPE_TO_DIR = {
    "axiom": "foundations",
    "object": "objects",
    "property": "properties",
    "operation": "operations",
    "theorem": "theorems",
    "lemma": "theorems",
    "corollary": "theorems"
}

def load_system_prompt() -> str:
    prompt_path = DOCS_DIR / "agent_prompt_content_extractor.md"
    with open(prompt_path, "r", encoding="utf-8") as f:
        # Append thinking requirement to the prompt
        return f.read() + "\n\nBefore generating LaTeX, you MUST output your Chain of Thought (Reasoning) inside `<think>...</think>` XML tags."

def extract_latex_blocks(text: str) -> list[str]:
    # Match ```latex ... ``` blocks
    pattern = re.compile(r"```latex\n(.*?)```", re.DOTALL)
    return pattern.findall(text)

def parse_metadata(latex_content: str) -> dict:
    metadata = {}
    id_match = re.search(r"%\s*entity-id:\s*([^\n]+)", latex_content)
    type_match = re.search(r"%\s*entity-type:\s*([^\n]+)", latex_content)
    
    if id_match:
        metadata["id"] = id_match.group(1).strip()
    if type_match:
        metadata["type"] = type_match.group(1).strip().lower()
        
    return metadata

def save_tex_file(entity_id: str, entity_type: str, content: str) -> Path | None:
    target_dir_name = TYPE_TO_DIR.get(entity_type)
    if not target_dir_name:
        print(f"  [Error] Unknown entity type: {entity_type} for {entity_id}")
        return None
        
    target_dir = CONTENT_DIR / target_dir_name
    target_dir.mkdir(parents=True, exist_ok=True)
    
    file_path = target_dir / f"{entity_id}.tex"
    with open(file_path, "w", encoding="utf-8") as f:
        f.write(content.strip() + "\n")
    
    return file_path

def update_master_tex(entity_id: str, entity_type: str):
    target_dir_name = TYPE_TO_DIR.get(entity_type)
    if not target_dir_name:
        return
        
    input_line = f"\\input{{{target_dir_name}/{entity_id}}}\n"
    
    with open(MASTER_TEX_PATH, "r", encoding="utf-8") as f:
        lines = f.readlines()
        
    # Check if already included
    if any(input_line.strip() in line for line in lines):
        return
        
    # Find the section to insert into
    # Example: \section{Операции (Operations)}
    # We will just append it before the next \section or \end{document}
    section_patterns = {
        "foundations": "Основания математики",
        "objects": "Объекты",
        "operations": "Операции",
        "properties": "Свойства",
        "theorems": "Теоремы"
    }
    
    search_term = section_patterns.get(target_dir_name, target_dir_name)
    
    insert_idx = -1
    in_section = False
    
    for i, line in enumerate(lines):
        if "\\chapter{" in line:
            if search_term in line:
                in_section = True
            elif in_section:
                # We hit the next section, insert before this
                insert_idx = i - 1
                break
        elif "\\end{document}" in line and in_section:
            insert_idx = i - 1
            break
            
    if insert_idx != -1:
        lines.insert(insert_idx, input_line)
        with open(MASTER_TEX_PATH, "w", encoding="utf-8") as f:
            f.writelines(lines)
        print(f"  [OK] Added {input_line.strip()} to master.tex")
    else:
        print(f"  [Warning] Could not automatically insert {entity_id} into master.tex")

def update_todo_queue() -> set:
    # 1. Read all existing entity IDs
    existing_entities = set()
    for root, _, files in os.walk(CONTENT_DIR):
        for file in files:
            if file.endswith(".tex") and file not in ["master.tex", "TEMPLATE.tex"]:
                existing_entities.add(file.replace(".tex", ""))
                
    # 2. Extract all \entityref{ID} from all files
    referenced_entities = set()
    for root, _, files in os.walk(CONTENT_DIR):
        for file in files:
            if file.endswith(".tex") and file not in ["master.tex", "TEMPLATE.tex"]:
                with open(os.path.join(root, file), "r", encoding="utf-8") as f:
                    content = f.read()
                    refs = re.findall(r"\\entityref\{([^}]+)\}", content)
                    referenced_entities.update(refs)
                    
    # 3. Queue = Referenced - Existing
    missing_entities = referenced_entities - existing_entities
    
    with open(TODO_QUEUE_FILE, "w", encoding="utf-8") as f:
        json.dump(list(missing_entities), f, indent=2)
        
    print(f"\nTODO Queue updated: {len(missing_entities)} unresolved entities.")
    return missing_entities

def run_validation():
    print("\nRunning validation (build.bat)...")
    result = subprocess.run(["build.bat"], cwd=str(PROJECT_ROOT), shell=True, capture_output=True, text=True)
    if result.returncode == 0:
        print("  [SUCCESS] Zero Compile Errors.")
    else:
        print("  [ERROR] Compilation failed.")
        print(result.stdout)
        print(result.stderr)

def query_ollama_vision(prompt, image_paths, model="llava-phi3:latest"):
    """Sends a request with images to the local Ollama API."""
    url = "http://localhost:11434/api/generate"
    
    encoded_images = []
    for ipath in image_paths:
        with open(ipath, "rb") as img_file:
            encoded_images.append(base64.b64encode(img_file.read()).decode('utf-8'))
    
    data = {
        "model": model,
        "prompt": prompt,
        "stream": False,
        "images": encoded_images,
        "options": {
            "temperature": 0.1
        }
    }
    
    try:
        req = urllib.request.Request(url, json.dumps(data).encode('utf-8'), headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req, timeout=300) as response:
            result = json.loads(response.read().decode('utf-8'))
            return result.get('response', '').strip()
    except Exception as e:
        print(f"  [Ollama Vision Error] {e}")
        return ""

def process_images(image_paths: list[Path]):
    # load_dotenv()
    # api_key = os.getenv("GOOGLE_API_KEY")
    # if not api_key:
    #     print("ERROR: GOOGLE_API_KEY environment variable not set.")
    #     sys.exit(1)
        
    # client = genai.Client(api_key=api_key)
    system_prompt = load_system_prompt()
    
    # Ask the specific instruction
    user_instruction = "Extract all mathematical definitions, axioms, and theorems from these pages into strictly formalized LaTeX blocks following the system instructions. Include % entity-id and % entity-type metadata."
    
    full_prompt = system_prompt + "\n\n" + user_instruction
    
    print(f"Sending request to Ollama (llava-phi3) with {len(image_paths)} images...")
    print("=" * 40)
    
    response_text = query_ollama_vision(full_prompt, image_paths)
    
    print("Ollama Response received.")
    print("-" * 40)
    print(response_text)
    print("\n" + "=" * 40)
    
    blocks = extract_latex_blocks(response_text)
    
    print(f"\nReceived {len(blocks)} LaTeX block(s) from Ollama.")
    
    for i, block in enumerate(blocks):
        meta = parse_metadata(block)
        ent_id = meta.get("id")
        ent_type = meta.get("type")
        
        if ent_id and ent_type:
            print(f"Processing entity: {ent_id} ({ent_type})")
            saved_path = save_tex_file(ent_id, ent_type, block)
            if saved_path:
                update_master_tex(ent_id, ent_type)
        else:
            print(f"  [Warning] Block {i+1} is missing entity-id or entity-type metadata.")

    update_todo_queue()
    run_validation()

def main():
    parser = argparse.ArgumentParser(description="Orchestration Agent for Content Extraction")
    parser.add_argument("--book", default="zorich-1", help="Book key from registry (default: zorich-1)")
    parser.add_argument("--all", action="store_true", help="Parse the entire book")
    parser.add_argument("--query", type=str, help="Parse pages containing this specific text query")
    parser.add_argument("--pages", type=str, help="Specific page range (e.g., '10-20')")
    args = parser.parse_args()
    
    book_info = BOOK_REGISTRY.get(args.book)
    if not book_info:
        print(f"Error: Unknown book '{args.book}'")
        sys.exit(1)
        
    pdf_path = BOOKS_DIR / book_info["file"]
    if not pdf_path.exists():
        print(f"Error: PDF not found at {pdf_path}")
        sys.exit(1)
        
    import fitz
    print(f"Opening PDF: {pdf_path.name}")
    doc = fitz.open(str(pdf_path))
    total_pages = len(doc)
    pages_to_render = set()
    
    if args.all:
        print("Mode: Entire Textbook")
        pages_to_render = set(range(1, total_pages + 1))
    elif args.pages:
        print(f"Mode: Specific Pages ({args.pages})")
        pages_to_render = set(parse_page_range(args.pages))
    elif args.query:
        print(f"Mode: Entity Query ('{args.query}')")
        query_text = args.query.lower()
        for i in range(total_pages):
            text = doc[i].get_text().lower()
            if query_text in text:
                pages_to_render.add(i + 1)
                # optionally add context pages (i, i+1, i+2)
                pages_to_render.add(min(i + 2, total_pages)) 
    else:
        print("Mode: Fallback (Zorich-1 Chapter 3: Limits)")
        if args.book == "zorich-1":
            print("Using exact Chapter 3 boundaries: pages 84-149.")
            pages_to_render = set(range(84, 150))
        else:
            print("No command arguments provided, and fallback is only supported for 'zorich-1'.")
            sys.exit(1)

    if not pages_to_render:
        print("No pages matched the criteria.")
        sys.exit(0)
        
    page_list = sorted(list(pages_to_render))
    print(f"Pages chosen for rendering: {page_list}")
    
    generated_images = render_pages(pdf_path, args.book, page_list, dpi=150, split_half=False)
    doc.close()
    
    if generated_images:
        process_images(generated_images)
    else:
        print("No images were successfully rendered.")

if __name__ == "__main__":
    main()
