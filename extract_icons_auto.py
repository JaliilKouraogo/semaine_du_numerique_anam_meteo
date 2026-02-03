"""
extract_icons_auto.py - Extraction automatique des icônes depuis la légende de chaque carte

Pour CHAQUE carte:
1. Extrait la zone de légende (icônes + noms en français)
2. Utilise Qwen pour lire les icônes de la légende
3. Compare les icônes des villes avec celles de la légende

Usage:
    python extract_icons_auto.py --input-dir 2023_temps_specific --maps-dir 2023_maps --limit 5
"""

import cv2
import json
import numpy as np
from pathlib import Path
import argparse
import os
import base64
import requests
import re
from datetime import datetime
import threading

# ---------- CONFIG ----------
CITIES_REL_FILE = "cities_rel.json"
ICON_ZONES_FILE = "icon_zones.json"
LEGEND_CONFIG_FILE = "legend_config.json"

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
            return json.load(f).get("cities", {})
    return {}


def load_cities_rel():
    """Charge les coordonnées relatives des villes."""
    if Path(CITIES_REL_FILE).exists():
        with open(CITIES_REL_FILE, "r", encoding="utf-8") as f:
            all_cities = json.load(f)
        return {c["name"]: c for c in all_cities if c["name"] in TARGET_CITIES}
    return {}


