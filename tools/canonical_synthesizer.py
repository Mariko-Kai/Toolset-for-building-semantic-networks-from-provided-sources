import sqlite3
import urllib.request
import json
import uuid
import re
from pathlib import Path

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "mathesis_index.db"
CONTENT_DIR = PROJECT_ROOT / "content"

def query_ollama(prompt, model="llama3.1:8b"):
    url = "http://localhost:11434/api/generate"
    data = {
        "model": model,
        "prompt": prompt,
        "stream": False
    }
    try:
        req = urllib.request.Request(url, json.dumps(data).encode('utf-8'), headers={'Content-Type': 'application/json'})
        with urllib.request.urlopen(req) as response:
            result = json.loads(response.read().decode('utf-8'))
            return result.get('response', '').strip()
    except Exception as e:
        print(f"Ollama error: {e}")
        return ""

def synthesize_cluster(cluster_id, formulations, sources):
    print(f"Synthesizing cluster {cluster_id} with {len(formulations)} formulations from {sources}...")
    
    text_input = "\n\n".join([f"Источник ({s}): {t}" for s, t in zip(sources, formulations)])
    
    prompt = f"""Синтезируй максимально строгую математическую формулировку на основе следующих определений, которые включают предыдущий контекст (до начала параграфа):
{text_input}

ВНИМАНИЕ: Обязательно выяви все неявные ограничения из контекста (например, что функция должна быть ограниченной, или задана на замкнутом промежутке) и явно включи их в объявление типов или математическую формулу.

Выведи ТОЛЬКО LaTeX код без обрамляющих блоков ```latex. Код должен включать мета-комментарии:
% entity-id: <сгенерируй короткий id, например op-integral>
% entity-type: <выбери: object, property, operation или theorem>
и сам блок \\begin{{object}}[Название] ... \\end{{object}} (или property/operation/theorem) с канонической математической записью, без лишнего естественного языка. 
Используй макросы \\mForall, \\mExists, \\mImplies, \\mIff.
"""
    response = query_ollama(prompt)
    # Cleanup possible backticks
    response = re.sub(r'^```latex\s*', '', response, flags=re.MULTILINE)
    response = re.sub(r'^```\s*', '', response, flags=re.MULTILINE)
    return response

def main():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("SELECT temp_cluster_id, source_book, raw_text FROM formulation_raw_cache WHERE temp_cluster_id IS NOT NULL")
    rows = cursor.fetchall()
    
    clusters = {}
    for cid, source, text in rows:
        if cid not in clusters:
            clusters[cid] = {'sources': [], 'texts': []}
        clusters[cid]['sources'].append(source)
        clusters[cid]['texts'].append(text)
        
    for cid, data in clusters.items():
        synthesized_tex = synthesize_cluster(cid, data['texts'], data['sources'])
        if not synthesized_tex:
            continue
            
        match_id = re.search(r'% entity-id:\s*([a-zA-Z0-9\-]+)', synthesized_tex)
        match_type = re.search(r'% entity-type:\s*([a-zA-Z]+)', synthesized_tex)
        
        if not match_id or not match_type:
            print(f"Failed to parse metadata from LLM output for cluster {cid}.\nOutput:\n{synthesized_tex}")
            continue
            
        entity_id = match_id.group(1).strip()
        entity_type = match_type.group(1).strip()
        title = entity_id.replace('-', ' ').title()
        
        # Decide directory based on type
        type_dir = entity_type + "s"
        target_dir = CONTENT_DIR / type_dir
        target_dir.mkdir(exist_ok=True)
        
        file_path = target_dir / f"{title} [{entity_id}].tex"
        
        with open(file_path, "w", encoding="utf-8") as f:
            f.write(synthesized_tex)
            
        cursor.execute("INSERT OR REPLACE INTO entities (entity_id, type, title, path) VALUES (?, ?, ?, ?)",
                       (entity_id, entity_type, title, str(file_path.relative_to(PROJECT_ROOT))))
                       
        for source in data['sources']:
            cursor.execute("INSERT INTO formulation_sources (entity_id, source_book) VALUES (?, ?)", (entity_id, source))
            
        # Clean up cache
        cursor.execute("DELETE FROM formulation_raw_cache WHERE temp_cluster_id = ?", (cid,))
            
    conn.commit()
    conn.close()
    print("Canonical synthesis complete.")

if __name__ == "__main__":
    main()
