import sqlite3
import urllib.request
import json
import faiss
import numpy as np
from pathlib import Path
import uuid

PROJECT_ROOT = Path(__file__).resolve().parent.parent
DB_PATH = PROJECT_ROOT / "mathesis_index.db"

def get_embedding(text):
    url = 'http://localhost:11434/api/embeddings'
    data = {'model': 'nomic-embed-text:latest', 'prompt': text}
    req = urllib.request.Request(url, json.dumps(data).encode('utf-8'), headers={'Content-Type': 'application/json'})
    try:
        with urllib.request.urlopen(req) as response:
            result = json.loads(response.read().decode('utf-8'))
            return result.get('embedding', [])
    except Exception as e:
        print(f"Embedding error: {e}")
        return []

def main():
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("SELECT id, raw_text FROM formulation_raw_cache WHERE temp_cluster_id IS NULL")
    rows = cursor.fetchall()
    
    if not rows:
        print("No new formulations to align.")
        return

    ids = []
    embeddings = []
    
    print("Generating embeddings via Ollama...")
    for row_id, text in rows:
        emb = get_embedding(text)
        if emb:
            ids.append(row_id)
            embeddings.append(emb)
            
    if not embeddings:
        return
        
    embeddings_np = np.array(embeddings).astype('float32')
    dim = embeddings_np.shape[1]
    
    print("Clustering using FAISS...")
    faiss.normalize_L2(embeddings_np)
    index = faiss.IndexFlatIP(dim)
    index.add(embeddings_np)
    
    D, I = index.search(embeddings_np, k=embeddings_np.shape[0])
    
    clusters = {}
    visited = set()
    
    for i in range(embeddings_np.shape[0]):
        if i in visited:
            continue
        cluster_id = str(uuid.uuid4())[:8]
        clusters[cluster_id] = []
        for j in range(embeddings_np.shape[0]):
            if D[i][j] > 0.8:
                if I[i][j] not in visited:
                    clusters[cluster_id].append(ids[I[i][j]])
                    visited.add(I[i][j])
                    
    print(f"Found {len(clusters)} clusters.")
    
    for cid, member_ids in clusters.items():
        for mid in member_ids:
            cursor.execute("UPDATE formulation_raw_cache SET temp_cluster_id = ? WHERE id = ?", (cid, mid))
            
    conn.commit()
    conn.close()
    print("Entity alignment complete.")

if __name__ == "__main__":
    main()
