"""
extract_icons_from_map_legend.py - Extraction d'icônes depuis la légende de la carte

Ce script:
1. Extrait automatiquement la légende en bas de chaque carte
2. Utilise Qwen pour lire les icônes et leurs noms depuis la légende
3. Compare les icônes près des villes avec celles identifiées dans la légende

Avantage: Utilise la légende PRÉSENTE dans la carte, pas une image externe.

Usage:
    python extract_icons_from_map_legend.py --input-dir 2023_temps_specific --maps-dir 2023_maps --limit 5
"""

import cv2
import json
import os
import re
import base64
import requests
import numpy as np
from pathlib import Path
from datetime import datetime
import argparse
import threading

# ---------- CONFIG ----------
CITIES_REL_FILE = "cities_rel.json"
ICON_ZONES_FILE = "icon_zones.json"
DEFAULT_INPUT_DIR = Path("2024_temps_specific")
DEFAULT_MAPS_DIR = Path("2024_maps")

OLLAMA_URL = "http://localhost:11434/api/generate"
DEFAULT_MODEL = "qwen3-vl:8b"
TIMEOUT_SECONDS = 120

file_lock = threading.Lock()

# Villes cibles
TARGET_CITIES = [
    "DORI", "OUAHIGOUYA", "OUAGADOUGOU", "BOGANDE", "DEDOUGOU",
    "FADA NGOURMA", "BOBO DIOULASSO", "BOROMO", "PO", "GAOUA"
]


