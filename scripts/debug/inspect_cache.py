import sqlite3
import sys

conn = sqlite3.connect("cache.db")

query_filter = sys.argv[1] if len(sys.argv) > 1 else None

print("=== embedding_cache ===")
if query_filter:
    rows = conn.execute(
        "SELECT question, created_at FROM embedding_cache WHERE question LIKE ?",
        (f"%{query_filter}%",),
    )
else:
    rows = conn.execute("SELECT question, created_at FROM embedding_cache")
for row in rows:
    print(row)

print("\n=== response_cache ===")
if query_filter:
    rows = conn.execute(
        "SELECT question, substr(answer, 1, 60), created_at FROM response_cache WHERE question LIKE ?",
        (f"%{query_filter}%",),
    )
else:
    rows = conn.execute("SELECT question, substr(answer, 1, 60), created_at FROM response_cache")
for row in rows:
    print(row)

conn.close()