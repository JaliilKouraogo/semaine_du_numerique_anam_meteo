from backend.utils.database import DatabaseManager
import os

db = DatabaseManager(os.getenv('DATABASE_URL'))
conn = db.get_connection()
cursor = conn.cursor()
cursor.execute("DELETE FROM bulletins WHERE date IN ('2026-02-02', '2026-02-03')")
conn.commit()
print("Cleaned Feb 2026 incorrect data.")
