import requests
import json

url = "http://localhost:8000/api/v1/bulletins/regenerate-translation"
payload = {
    "date": "2023-07-01",
    "station_name": "National",
    "language": "dioula"
}
headers = {"Content-Type": "application/json"}

try:
    response = requests.post(url, json=payload, headers=headers)
    print(f"Status: {response.status_code}")
    print(f"Response: {json.dumps(response.json(), indent=2, ensure_ascii=False)}")
except Exception as e:
    print(f"Error: {e}")
