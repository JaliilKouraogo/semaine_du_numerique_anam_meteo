import time
import requests

def check_and_recalc():
    while True:
        try:
            r = requests.post('http://localhost:8000/api/v1/metrics/recalculate', json={'force': True}, timeout=10)
            print(f"Status: {r.status_code}, Resp: {r.text}")
            if "evaluated" in r.text and r.json().get("result", {}).get("daily", {}).get("evaluated", 0) > 0:
                print("SUCCESS: Metrics calculated!")
                break
        except Exception as e:
            print(f"Error: {e}")
        time.sleep(5)

if __name__ == "__main__":
    check_and_recalc()
