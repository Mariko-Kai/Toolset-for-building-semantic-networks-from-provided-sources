import sqlite3
import os
from pathlib import Path

PROJECT_ROOT = Path("f:/Universe/Projects/Учебник по матанализу")
conn = sqlite3.connect(PROJECT_ROOT / 'mathesis_index.db')
cursor = conn.cursor()

bad_ids = [
    'op-limit', 'riemann-integrability', 'def-lim-sequence', 'op-integral',
    'ax-completeness', 'ax-fol-5', 'ax-fol-4', 'rule-generalization', 'rule-modus-ponens',
    'def-limit', 'lim-sequential'
]

placeholders = ','.join('?' * len(bad_ids))
cursor.execute(f"DELETE FROM entities WHERE entity_id IN ({placeholders})", bad_ids)
cursor.execute(f"DELETE FROM entity_dependency WHERE source_id IN ({placeholders}) OR target_id IN ({placeholders})", bad_ids + bad_ids)
cursor.execute(f"DELETE FROM formulation_sources WHERE entity_id IN ({placeholders})", bad_ids)

conn.commit()
conn.close()
print("Cleaned up database.")
