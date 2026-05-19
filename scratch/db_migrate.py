import sqlite3
conn = sqlite3.connect('mathesis_index.db')
cursor = conn.cursor()
try:
    cursor.execute("ALTER TABLE formulation_raw_cache ADD COLUMN page_ref INTEGER DEFAULT 0")
    print("Column added successfully.")
except sqlite3.OperationalError as e:
    print(f"Error (might already exist): {e}")
conn.commit()
conn.close()
