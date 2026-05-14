import sqlite3, os
conn = sqlite3.connect('mathesis_index.db')
cursor = conn.cursor()
cursor.execute('SELECT entity_id, path FROM entities')
rows = cursor.fetchall()
missing = [r for r in rows if not os.path.exists(r[1])]
print('Missing files in DB:', missing)

cursor.execute('SELECT source_id, target_id FROM entity_dependency WHERE source_id="" OR target_id=""')
empty = cursor.fetchall()
print('Empty cells in deps:', empty)
conn.close()
