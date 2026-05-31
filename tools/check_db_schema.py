import sqlite3
from pipeline.config import get_db_path

db_path = get_db_path()
conn = sqlite3.connect(db_path)
for row in conn.execute("SELECT name, sql FROM sqlite_master WHERE type='table'"):
    print(f"Table: {row[0]}")
    print(row[1])
    print("-" * 50)
conn.close()