def load_icon_zones():
    """Charge les zones d'icônes calibrées."""
    if Path(ICON_ZONES_FILE).exists():
        with open(ICON_ZONES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        return data.get("cities", {}), data.get("zone_size_default", 40)
    return {}, 40


def load_cities_rel():
    """Charge les coordonnées relatives des villes."""
    if Path(CITIES_REL_FILE).exists():
        with open(CITIES_REL_FILE, "r", encoding="utf-8") as f:
            all_cities = json.load(f)
        return {c["name"]: c for c in all_cities if c["name"] in TARGET_CITIES}
    return {}


def detect_map_bbox(img):
    """Détecte les limites de la carte."""
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)
    _, thresh = cv2.threshold(blur, 0, 255, cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    h, w = gray.shape
    img_area = w * h
    best = None
    best_area = 0
    
    for cnt in contours:
        x, y, cw, ch = cv2.boundingRect(cnt)
        area = cw * ch
        if 0.05 * img_area < area < 0.9 * img_area and area > best_area:
            best_area = area
            best = (x, y, cw, ch)
    
    if best is None:
        return 0, 0, w, h
    
    x, y, cw, ch = best
    return x, y, x + cw, y + ch


def extract_legend_from_map(img):
    """
    Extrait la zone de légende en bas de la carte.
    La légende contient les icônes avec leurs noms.
    """
    h, w = img.shape[:2]
    
    # La légende est généralement dans les 15% du bas de la carte
    # et commence à environ 40% de la largeur (après le texte)
    legend_top = int(h * 0.78)
    legend_left = int(w * 0.25)
    legend_right = int(w * 0.95)
    
    legend = img[legend_top:h, legend_left:legend_right]
    
    return legend


def image_to_base64(img):
    """Convertit une image OpenCV en base64."""
    ok, buf = cv2.imencode(".png", img)
    if ok:
        return base64.b64encode(buf.tobytes()).decode("ascii")
    return ""


def extract_legend_icons_with_qwen(legend_img, model):
    """
    Utilise Qwen pour lire la légende et identifier les icônes avec leurs noms.
    Retourne un dictionnaire {description: icon_image_base64}
    """
    legend_b64 = image_to_base64(legend_img)
    
    prompt = """Look at this weather legend image.
List ALL the weather icons and their French names that you can see.

Format your response as a simple list, one per line:
- [icon description]

Example response:
- Temps partiellement nuageux
- Ciel nuageux
- Pluies faibles
- Orages isoles
- Pluies orageuses isolees
- Orages et pluies

List all icons you see:"""

    payload = {
        "model": model,
        "prompt": prompt,
        "images": [legend_b64],
        "stream": False,
    }
    
    try:
        resp = requests.post(OLLAMA_URL, json=payload, timeout=TIMEOUT_SECONDS)
        resp.raise_for_status()
        data = resp.json()
        text = data.get("response", "").strip()
        
        # Nettoyer <think> tags
        if "<think>" in text:
            text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
        
        # Parser les icônes trouvées
        icons = []
        for line in text.split('\n'):
            line = line.strip()
            if line.startswith('-'):
                icon_name = line[1:].strip()
                if icon_name:
                    icons.append(icon_name)
        
        return icons
        
    except Exception as e:
        print(f"   [ERROR] Lecture légende: {str(e)[:50]}")
    
    return []


def crop_icon_zone(img, city_name, icon_zones, cities_rel, zone_size):
    """Crop la zone d'icône pour une ville."""
    h, w = img.shape[:2]
    
    if city_name in icon_zones:
        zone = icon_zones[city_name]
        cx = int(zone["x_rel"] * w)
        cy = int(zone["y_rel"] * h)
        size = zone.get("zone_size", zone_size)
    elif city_name in cities_rel:
        city = cities_rel[city_name]
        try:
            x0, y0, x1, y1 = detect_map_bbox(img)
        except:
            x0, y0, x1, y1 = 0, 0, w, h
        
        map_w = x1 - x0
        map_h = y1 - y0
        
        cx = int(x0 + city["x_rel"] * map_w) - 15
        cy = int(y0 + city["y_rel"] * map_h) - 10
        size = zone_size
    else:
        return None
    
    x1c = max(0, cx - size)
    y1c = max(0, cy - size)
    x2c = min(w, cx + size)
    y2c = min(h, cy + size)
    
    crop = img[y1c:y2c, x1c:x2c]
    
    if crop.size == 0:
        return None
    
    return crop


def identify_icon_with_legend(icon_crop, legend_img, legend_icons, city_name, model):
    """
    Identifie l'icône d'une ville en la comparant avec la légende.
    """
    icon_b64 = image_to_base64(icon_crop)
    legend_b64 = image_to_base64(legend_img)
    
    # Liste des icônes trouvées dans la légende
    icons_list = "\n".join(f"- {icon}" for icon in legend_icons)
    
    prompt = f"""IMAGE 1: Weather icon near the city "{city_name}"
IMAGE 2: Legend from the same map

Compare the icon in IMAGE 1 with the icons in the legend (IMAGE 2).
Which icon from the legend matches?

Available icons in this legend:
{icons_list}

Reply with ONLY the matching icon name from the list above.
If unsure, pick the closest match.

Answer:"""

    payload = {
        "model": model,
        "prompt": prompt,
        "images": [icon_b64, legend_b64],
        "stream": False,
    }
    
    try:
        resp = requests.post(OLLAMA_URL, json=payload, timeout=TIMEOUT_SECONDS)
        resp.raise_for_status()
        data = resp.json()
        text = data.get("response", "").strip()
        
        # Nettoyer
        if "<think>" in text:
            text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
        
        result = text.split('\n')[0].strip()
        
        # Valider contre les icônes de la légende
        for icon in legend_icons:
            if icon.lower() in result.lower() or result.lower() in icon.lower():
                return icon
        
        return result[:50] if result else ""
        
    except requests.exceptions.Timeout:
        print(f"      [TIMEOUT] {city_name}")
    except Exception as e:
        print(f"      [ERROR] {city_name}: {str(e)[:40]}")
    
    return ""


def find_map_for_json(json_path: Path, maps_dir: Path):
    """Trouve le fichier image source."""
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    source_image = data.get("source_image", "")
    if not source_image:
        return None
    
    rel_dir = json_path.parent.name
    for p in [maps_dir / rel_dir / source_image, maps_dir / source_image]:
        if p.exists():
            return p
    
    for p in maps_dir.rglob(source_image):
        return p
    
    return None


def process_json_file(json_path, maps_dir, icon_zones, cities_rel, zone_size, 
                      model, output_dir=None):
    """Traite un fichier JSON."""
    print(f"\n📄 {json_path.name}")
    
    map_path = find_map_for_json(json_path, maps_dir)
    if map_path is None:
        print(f"   ❌ Image source introuvable")
        return 0
    
    # Charger l'image
    try:
        data = np.fromfile(str(map_path), dtype=np.uint8)
        img = cv2.imdecode(data, cv2.IMREAD_COLOR)
    except Exception as e:
        print(f"   ❌ Erreur: {e}")
        return 0
    
    if img is None:
        return 0
    
    # Extraire la légende de cette carte
    legend_img = extract_legend_from_map(img)
    print(f"   📊 Légende extraite: {legend_img.shape[1]}x{legend_img.shape[0]}")
    
    # Lire les icônes de la légende avec Qwen
    legend_icons = extract_legend_icons_with_qwen(legend_img, model)
    if legend_icons:
        print(f"   📋 Icônes trouvées: {', '.join(legend_icons[:5])}...")
    else:
        print(f"   ⚠️ Aucune icône lue dans la légende")
        # Fallback sur une liste par défaut
        legend_icons = [
            "Temps partiellement nuageux",
            "Ciel nuageux", 
            "Pluies faibles",
            "Orages isoles",
            "Pluies orageuses isolees",
            "Orages et pluies"
        ]
    
    # Charger JSON
    with open(json_path, "r", encoding="utf-8") as f:
        json_data = json.load(f)
    
    count = 0
    stations = json_data.get("stations", [])
    
    for i, station in enumerate(stations):
        city_name = station["nom"]
        
        if city_name not in TARGET_CITIES:
            continue
        
        # Crop de la zone d'icône
        crop = crop_icon_zone(img, city_name, icon_zones, cities_rel, zone_size)
        
        if crop is None:
            print(f"   ✗ {city_name:<15} -> Crop échoué")
            continue
        
        # Identifier l'icône
        icon = identify_icon_with_legend(crop, legend_img, legend_icons, city_name, model)
        
        if icon:
            stations[i]["weather_icon"] = icon
            count += 1
            print(f"   ✓ {city_name:<15} -> {icon}")
        else:
            print(f"   ✗ {city_name:<15} -> Non identifié")
    
    # Sauvegarder
    json_data["stations"] = stations
    json_data["_icons_from_map_legend"] = datetime.now().isoformat()
    json_data["_legend_icons_detected"] = legend_icons
    
    if output_dir:
        rel_subdir = json_path.parent.name
        out_subdir = output_dir / rel_subdir
        os.makedirs(out_subdir, exist_ok=True)
        out_path = out_subdir / json_path.name
    else:
        out_path = json_path
    
    with file_lock:
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(json_data, f, ensure_ascii=False, indent=2)
    
    print(f"   💾 {count} icônes")
    return count


def main():
    parser = argparse.ArgumentParser(description="Extraction d'icônes depuis la légende de la carte")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--maps-dir", type=Path, default=DEFAULT_MAPS_DIR)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--skip-done", action="store_true")
    args = parser.parse_args()
    
    print("=" * 60)
    print("🎯 EXTRACTION D'ICÔNES DEPUIS LÉGENDE DE LA CARTE")
    print("=" * 60)
    
    # Charger les zones calibrées
    icon_zones, zone_size = load_icon_zones()
    if icon_zones:
        print(f"✓ {len(icon_zones)} zones calibrées")
    
    # Fallback sur cities_rel
    cities_rel = load_cities_rel()
    print(f"📍 {len(cities_rel)} villes")
    
    if args.output_dir:
        os.makedirs(args.output_dir, exist_ok=True)
        print(f"📂 Sortie: {args.output_dir}")
    
    # Fichiers JSON
    json_files = sorted(args.input_dir.rglob("*.json"))
    json_files = [f for f in json_files if ".cache" not in str(f)]
    
    if args.skip_done:
        filtered = []
        for jf in json_files:
            with open(jf, "r", encoding="utf-8") as f:
                d = json.load(f)
            if "_icons_from_map_legend" not in d:
                filtered.append(jf)
        json_files = filtered
    
    if args.limit > 0:
        json_files = json_files[:args.limit]
    
    print(f"🗂️ {len(json_files)} fichiers")
    print(f"🤖 {args.model}")
    print("=" * 60)
    
    if not json_files:
        print("✅ Rien à traiter!")
        return
    
    # Traitement
    start = datetime.now()
    total = 0
    
    for jf in json_files:
        total += process_json_file(
            jf, args.maps_dir, icon_zones, cities_rel, zone_size,
            args.model, args.output_dir
        )
    
    elapsed = (datetime.now() - start).total_seconds()
    print(f"\n{'='*60}")
    print(f"✅ {total} icônes | ⏱️ {elapsed:.1f}s")
    print("=" * 60)


if __name__ == "__main__":
    main()
