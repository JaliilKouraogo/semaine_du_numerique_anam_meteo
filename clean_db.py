from backend.utils.database import DatabaseManager
import os

db = DatabaseManager(os.getenv('DATABASE_URL'))
conn = db.get_connection()
cursor = conn.cursor()
cursor.execute("DELETE FROM bulletins WHERE date LIKE '2023-07%'")
conn.commit()
print("Cleaned July 2023 data.")
