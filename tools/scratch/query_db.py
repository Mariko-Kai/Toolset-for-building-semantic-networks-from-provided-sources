import sqlite3
conn = sqlite3.connect('mathesis_index.db')
cursor = conn.cursor()
cursor.execute("SELECT entity_id, path FROM entities WHERE entity_id IN ('def-limit', 'lim-sequential')")
print(cursor.fetchall())
conn.close()
