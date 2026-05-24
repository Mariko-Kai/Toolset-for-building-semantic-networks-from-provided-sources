import sqlite3
import ollama
import struct

DB_PATH = r'f:\Universe\Projects\Учебник по матанализу\db\mathesis_index.db'
MODEL = "nomic-embed-text:latest"

def main():
    print("=== Updating Embeddings for DB (BLOB format) ===")
    conn = sqlite3.connect(DB_PATH)
    cursor = conn.cursor()
    
    cursor.execute("SELECT entity_id, title, nl_desc FROM entities")
    rows = cursor.fetchall()
    
    print(f"Found {len(rows)} entities. Recomputing to binary BLOB format...")
    
    for row in rows:
        entity_id, title, nl_desc = row
        text = f"{title}\n{nl_desc}"
        
        try:
            response = ollama.embeddings(model=MODEL, prompt=text)
            emb = response['embedding']
            
            # Store as binary blob of 32-bit floats
            emb_blob = struct.pack(f"{len(emb)}f", *emb)
            
            cursor.execute(
                "UPDATE entities SET embedding = ? WHERE entity_id = ?",
                (emb_blob, entity_id)
            )
            print(f"  [+] Computed BLOB embedding for {entity_id}")
        except Exception as e:
            print(f"  [-] Failed for {entity_id}: {e}")
            
    conn.commit()
    conn.close()
    print("Done!")

if __name__ == '__main__':
    main()
