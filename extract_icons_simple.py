"""
extract_icons_simple.py - Extraction simple par Template Matching

Utilise UNIQUEMENT le template matching avec le dossier icon_templates/
Pas de Qwen, pas de légende - juste comparaison d'images.

Usage:
    python extract_icons_simple.py --input-dir 2023_temps_specific --maps-dir 2023_maps --limit 10
"""

import cv2
import json
import numpy as np
from pathlib import Path
import argparse
import os
from datetime import datetime

# ---------- CONFIG ----------
CITIES_REL_FILE = "cities_rel.json"
ICON_ZONES_FILE = "icon_zones.json"
ICON_TEMPLATES_DIR = Path("icon_templates")

DEFAULT_INPUT_DIR = Path("2024_temps_specific")
DEFAULT_MAPS_DIR = Path("2024_maps")

# Villes cibles
TARGET_CITIES = [
    "DORI", "OUAHIGOUYA", "OUAGADOUGOU", "BOGANDE", "DEDOUGOU",
    "FADA NGOURMA", "BOBO DIOULASSO", "BOROMO", "PO", "GAOUA"
]

# Mapping des fichiers template vers les noms d'icônes
TEMPLATE_NAMES = {
    "icon_00_Pluies_orageuses_isolees.png": "Pluies orageuses isolées",
    "icon_01_Orages_isoles.png": "Orages isolés",
    "icon_02_Pluies_faibles.png": "Pluies faibles",
    "icon_03_Ciel_nuageux.png": "Ciel nuageux",
    "icon_04_Temps_partiellement_nuage.png": "Temps partiellement nuageux",
    "icon_05_Ciel_degage.png": "Ciel dégagé",
    "icon_06_Poussiere_en_suspension.png": "Poussière en suspension",
    "icon_07_Pluie_orageuse.png": "Pluie orageuse",
    "icon_08_Orage.png": "Orage",
    "icon_09_Pluie.png": "Pluie",
    "icon_10_Ciel_couvert.png": "Ciel couvert",
    "icon_11_Ciel_nuageux_2.png": "Ciel nuageux",
}


def load_templates():
    """Charge tous les templates d'icônes."""
    templates = []
    
    if not ICON_TEMPLATES_DIR.exists():
        print(f"❌ Dossier {ICON_TEMPLATES_DIR} non trouvé!")
        return templates
    
    for png_file in sorted(ICON_TEMPLATES_DIR.glob("*.png")):
        data = np.fromfile(str(png_file), dtype=np.uint8)
        img = cv2.imdecode(data, cv2.IMREAD_COLOR)
        
        if img is not None:
            name = TEMPLATE_NAMES.get(png_file.name, png_file.stem.replace("_", " "))
            templates.append({
                "name": name,
                "filename": png_file.name,
                "image": img,
                "gray": cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            })
    
    return templates


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


def crop_icon_zone(img, city_name, icon_zones, cities_rel, zone_size=50):
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


def match_template(crop, templates, threshold=0.4):
    """
    Compare le crop avec tous les templates.
    Retourne le meilleur match.
    """
    if crop is None or crop.size == 0:
        return "", 0.0
    
    crop_gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    crop_h, crop_w = crop_gray.shape
    
    best_name = ""
    best_score = 0.0
    
    for tmpl in templates:
        template_gray = tmpl["gray"]
        tmpl_h, tmpl_w = template_gray.shape
        tmpl_name = tmpl["name"]
        
        # Tester plusieurs échelles
        for scale in [0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.5]:
            new_w = int(tmpl_w * scale)
            new_h = int(tmpl_h * scale)
            
            if new_w <= 0 or new_h <= 0 or new_w > crop_w or new_h > crop_h:
                continue
            
            resized = cv2.resize(template_gray, (new_w, new_h))
            
            try:
                result = cv2.matchTemplate(crop_gray, resized, cv2.TM_CCOEFF_NORMED)
                _, max_val, _, _ = cv2.minMaxLoc(result)
                
                if max_val > best_score:
                    best_score = max_val
                    best_name = tmpl_name
            except:
                continue
    
    if best_score >= threshold:
        return best_name, best_score
    
    return "", best_score


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


def process_json_file(json_path, maps_dir, icon_zones, cities_rel, templates, output_dir=None):
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
        
        # Template matching
        icon_name, score = match_template(crop, templates)
        
        if icon_name:
            stations[i]["weather_icon"] = icon_name
            stations[i]["match_score"] = round(score, 3)
            count += 1
            print(f"   ✓ {city_name:<15} -> {icon_name} ({score:.2f})")
        else:
            print(f"   ✗ {city_name:<15} -> Score: {score:.2f}")
    
    # Sauvegarder
    json_data["stations"] = stations
    json_data["_icons_template_matched"] = datetime.now().isoformat()
    
    if output_dir:
        rel_subdir = json_path.parent.name
        out_subdir = output_dir / rel_subdir
        os.makedirs(out_subdir, exist_ok=True)
        out_path = out_subdir / json_path.name
    else:
        out_path = json_path
    
    with open(out_path, "w", encoding="utf-8") as f:
        json.dump(json_data, f, ensure_ascii=False, indent=2)
    
    print(f"   💾 {count} icônes")
    return count


def main():
    parser = argparse.ArgumentParser(description="Extraction simple par template matching")
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--maps-dir", type=Path, default=DEFAULT_MAPS_DIR)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--skip-done", action="store_true")
    parser.add_argument("--threshold", type=float, default=0.4)
    args = parser.parse_args()
    
    print("=" * 60)
    print("🎯 EXTRACTION PAR TEMPLATE MATCHING")
    print("=" * 60)
    
    # Charger les templates
    templates = load_templates()
    print(f"📚 {len(templates)} templates chargés")
    for t in templates:
        print(f"   - {t['name']}")
    
    # Charger les ressources
    icon_zones = load_icon_zones()
    cities_rel = load_cities_rel()
    
    print(f"📍 {len(icon_zones)} zones calibrées")
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
            if "_icons_template_matched" not in d:
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
        total += process_json_file(jf, args.maps_dir, icon_zones, cities_rel, templates, args.output_dir)
    
    elapsed = (datetime.now() - start).total_seconds()
    print(f"\n{'='*60}")
    print(f"✅ {total} icônes | ⏱️ {elapsed:.1f}s")
    print("=" * 60)


if __name__ == "__main__":
    main()
