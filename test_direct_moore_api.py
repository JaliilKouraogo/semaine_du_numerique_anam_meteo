
import requests
import json

def test_direct_api():
    print("--- Test direct de l'API de traduction Moore ---")
    url = "https://fr-mos-translator-314397473739.europe-west1.run.app/api/translate"
    payload = {
        "text": "Je suis ravi de vous revoir",
        "source_lang": "french",
        "target_lang": "moore"
    }
    
    try:
        print(f"Appel de l'API avec : {payload['text']}")
        response = requests.post(url, json=payload, timeout=30)
        print(f"Status Code : {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print(f"Réponse JSON : {json.dumps(data, indent=2, ensure_ascii=False)}")
            translated = data.get("translation")
            if translated:
                print(f"Traduction obtenue : {translated}")
            else:
                print("Pas de champ 'translation' dans la réponse.")
        else:
            print(f"Erreur : {response.text}")
            
    except Exception as e:
        print(f"Exception lors de l'appel : {e}")

if __name__ == "__main__":
    test_direct_api()
