
import requests
import json

def check_bulletins():
    try:
        resp = requests.get("http://localhost:8000/api/v1/bulletins?limit=100")
        if resp.status_code == 200:
            data = resp.json()
            print("--- Bulletins List ---")
            for item in data.get("items", []):
                print(f"ID: {item.get('id')}, Date: {item.get('date')}, Type: {item.get('type')}, Path: {item.get('file_path')}")
        else:
            print(f"Error {resp.status_code}: {resp.text}")
            
        resp_metrics = requests.get("http://localhost:8000/api/v1/metrics?limit=10")
        if resp_metrics.status_code == 200:
            data = resp_metrics.json()
            print("\n--- Latest Metrics ---")
            for item in data.get("items", []):
                print(f"Obs Date: {item.get('date')}, Fore Ref: {item.get('forecast_reference_date')}, Sample: {item.get('sample_size')}")
    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    check_bulletins()
