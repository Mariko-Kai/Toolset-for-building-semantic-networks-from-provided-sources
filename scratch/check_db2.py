import sqlite3

conn = sqlite3.connect("mathesis_index.db")
cursor = conn.cursor()

# All unique clusters
cursor.execute("SELECT temp_cluster_id, COUNT(*), GROUP_CONCAT(DISTINCT source_book) FROM formulation_raw_cache WHERE temp_cluster_id IS NOT NULL GROUP BY temp_cluster_id")
print("Clusters in formulation_raw_cache:")
for row in cursor.fetchall():
    print(f"  cluster={row[0]}: {row[1]} formulations, sources={row[2]}")

# Check total data
cursor.execute("SELECT COUNT(*), GROUP_CONCAT(DISTINCT source_book) FROM formulation_raw_cache")
row = cursor.fetchone()
print(f"\nTotal rows: {row[0]}, sources: {row[1]}")

# Sample raw text
cursor.execute("SELECT temp_cluster_id, source_book, substr(raw_text, 1, 200) FROM formulation_raw_cache LIMIT 10")
print("\nSample texts:")
for i, row in enumerate(cursor.fetchall()):
    print(f"\n--- Sample {i+1} (cluster={row[0]}, source={row[1]}) ---")
    print(row[2])

conn.close()
