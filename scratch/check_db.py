import sqlite3

conn = sqlite3.connect("mathesis_index.db")
cursor = conn.cursor()

# List all tables
cursor.execute("SELECT name FROM sqlite_master WHERE type='table'")
tables = [r[0] for r in cursor.fetchall()]
print("Tables:", tables)

# Check entity counts
for table in tables:
    cursor.execute(f"SELECT COUNT(*) FROM [{table}]")
    count = cursor.fetchone()[0]
    print(f"  {table}: {count} rows")

# Check formulation_raw_cache content
if "formulation_raw_cache" in tables:
    cursor.execute("SELECT temp_cluster_id, source_book, substr(raw_text, 1, 80) FROM formulation_raw_cache LIMIT 5")
    print("\nformulation_raw_cache samples:")
    for row in cursor.fetchall():
        print(f"  cluster={row[0]}, source={row[1]}, text={row[2]}...")

# Check entities table if it exists
if "entities" in tables:
    cursor.execute("SELECT entity_id, type, title FROM entities")
    print("\nEntities:")
    for row in cursor.fetchall():
        print(f"  {row[0]} ({row[1]}): {row[2]}")

conn.close()
