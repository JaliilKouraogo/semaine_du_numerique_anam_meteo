from backend.utils.database import DatabaseManager
import os

db = DatabaseManager(os.getenv('DATABASE_URL'))
print("Pairs for 2026-02-03 (obs) and 2026-02-03 (forecast):")
try:
    pairs = db.get_observation_forecast_pairs('2026-02-03', '2026-02-03')
    print(pairs)
except Exception as e:
    print(f"Error: {e}")
