Вотimport sqlite3
import os

db_path = 'db/mathesis_index.db'
if os.path.exists(db_path):
    conn = sqlite3.connect(db_path)
    conn.execute("DELETE FROM entities WHERE entity_id='prop-cantor-uniform-continuity'")
    conn.commit()
    conn.close()
    print("Deleted from DB")
