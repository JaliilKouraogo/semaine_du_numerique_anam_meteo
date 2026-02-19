from backend.utils.database import DatabaseManager
import os

db = DatabaseManager(os.getenv('DATABASE_URL'))
conn = db.get_connection()
cursor = conn.cursor()
cursor.execute("SELECT date, type FROM bulletins WHERE date >= '2026-02-01' ORDER BY date, type")
for r in cursor.fetchall():
    print(f"{r[0]} | {r[1]}")
