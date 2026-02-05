
import cv2
import json
import numpy as np
import base64
import requests
import concurrent.futures
from pathlib import Path

# Configuration paths Relative to project root
BASE_DIR = Path(__file__).resolve().parent.parent
CONFIG_DIR = BASE_DIR / "config"
ZONES_FILE = CONFIG_DIR / "cities_icons_zones.json"

OLLAMA_URL = "http://localhost:11434/api/generate"
MODEL = "minicpm-v:8b"

def encode_image(image):
    _, buffer = cv2.imencode('.png', image)
    return base64.b64encode(buffer).decode('utf-8')

def call_ollama(cities_data):
    """
    cities_data: list of {'name': str, 'image': bgr_img}
    """
    # Create collage
    crops = [c['image'] for c in cities_data]
    h_per_crop = 160
    w_max = max(c.shape[1] for c in crops) if crops else 200
    canvas_w = w_max + 300
    
    collage = np.full((h_per_crop * 5, canvas_w, 3), 255, dtype=np.uint8)
    for i, c in enumerate(crops):
        if c is None or c.size == 0: continue
        h, w = c.shape[:2]
        y_off = i * h_per_crop
        
        cv2.rectangle(collage, (0, y_off), (canvas_w-1, y_off + h_per_crop - 1), (0,0,0), 2)
        
        h_fit = min(h, h_per_crop - 10)
        w_fit = min(w, w_max)
        y_img = y_off + (h_per_crop - h_fit) // 2
        
        collage[y_img:y_img+h_fit, 10:10+w_fit] = c[:h_fit, :w_fit]
        cv2.putText(collage, f"ZONE V{i+1}: {cities_data[i]['name']}", (w_fit + 20, y_off + 90), 
                    cv2.FONT_HERSHEY_DUPLEX, 1.0, (0, 0, 0), 2)

    img_base64 = encode_image(collage)
    
    prompt = """Task: Identify weather icons in 5 labeled zones (V1 to V5).
Rules:
1. 'TSRA': Cloud with lightning or rain.
2. 'DUFU': Cloud with orange/brown tint (dust/sand).
3. 'NSW': No icon (just city name or empty).
Output ONLY JSON."""

    payload = {
        "model": MODEL,
        "prompt": prompt,
        "images": [img_base64],
        "stream": False,
        "options": {"temperature": 0.1},
        "format": "json"
    }

    try:
        response = requests.post(OLLAMA_URL, json=payload, timeout=300)
        content = response.json().get('response', '{}')
        predictions = json.loads(content)
        
        results = {}
        for i, city in enumerate(cities_data):
            key_num = f"V{i+1}"
            val = "NSW"
            for k, v in predictions.items():
                if key_num in k.upper():
                    v_upper = str(v).upper()
                    if "TS" in v_upper: val = "TSRA"
                    elif "DU" in v_upper: val = "DUFU"
                    else: val = "NSW"
                    break
            results[city['name']] = val
        return results
    except Exception:
        return {c['name']: "NSW" for c in cities_data}

def recognize_icons(image_path_or_buf):
    if isinstance(image_path_or_buf, (str, Path)):
        data = np.fromfile(str(image_path_or_buf), dtype=np.uint8)
        map_img = cv2.imdecode(data, cv2.IMREAD_COLOR)
    else:
        map_img = cv2.imdecode(np.frombuffer(image_path_or_buf, np.uint8), cv2.IMREAD_COLOR)

    if map_img is None: return {}

    with open(ZONES_FILE, 'r', encoding='utf-8') as f:
        zones_data = json.load(f)

    h_m, w_m = map_img.shape[:2]
    all_crops = []
    for zone in zones_data['zones']:
        cx = int((zone['x1_rel'] + zone['x2_rel']) / 2 * w_m)
        cy = int((zone['y1_rel'] + zone['y2_rel']) / 2 * h_m)
        search_size = 100
        sx1, sy1 = max(0, cx-search_size), max(0, cy-search_size)
        sx2, sy2 = min(w_m, cx+search_size), min(h_m, cy+search_size)
        all_crops.append({'name': zone['name'], 'image': map_img[sy1:sy2, sx1:sx2]})

    groups = [all_crops[0:5], all_crops[5:10]]
    final_results = {}
    with concurrent.futures.ThreadPoolExecutor(max_workers=2) as executor:
        futures = [executor.submit(call_ollama, g) for g in groups]
        for f in concurrent.futures.as_completed(futures):
            final_results.update(f.result())
            
    return final_results
