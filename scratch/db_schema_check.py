import sqlite3
conn = sqlite3.connect('mathesis_index.db')
cursor = conn.cursor()
cursor.execute("SELECT sql FROM sqlite_master WHERE name='formulation_raw_cache'")
print(cursor.fetchone()[0])
conn.close()
