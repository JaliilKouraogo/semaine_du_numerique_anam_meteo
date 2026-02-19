
import psycopg2
from psycopg2.extras import RealDictCursor
import re
import unicodedata
from pathlib import Path
from datetime import datetime

def normalize_month(m):
    t = unicodedata.normalize("NFKD", m.lower())
    return "".join(ch for ch in t if not unicodedata.combining(ch))

def fix_bulletin_dates():
    try:
        conn = psycopg2.connect("postgresql://anam_user:anam_password@127.0.0.1:5433/anam_db")
        
        pdf_date_regex = re.compile(r"(\d{1,2})[a-zA-Z\u00C0-\u00FF\s_\-]+?([a-zA-Z\u00C0-\u00FF]+)[_\- ]+(\d{4})", re.IGNORECASE)
        month_map = {
            "janvier": 1, "fevrier": 2, "février": 2, "mars": 3, "avril": 4, "mai": 5, "juin": 6,
            "juillet": 7, "aout": 8, "août": 8, "septembre": 9, "octobre": 10, "novembre": 11, "decembre": 12, "décembre": 12
        }

        with conn.cursor(cursor_factory=RealDictCursor) as cursor:
            cursor.execute("SELECT id, date, type, file_path FROM bulletins")
            bulletins = cursor.fetchall()
            
            updated_count = 0
            for b in bulletins:
                b_id = b['id']
                b_date = b['date']
                b_path = b['file_path']
                
                if not b_path:
                    continue
                
                stem = Path(b_path).stem
                match = pdf_date_regex.search(stem)
                if match:
                    try:
                        day = int(match.group(1))
                        month_str = normalize_month(match.group(2))
                        year = int(match.group(3))
                        month = month_map.get(month_str)
                        
                        if month:
                            new_date = datetime(year, month, day).strftime("%Y-%m-%d")
                            if new_date != b_date:
                                print(f"Updating Bulletin {b_id}: {b_date} -> {new_date} (Path: {stem})")
                                cursor.execute("UPDATE bulletins SET date = %s WHERE id = %s", (new_date, b_id))
                                updated_count += 1
                    except Exception as e:
                        print(f"Error parsing {stem}: {e}")
            
            conn.commit()
            print(f"\nFinished. Updated {updated_count} bulletins.")
            
    except Exception as e:
        print(f"Database error: {e}")

if __name__ == "__main__":
    fix_bulletin_dates()
