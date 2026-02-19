
import psycopg2
from psycopg2.extras import RealDictCursor
import json

def inspect_db():
    conn = psycopg2.connect("postgresql://anam_user:anam_password@127.0.0.1:5433/anam_db")
    with conn.cursor(cursor_factory=RealDictCursor) as cursor:
        print("--- Latest Bulletins ---")
        cursor.execute("SELECT id, date, type, file_path FROM bulletins ORDER BY date DESC, type LIMIT 10")
        bulletins = cursor.fetchall()
        for b in bulletins:
            print(f"ID: {b['id']}, Date: {b['date']}, Type: {b['type']}, Path: {b['file_path']}")
            
        print("\n--- Bulletin Payloads for 15 and 16 ---")
        cursor.execute("SELECT file_path, payload_json FROM bulletin_payloads WHERE file_path LIKE '%%Bulletin_du_08%%' OR file_path LIKE '%%Bulletin_du_09%%'")
        payloads = cursor.fetchall()
        for p in payloads:
            print(f"Path: {p['file_path']}")
            payload = json.loads(p['payload_json'])
            print(f"  Type in payload: {payload.get('type')}")
            if 'data' in payload:
                for m in payload['data']:
                    print(f"  Map Type: {m.get('type')}")
            
        print("\n--- Latest Evaluation Metrics ---")
        cursor.execute("SELECT id, bulletin_date, forecast_reference_date, sample_size, calculated_at FROM evaluation_metrics ORDER BY bulletin_date DESC LIMIT 5")
        metrics = cursor.fetchall()
        for m in metrics:
            print(f"ID: {m['id']}, Obs Date: {m['bulletin_date']}, Fore Ref: {m['forecast_reference_date']}, Sample: {m['sample_size']}, At: {m['calculated_at']}")

if __name__ == "__main__":
    inspect_db()