def load_legend_config():
    """Charge la configuration de la légende calibrée."""
    if Path(LEGEND_CONFIG_FILE).exists():
        with open(LEGEND_CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def image_to_base64(img):
    """Convertit une image OpenCV en base64."""
    ok, buf = cv2.imencode(".png", img)
    if ok:
        return base64.b64encode(buf.tobytes()).decode("ascii")
    return ""


def extract_legend_from_map(img, legend_config):
    """Extrait la zone de légende de la carte selon la configuration."""
    h, w = img.shape[:2]
    
    if legend_config:
        rel = legend_config.get("legend_rect_rel", {})
        x1 = int(rel.get("x1_rel", 0.4) * w)
        y1 = int(rel.get("y1_rel", 0.8) * h)
        x2 = int(rel.get("x2_rel", 0.95) * w)
        y2 = int(rel.get("y2_rel", 0.95) * h)
    else:
        # Estimation par défaut : les 15% du bas, partie droite
        x1 = int(w * 0.4)
        y1 = int(h * 0.8)
        x2 = w
        y2 = h
    
    return img[y1:y2, x1:x2]


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


def crop_icon_zone(img, city_name, icon_zones, cities_rel, zone_size=45):
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
        
        # Offset vers le haut-gauche pour capturer l'icône
        cx = int(x0 + city["x_rel"] * map_w) - 20
        cy = int(y0 + city["y_rel"] * map_h) - 15
        size = zone_size
    else:
        return None
    
    x1 = max(0, cx - size)
    y1 = max(0, cy - size)
    x2 = min(w, cx + size)
    y2 = min(h, cy + size)
    
    crop = img[y1:y2, x1:x2]
    return crop if crop.size > 0 else None


def identify_city_icon_with_legend(city_crop, legend_img, city_name, model):
    """
    Utilise Qwen pour identifier l'icône d'une ville
    en la comparant avec la légende de la même carte.
    """
    city_b64 = image_to_base64(city_crop)
    legend_b64 = image_to_base64(legend_img)
    
    prompt = f"""Tu vois 2 images:
IMAGE 1: Zone météo de la ville "{city_name}" sur la carte
IMAGE 2: Légende de cette carte avec les icônes et leurs noms en français

Compare l'icône visible dans IMAGE 1 avec les icônes de la légende (IMAGE 2).
Réponds avec UNIQUEMENT le nom français exact de l'icône qui correspond.

Par exemple: Ciel dégagé, Ciel nuageux, Temps partiellement nuageux, Pluies faibles, Orages isolés, Pluies orageuses isolées, Poussière en suspension

Si l'icône combine météo + poussière, indique les deux.
Exemple: Ciel dégagé avec poussière, Orage avec poussière

Réponse (nom de l'icône uniquement):"""

    payload = {
        "model": model,
        "prompt": prompt,
        "images": [city_b64, legend_b64],
        "stream": False,
    }
    
    try:
        resp = requests.post(OLLAMA_URL, json=payload, timeout=TIMEOUT_SECONDS)
        resp.raise_for_status()
        data = resp.json()
        text = data.get("response", "").strip()
        
        # Nettoyer les tags <think>
        if "<think>" in text:
            text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
        
        # Prendre la première ligne non vide
        for line in text.split('\n'):
            line = line.strip()
            if line and len(line) > 3:
                # Nettoyer les caractères indésirables
                result = re.sub(r'^[-•*]\s*', '', line)
                return result[:80]
        
        return ""
        
    except requests.exceptions.Timeout:
        print(f"      [TIMEOUT]")
    except Exception as e:
        print(f"      [ERROR]: {str(e)[:30]}")
    
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


def process_json_file(json_path, maps_dir, icon_zones, cities_rel, 
                      legend_config, model, output_dir=None):
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
    
    # Extraire la légende de CETTE carte
    legend_img = extract_legend_from_map(img, legend_config)
    
    if legend_img is None or legend_img.size == 0:
        print(f"   ❌ Légende non extraite")
        return 0
    
    print(f"   📊 Légende: {legend_img.shape[1]}x{legend_img.shape[0]} px")
    
    # Charger JSON
    with open(json_path, "r", encoding="utf-8") as f:
        json_data = json.load(f)
    
    count = 0
    stations = json_data.get("stations", [])
    
    for i, station in enumerate(stations):
        city_name = station["nom"]
        
        if city_name not in TARGET_CITIES:
            continue
        
        # Crop de la zone d'icône de la ville
        city_crop = crop_icon_zone(img, city_name, icon_zones, cities_rel)
        
        if city_crop is None:
            print(f"   ✗ {city_name:<15} -> Crop échoué")
            continue
        
        # Identifier l'icône en comparant avec la légende
        icon_name = identify_city_icon_with_legend(city_crop, legend_img, city_name, model)
        
        if icon_name:
            stations[i]["weather_icon"] = icon_name
            count += 1
            print(f"   ✓ {city_name:<15} -> {icon_name}")
        else:
            print(f"   ✗ {city_name:<15} -> Non identifié")
    
    # Sauvegarder
    json_data["stations"] = stations
    json_data["_icons_auto_extracted"] = datetime.now().isoformat()
    
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
    parser = argparse.ArgumentParser(description="Extraction automatique des icônes depuis la légende")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--maps-dir", type=Path, default=DEFAULT_MAPS_DIR)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--skip-done", action="store_true")
    args = parser.parse_args()
    
    print("=" * 60)
    print("🎯 EXTRACTION AUTO DES ICÔNES (LÉGENDE DE CHAQUE CARTE)")
    print("=" * 60)
    
    # Charger les ressources
    icon_zones = load_icon_zones()
    cities_rel = load_cities_rel()
    legend_config = load_legend_config()
    
    print(f"📍 {len(icon_zones)} zones calibrées")
    print(f"📍 {len(cities_rel)} villes")
    if legend_config:
        print(f"📊 Config légende chargée")
    print(f"🤖 {args.model}")
    
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
            if "_icons_auto_extracted" not in d:
                filtered.append(jf)
        json_files = filtered
    
    if args.limit > 0:
        json_files = json_files[:args.limit]
    
    print(f"🗂️ {len(json_files)} fichiers")
    print("=" * 60)
    
    if not json_files:
        print("✅ Rien à traiter!")
        return
    
    # Traitement
    start = datetime.now()
    total = 0
    
    for jf in json_files:
        total += process_json_file(
            jf, args.maps_dir, icon_zones, cities_rel,
            legend_config, args.model, args.output_dir
        )
    
    elapsed = (datetime.now() - start).total_seconds()
    print(f"\n{'='*60}")
    print(f"✅ {total} icônes | ⏱️ {elapsed:.1f}s")
    print("=" * 60)


if __name__ == "__main__":
    main()
