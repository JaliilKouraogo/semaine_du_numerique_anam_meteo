"""
extract_icons_qwen.py - Extraction d'icônes avec Qwen et zones calibrées

Ce script utilise:
1. Les zones d'icônes calibrées (icon_zones.json)
2. La légende extraite de la carte
3. Qwen pour identifier chaque icône

Usage:
    # Avec zones calibrées
    python extract_icons_qwen.py --input-dir 2023_temps_specific --maps-dir 2023_maps

    # Avec légende auto-extraite de chaque carte
    python extract_icons_qwen.py --input-dir 2023_temps_specific --maps-dir 2023_maps --auto-legend
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
TIMEOUT_SECONDS = 90

file_lock = threading.Lock()

# Villes cibles
TARGET_CITIES = [
    "DORI", "OUAHIGOUYA", "OUAGADOUGOU", "BOGANDE", "DEDOUGOU",
    "FADA NGOURMA", "BOBO DIOULASSO", "BOROMO", "PO", "GAOUA"
]

# Icônes possibles (depuis legend_icons.png)
VALID_ICONS = [
    "Pluies orageuses isolees",
    "Orages isoles",
    "Pluies faibles",
    "Ciel nuageux",
    "Temps partiellement nuageux",
    "Ciel degage",
    "Poussiere en suspension",
    "Pluie orageuse",
    "Orage",
    "Pluie",
    "Ciel couvert",
]


def load_icon_zones():
    """Charge les zones d'icônes calibrées."""
    if not Path(ICON_ZONES_FILE).exists():
        print(f"⚠️ Fichier {ICON_ZONES_FILE} non trouvé")
        print("   Utilisez d'abord: python calibrate_icon_zones.py --map <carte>")
        return None, 40
    
    with open(ICON_ZONES_FILE, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    return data.get("cities", {}), data.get("zone_size_default", 40)


def load_cities_rel():
    """Charge les coordonnées relatives des villes (fallback)."""
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
    """Extrait la légende du bas de la carte."""
    h, w = img.shape[:2]
    
    # La légende est dans les 15-20% du bas
    legend_top = int(h * 0.82)
    legend = img[legend_top:h, :]
    
    return legend


def crop_icon_zone(img, city_name, icon_zones, cities_rel, zone_size):
    """Crop la zone d'icône pour une ville."""
    h, w = img.shape[:2]
    
    # Priorité aux zones calibrées
    if city_name in icon_zones:
        zone = icon_zones[city_name]
        cx = int(zone["x_rel"] * w)
        cy = int(zone["y_rel"] * h)
        size = zone.get("zone_size", zone_size)
    elif city_name in cities_rel:
        # Fallback sur cities_rel avec offset pour l'icône
        city = cities_rel[city_name]
        
        # Détecter la zone de carte
        try:
            x0, y0, x1, y1 = detect_map_bbox(img)
        except:
            x0, y0, x1, y1 = 0, 0, w, h
        
        map_w = x1 - x0
        map_h = y1 - y0
        
        cx = int(x0 + city["x_rel"] * map_w) - 15  # Offset pour l'icône
        cy = int(y0 + city["y_rel"] * map_h) - 10
        size = zone_size
    else:
        return None
    
    # Extraire le crop
    x1 = max(0, cx - size)
    y1 = max(0, cy - size)
    x2 = min(w, cx + size)
    y2 = min(h, cy + size)
    
    crop = img[y1:y2, x1:x2]
    
    if crop.size == 0:
        return None
    
    return crop


def image_to_base64(img):
    """Convertit une image OpenCV en base64."""
    ok, buf = cv2.imencode(".png", img)
    if ok:
        return base64.b64encode(buf.tobytes()).decode("ascii")
    return ""


def call_qwen_for_icon(icon_crop, legend_img, city_name, model):
    """Appelle Qwen pour identifier l'icône."""
    
    icon_b64 = image_to_base64(icon_crop)
    legend_b64 = image_to_base64(legend_img) if legend_img is not None else ""
    
    images = [icon_b64]
    if legend_b64:
        images.append(legend_b64)
    
    # Liste des icônes valides pour le prompt
    icons_list = "\n".join(f"- {icon}" for icon in VALID_ICONS)
    
    prompt = f"""Look at IMAGE 1 showing the weather icon for {city_name}.
{"Compare with the legend in IMAGE 2." if legend_b64 else ""}

Identify the weather icon. Choose EXACTLY one from this list:
{icons_list}

Reply with ONLY the icon name, nothing else.
Example: Ciel couvert
Example: Pluie orageuse  
Example: Temps partiellement nuageux

Answer:"""

    payload = {
        "model": model,
        "prompt": prompt,
        "images": images,
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
        
        # Prendre la première ligne
        result = text.split('\n')[0].strip()
        
        # Valider contre la liste
        for valid in VALID_ICONS:
            if valid.lower() in result.lower() or result.lower() in valid.lower():
                return valid
        
        # Si pas de match exact, retourner tel quel
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
                      model, output_dir=None, use_legend=True):
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
    
    # Extraire la légende si demandé
    legend_img = extract_legend_from_map(img) if use_legend else None
    
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
        
        # Appel Qwen
        icon = call_qwen_for_icon(crop, legend_img, city_name, model)
        
        if icon:
            stations[i]["weather_icon"] = icon
            count += 1
            print(f"   ✓ {city_name:<15} -> {icon}")
        else:
            print(f"   ✗ {city_name:<15} -> Non identifié")
    
    # Sauvegarder
    json_data["stations"] = stations
    json_data["_icons_qwen_extracted"] = datetime.now().isoformat()
    
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
    parser = argparse.ArgumentParser(description="Extraction d'icônes avec Qwen")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--maps-dir", type=Path, default=DEFAULT_MAPS_DIR)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--auto-legend", action="store_true", help="Extraire la légende de chaque carte")
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--skip-done", action="store_true")
    args = parser.parse_args()
    
    print("=" * 60)
    print("🎯 EXTRACTION D'ICÔNES AVEC QWEN")
    print("=" * 60)
    
    # Charger les zones calibrées
    icon_zones, zone_size = load_icon_zones()
    if icon_zones:
        print(f"✓ {len(icon_zones)} zones calibrées chargées")
    
    # Fallback sur cities_rel
    cities_rel = load_cities_rel()
    print(f"📍 {len(cities_rel)} villes (fallback)")
    
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
            if "_icons_qwen_extracted" not in d:
                filtered.append(jf)
        json_files = filtered
    
    if args.limit > 0:
        json_files = json_files[:args.limit]
    
    print(f"🗂️ {len(json_files)} fichiers à traiter")
    print(f"🤖 Modèle: {args.model}")
    print("=" * 60)
    
    if not json_files:
        print("✅ Rien à traiter!")
        return
    
    # Traitement
    start = datetime.now()
    total = 0
    
    for jf in json_files:
        total += process_json_file(
            jf, args.maps_dir, icon_zones or {}, cities_rel, zone_size,
            args.model, args.output_dir, args.auto_legend
        )
    
    elapsed = (datetime.now() - start).total_seconds()
    print(f"\n{'='*60}")
    print(f"✅ {total} icônes | ⏱️ {elapsed:.1f}s")
    print("=" * 60)


if __name__ == "__main__":
    main()
