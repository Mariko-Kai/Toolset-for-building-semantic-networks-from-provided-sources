import sqlite3
import faiss
import numpy as np
from pathlib import Path
import uuid
import sys
import io

# Fix Windows console encoding
if sys.platform == 'win32':
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8', errors='replace')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8', errors='replace')

PROJECT_ROOT = Path(__file__).resolve().parent.parent

# Ensure project root is on path for ModelManager import
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from pipeline.config import get_db_path
DB_PATH = Path(get_db_path())  # единый путь к БД из конфига (env MATHESIS_DB_PATH)

from pipeline.model_manager import ModelManager

def get_embedding(text):
    """Gets embedding via ModelManager embed role (supports remote Ollama via configured host)."""
    mgr = ModelManager.get_instance()
    result = mgr.get_embedding(text, role="embed")
    if result is None:
        return []
    return result

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
