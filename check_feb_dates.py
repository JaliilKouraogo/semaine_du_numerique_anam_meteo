from backend.utils.database import DatabaseManager
import os

db = DatabaseManager(os.getenv('DATABASE_URL'))
conn = db.get_connection()
cursor = conn.cursor()
query = "SELECT id, date, type, file_path FROM bulletins WHERE date IN ('2026-02-02', '2026-02-03') ORDER BY date, type"
cursor.execute(query)
for r in cursor.fetchall():
    print(f"{r[0]} | {r[1]} | {r[2]} | {r[3]}")
