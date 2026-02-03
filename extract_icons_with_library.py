"""
extract_icons_with_library.py - Extraction d'icônes avec la bibliothèque

Ce script:
1. Charge la bibliothèque d'icônes construite
2. Pour chaque carte, extrait la légende et identifie les icônes
3. Utilise le template matching pour associer les icônes aux villes
4. Gère les icônes fusionnées avec "poussière en suspension"

Usage:
    python extract_icons_with_library.py --input-dir 2023_temps_specific --maps-dir 2023_maps --limit 5
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
ICON_LIBRARY_FILE = "icon_library.json"

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

# Normalisation des noms d'icônes - LISTE COMPLÈTE
# Icônes de base
BASE_ICONS = {
    # Temps clair
    "ciel degage": "Ciel dégagé",
    "ciel dégagé": "Ciel dégagé",
    "ensoleille": "Ciel dégagé",
    "ensoleillé": "Ciel dégagé",
    "soleil": "Ciel dégagé",
    "il fait soleil": "Ciel dégagé",
    "temps ensoleille": "Ciel dégagé",
    "temps ensoleillé": "Ciel dégagé",
    
    # Nuageux
    "ciel nuageux": "Ciel nuageux",
    "nuageux": "Ciel nuageux",
    "temps nuageux": "Ciel nuageux",
    "ciel couvert": "Ciel couvert",
    
    # Partiellement nuageux
    "temps partiellement nuageux": "Temps partiellement nuageux",
    "partiellement nuageux": "Temps partiellement nuageux",
    "ciel peu nuageux": "Temps partiellement nuageux",
    "soleil nuageux": "Temps partiellement nuageux",
    
    # Pluies
    "pluie": "Pluie",
    "pluies": "Pluie",
    "pluies faibles": "Pluies faibles",
    "pluie faible": "Pluies faibles",
    
    # Orages
    "orage": "Orage",
    "orages": "Orage",
    "orages isoles": "Orages isolés",
    "orages isolés": "Orages isolés",
    "orage isole": "Orages isolés",
    "orage isolé": "Orages isolés",
    
    # Pluies orageuses
    "pluies orageuses": "Pluies orageuses",
    "pluies orageuses isolees": "Pluies orageuses isolées",
    "pluies orageuses isolées": "Pluies orageuses isolées",
    "pluie orageuse": "Pluies orageuses",
    "orages et pluies": "Orages et pluies",
    "orages avec pluies": "Orages et pluies",
    "orages avec pluies isoles": "Orages avec pluies isolées",
    "orages avec pluies isolées": "Orages avec pluies isolées",
    
    # Poussière seule
    "poussiere": "Poussière en suspension",
    "poussière": "Poussière en suspension",
    "poussiere en suspension": "Poussière en suspension",
    "poussière en suspension": "Poussière en suspension",
}

# Combinaisons avec poussière
DUST_COMBINATIONS = {
    "Ciel dégagé": "Ciel dégagé avec poussière",
    "Ciel nuageux": "Ciel nuageux avec poussière",
    "Ciel couvert": "Ciel couvert avec poussière",
    "Temps partiellement nuageux": "Temps partiellement nuageux avec poussière",
    "Pluie": "Pluie avec poussière",
    "Pluies faibles": "Pluies faibles avec poussière",
    "Orage": "Orage avec poussière",
    "Orages isolés": "Orages isolés avec poussière",
    "Pluies orageuses": "Pluies orageuses avec poussière",
    "Pluies orageuses isolées": "Pluies orageuses isolées avec poussière",
    "Orages et pluies": "Orages et pluies avec poussière",
    "Orages avec pluies isolées": "Orages avec pluies isolées avec poussière",
}

# Liste complète de toutes les icônes possibles
ALL_VALID_ICONS = [
    # Sans poussière
    "Ciel dégagé",
    "Ciel nuageux",
    "Ciel couvert",
    "Temps partiellement nuageux",
    "Pluie",
    "Pluies faibles",
    "Orage",
    "Orages isolés",
    "Pluies orageuses",
    "Pluies orageuses isolées",
    "Orages et pluies",
    "Orages avec pluies isolées",
    "Poussière en suspension",
    # Avec poussière
    "Ciel dégagé avec poussière",
    "Ciel nuageux avec poussière",
    "Ciel couvert avec poussière",
    "Temps partiellement nuageux avec poussière",
    "Pluie avec poussière",
    "Pluies faibles avec poussière",
    "Orage avec poussière",
    "Orages isolés avec poussière",
    "Pluies orageuses avec poussière",
    "Pluies orageuses isolées avec poussière",
    "Orages et pluies avec poussière",
    "Orages avec pluies isolées avec poussière",
]


def normalize_icon_name(name):
    """Normalise le nom d'une icône et gère les combinaisons avec poussière."""
    if not name:
        return ""
    
    name_lower = name.lower().strip()
    
    # Mots-clés de poussière
    dust_keywords = ["poussiere", "poussière", "poussieres", "poussières"]
    
    # Vérifier si c'est une combinaison avec poussière
    has_dust = any(dust in name_lower for dust in dust_keywords)
    
    # Nettoyer le nom de la partie poussière pour trouver l'icône de base
    clean_name = name_lower
    if has_dust:
        for dust_phrase in ["poussiere en suspension", "poussière en suspension",
                            "poussieres en suspension", "poussières en suspension",
                            "avec poussiere", "avec poussière",
                            "poussiere", "poussière"]:
            clean_name = clean_name.replace(dust_phrase, "").strip()
    
    # Chercher une correspondance pour l'icône de base
    base_name = ""
    
    # D'abord essayer une correspondance exacte
    if clean_name in BASE_ICONS:
        base_name = BASE_ICONS[clean_name]
    else:
        # Chercher une correspondance partielle (priorité aux plus longs)
        matches = []
        for key, value in BASE_ICONS.items():
            if key in clean_name:
                matches.append((len(key), key, value))
        
        if matches:
            # Prendre la correspondance la plus longue
            matches.sort(reverse=True)
            base_name = matches[0][2]
    
    # Si pas de correspondance, garder le nom original nettoyé
    if not base_name:
        # Capitaliser proprement
        if clean_name:
            base_name = clean_name.title()
        else:
            base_name = name.title()
    
    # Ajouter "avec poussière" si nécessaire
    if has_dust:
        # Éviter les doublons
        if "poussière" not in base_name.lower() and "poussiere" not in base_name.lower():
            # Si l'icône de base est juste de la poussière
            if base_name == "Poussière en suspension" or not base_name.strip():
                return "Poussière en suspension"
            # Utiliser DUST_COMBINATIONS si disponible
            if base_name in DUST_COMBINATIONS:
                return DUST_COMBINATIONS[base_name]
            # Sinon, ajouter manuellement
            return f"{base_name} avec poussière"
    
    return base_name


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
    """Charge la configuration de la légende."""
    if Path(LEGEND_CONFIG_FILE).exists():
        with open(LEGEND_CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def load_icon_library():
    """Charge la bibliothèque d'icônes."""
    if Path(ICON_LIBRARY_FILE).exists():
        with open(ICON_LIBRARY_FILE, "r", encoding="utf-8") as f:
            lib = json.load(f)
        
        # Charger les templates
        templates = []
        for icon in lib.get("icons", []):
            img_path = icon.get("image_path")
            if img_path and Path(img_path).exists():
                data = np.fromfile(img_path, dtype=np.uint8)
                template = cv2.imdecode(data, cv2.IMREAD_COLOR)
                if template is not None:
                    templates.append({
                        "name": icon["name"],
                        "normalized_name": normalize_icon_name(icon["name"]),
                        "template": template
                    })
        
        return templates
    return []


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


def extract_legend_region(img, config):
    """Extrait la zone de légende."""
    h, w = img.shape[:2]
    
    rel = config.get("legend_rect_rel", {})
    x1 = int(rel.get("x1_rel", 0.4) * w)
    y1 = int(rel.get("y1_rel", 0.8) * h)
    x2 = int(rel.get("x2_rel", 0.95) * w)
    y2 = int(rel.get("y2_rel", 0.95) * h)
    
    return img[y1:y2, x1:x2]


def image_to_base64(img):
    """Convertit une image en base64."""
    ok, buf = cv2.imencode(".png", img)
    if ok:
        return base64.b64encode(buf.tobytes()).decode("ascii")
    return ""


def crop_icon_zone(img, city_name, icon_zones, cities_rel, zone_size=40):
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
    
    x1 = max(0, cx - size)
    y1 = max(0, cy - size)
    x2 = min(w, cx + size)
    y2 = min(h, cy + size)
    
    crop = img[y1:y2, x1:x2]
    return crop if crop.size > 0 else None


def match_icon_template(crop, templates, threshold=0.25):
    """Match le crop avec les templates de la bibliothèque."""
    if crop is None or crop.size == 0:
        return "", 0
    
    crop_gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    
    best_name = ""
    best_score = 0
    
    for tmpl in templates:
        template = tmpl["template"]
        template_gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
        
        for scale in [0.3, 0.4, 0.5, 0.6, 0.7, 0.8]:
            new_w = int(template_gray.shape[1] * scale)
            new_h = int(template_gray.shape[0] * scale)
            
            if new_w <= 0 or new_h <= 0:
                continue
            if new_w > crop_gray.shape[1] or new_h > crop_gray.shape[0]:
                continue
            
            resized = cv2.resize(template_gray, (new_w, new_h))
            
            try:
                result = cv2.matchTemplate(crop_gray, resized, cv2.TM_CCOEFF_NORMED)
                _, max_val, _, _ = cv2.minMaxLoc(result)
                
                if max_val > best_score:
                    best_score = max_val
                    best_name = tmpl["normalized_name"]
            except:
                continue
    
    if best_score >= threshold:
        return best_name, best_score
    
    return "", best_score


def identify_icon_with_qwen(crop, legend_img, model):
    """Fallback: utilise Qwen pour identifier l'icône."""
    crop_b64 = image_to_base64(crop)
    legend_b64 = image_to_base64(legend_img)
    
    prompt = """IMAGE 1: Weather icon from the map.
IMAGE 2: Legend from the same map.

Compare the icon and identify which weather type it represents.
Answer with ONLY the French weather description.

Examples: Ciel dégagé, Ciel nuageux, Pluie, Orage, Temps partiellement nuageux

Answer:"""

    payload = {
        "model": model,
        "prompt": prompt,
        "images": [crop_b64, legend_b64],
        "stream": False,
    }
    
    try:
        resp = requests.post(OLLAMA_URL, json=payload, timeout=TIMEOUT_SECONDS)
        resp.raise_for_status()
        data = resp.json()
        text = data.get("response", "").strip()
        
        if "<think>" in text:
            text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
        
        result = text.split('\n')[0].strip()
        return normalize_icon_name(result)
        
    except:
        pass
    
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
                      legend_config, templates, model, output_dir=None):
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
    
    # Extraire la légende
    legend_img = extract_legend_region(img, legend_config) if legend_config else None
    
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
        crop = crop_icon_zone(img, city_name, icon_zones, cities_rel)
        
        if crop is None:
            print(f"   ✗ {city_name:<15} -> Crop échoué")
            continue
        
        # D'abord essayer le template matching
        icon_name, score = match_icon_template(crop, templates)
        
        if icon_name and score >= 0.25:
            stations[i]["weather_icon"] = icon_name
            stations[i]["match_score"] = round(score, 3)
            count += 1
            print(f"   ✓ {city_name:<15} -> {icon_name} ({score:.2f})")
        else:
            # Fallback sur Qwen
            if legend_img is not None and legend_img.size > 0:
                icon_name = identify_icon_with_qwen(crop, legend_img, model)
                if icon_name:
                    stations[i]["weather_icon"] = icon_name
                    count += 1
                    print(f"   ✓ {city_name:<15} -> {icon_name} (qwen)")
                else:
                    print(f"   ✗ {city_name:<15} -> Non identifié")
            else:
                print(f"   ✗ {city_name:<15} -> Template: {score:.2f}")
    
    # Sauvegarder
    json_data["stations"] = stations
    json_data["_icons_library_extracted"] = datetime.now().isoformat()
    
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
    parser = argparse.ArgumentParser(description="Extraction d'icônes avec bibliothèque")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--maps-dir", type=Path, default=DEFAULT_MAPS_DIR)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--skip-done", action="store_true")
    args = parser.parse_args()
    
    print("=" * 60)
    print("🎯 EXTRACTION D'ICÔNES AVEC BIBLIOTHÈQUE")
    print("=" * 60)
    
    # Charger les ressources
    icon_zones = load_icon_zones()
    cities_rel = load_cities_rel()
    legend_config = load_legend_config()
    templates = load_icon_library()
    
    print(f"📍 {len(icon_zones)} zones calibrées")
    print(f"📍 {len(cities_rel)} villes")
    print(f"📚 {len(templates)} templates")
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
            if "_icons_library_extracted" not in d:
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
            legend_config, templates, args.model, args.output_dir
        )
    
    elapsed = (datetime.now() - start).total_seconds()
    print(f"\n{'='*60}")
    print(f"✅ {total} icônes | ⏱️ {elapsed:.1f}s")
    print("=" * 60)


if __name__ == "__main__":
    main()
