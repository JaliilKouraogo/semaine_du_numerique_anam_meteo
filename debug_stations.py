from backend.utils.database import DatabaseManager
import os

db = DatabaseManager(os.getenv('DATABASE_URL'))
conn = db.get_connection()
cursor = conn.cursor()
cursor.execute("SELECT s.name, b.type, b.date FROM weather_data w JOIN bulletins b ON w.bulletin_id = b.id JOIN stations s ON w.station_id = s.id WHERE b.date IN ('2026-02-02', '2026-02-03') ORDER BY s.name, b.date")
for r in cursor.fetchall():
    print(r)
