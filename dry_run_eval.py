
import os
import sys
from datetime import datetime, timedelta
import re
import unicodedata
from pathlib import Path

# Add backend to path
sys.path.append(os.getcwd())

from backend.utils.database import DatabaseManager

def normalize_month(m):
    t = unicodedata.normalize("NFKD", m.lower())
    return "".join(ch for ch in t if not unicodedata.combining(ch))

def dry_run_match():
    db_url = "postgresql://anam_user:anam_password@localhost:5432/anam_db"
    db_manager = DatabaseManager(db_url)
    
    conn = db_manager.get_connection()
    with conn.cursor() as cursor:
        cursor.execute("SELECT id, type, date, file_path FROM bulletins")
        all_bulletins = cursor.fetchall()

    pdf_date_regex = re.compile(r"(\d{1,2})[a-zA-Z\u00C0-\u00FF\s_\-]+?([a-zA-Z\u00C0-\u00FF]+)[_\- ]+(\d{4})", re.IGNORECASE)
    month_map = {
        "janvier": 1, "fevrier": 2, "février": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6,
        "juillet": 7, "aout": 8, "août": 8, "septembre": 9, "octobre": 10, "novembre": 11, "decembre": 12, "décembre": 12
    }

    forecasts_by_target = {}
    observations_by_target = {}

    for b_id, b_type, b_date, b_path in all_bulletins:
        file_date = None
        if b_path:
            match = pdf_date_regex.search(Path(b_path).stem)
            if match:
                try:
                    day = int(match.group(1))
                    month_str = normalize_month(match.group(2))
                    year = int(match.group(3))
                    month = month_map.get(month_str)
                    if month:
                        file_date = datetime(year, month, day)
                except: pass
        
        if file_date is None:
            try:
                file_date = datetime.strptime(b_date, "%Y-%m-%d")
            except: continue
            
        ref_date_str = file_date.strftime("%Y-%m-%d")
        if b_type == 'forecast':
            target_date = (file_date + timedelta(days=1)).strftime("%Y-%m-%d")
            forecasts_by_target[target_date] = (b_id, ref_date_str)
            print(f"Forecast {b_id}: {ref_date_str} -> Targets {target_date}")
        elif b_type == 'observation':
            target_date = ref_date_str
            observations_by_target[target_date] = b_id
            print(f"Observation {b_id}: Targets {target_date}")

    target_dates = sorted(set(observations_by_target.keys()) & set(forecasts_by_target.keys()))
    print(f"\nFinal Matched Target Dates: {target_dates}")

if __name__ == "__main__":
    dry_run_match()
