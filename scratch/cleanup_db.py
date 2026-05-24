import sys, sqlite3
from pathlib import Path
sys.stdout.reconfigure(encoding='utf-8')

PROJECT_ROOT = Path('.')
DB_PATH = PROJECT_ROOT / 'mathesis_index.db'
CONTENT_DIR = PROJECT_ROOT / 'content'

conn = sqlite3.connect(DB_PATH)
cur = conn.cursor()

cur.execute('SELECT entity_id FROM entities')
all_ids = [r[0] for r in cur.fetchall()]

# Entities with no .tex file in content/
to_delete = set()
for eid in all_ids:
    matches = list(CONTENT_DIR.rglob(f'*[{eid}].tex'))
    if not matches:
        to_delete.add(eid)

# Also force-delete Weierstrass theorem
to_delete.add('prop-weierstrass-extreme-value')

# Get all table names
cur.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in cur.fetchall()]
print(f'Tables: {tables}')

deleted_total = 0
for eid in sorted(to_delete):
    print(f'\nRemoving: {eid}')
    for table in tables:
        for col in ['entity_id', 'id', 'source_id']:
            try:
                cur.execute(f'DELETE FROM "{table}" WHERE "{col}" = ?', (eid,))
                if cur.rowcount > 0:
                    print(f'  [{table}.{col}] deleted {cur.rowcount} row(s)')
                    deleted_total += cur.rowcount
            except Exception:
                pass

conn.commit()
conn.close()
print(f'\nDone. Total rows deleted: {deleted_total}')
print(f'Removed: {sorted(to_delete)}')
