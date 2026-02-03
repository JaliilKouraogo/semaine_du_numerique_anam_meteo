"""
fix_icons_template.py - Extraction d'icônes par Template Matching (OpenCV)

Utilise legend_icons.png qui contient les icônes EXACTEMENT comme sur les cartes.

Icônes disponibles:
- Pluies orageuses isolées
- Orages isolés  
- Pluies faibles
- Ciel nuageux
- Temps partiellement nuageux
- Ciel dégagé
- Poussière en suspension
- Pluie orageuse
- Orage
- Pluie
- Ciel couvert
- Ciel nuageux

Usage:
    python fix_icons_template.py --extract-icons
    python fix_icons_template.py --input-dir 2023_temps_specific --maps-dir 2023_maps --limit 5
"""

import cv2
import json
import os
import numpy as np
from pathlib import Path
from datetime import datetime
import argparse
import threading

# ---------- CONFIG ----------
CITIES_REL_FILE = "cities_rel.json"
DEFAULT_INPUT_DIR = Path("2024_temps_specific")
DEFAULT_MAPS_DIR = Path("2024_maps")
ICONS_DIR = Path("icon_templates")

# Image de légende avec les icônes réelles de la carte
LEGEND_ICONS = "legend_icons.png"

file_lock = threading.Lock()

# ---------- VILLES CIBLÉES ----------
TARGET_CITIES = [
    "DORI", "OUAHIGOUYA", "OUAGADOUGOU", "BOGANDE", "DEDOUGOU",
    "FADA NGOURMA", "BOBO DIOULASSO", "BOROMO", "PO", "GAOUA"
]

# ---------- DÉFINITION DES ICÔNES (depuis legend_icons.png) ----------
# 12 icônes dans l'image, de gauche à droite
ICONS_DEFINITIONS = [
    (0, "Pluies orageuses isolees"),
    (1, "Orages isoles"),
    (2, "Pluies faibles"),
    (3, "Ciel nuageux"),
    (4, "Temps partiellement nuageux"),
    (5, "Ciel degage"),
    (6, "Poussiere en suspension"),
    (7, "Pluie orageuse"),
    (8, "Orage"),
    (9, "Pluie"),
    (10, "Ciel couvert"),
    (11, "Ciel nuageux 2"),
]


def extract_icons_from_legend(legend_path: str, icons_info: list, output_dir: Path):
    """
    Extrait les icônes individuelles de legend_icons.png
    """
    if not Path(legend_path).exists():
        print(f"❌ Image non trouvée: {legend_path}")
        return []
    
    # Charger l'image
    data = np.fromfile(legend_path, dtype=np.uint8)
    img = cv2.imdecode(data, cv2.IMREAD_COLOR)
    
    if img is None:
        print(f"❌ Impossible de lire: {legend_path}")
        return []
    
    h, w = img.shape[:2]
    print(f"📐 Image: {w}x{h}")
    
    # 12 icônes dans l'image
    num_icons = len(icons_info)
    cell_width = w // num_icons
    
    # Zone des icônes (partie supérieure, avant le texte)
    # Ajuster selon l'image - environ 60% de la hauteur pour l'icône
    icon_top = 5
    icon_bottom = int(h * 0.6)
    
    os.makedirs(output_dir, exist_ok=True)
    extracted = []
    
    for idx, description in icons_info:
        x_start = idx * cell_width + 2  # petit padding
        x_end = (idx + 1) * cell_width - 2
        
        # Extraire la zone de l'icône
        icon_crop = img[icon_top:icon_bottom, x_start:x_end]
        
        # Nom du fichier
        safe_desc = description.replace(" ", "_")[:25]
        filename = f"icon_{idx:02d}_{safe_desc}.png"
        filepath = output_dir / filename
        
        cv2.imwrite(str(filepath), icon_crop)
        print(f"   ✅ {filename}")
        
        extracted.append({
            "description": description,
            "filepath": str(filepath),
            "template": icon_crop
        })
    
    return extracted


def load_icon_templates(icons_dir: Path) -> list:
    """Charge tous les templates d'icônes depuis le dossier."""
    templates = []
    
    if not icons_dir.exists():
        print(f"❌ Dossier {icons_dir} non trouvé. Exécutez --extract-icons d'abord.")
        return []
    
    for img_path in sorted(icons_dir.glob("icon_*.png")):
        # Parse le nom: icon_00_Pluies_orageuses_isolees.png
        parts = img_path.stem.split("_", 2)
        if len(parts) >= 3:
            description = parts[2].replace("_", " ")
            
            # Charger l'image
            data = np.fromfile(str(img_path), dtype=np.uint8)
            template = cv2.imdecode(data, cv2.IMREAD_COLOR)
            
            if template is not None:
                templates.append({
                    "description": description,
                    "filepath": str(img_path),
                    "template": template
                })
    
    print(f"📂 {len(templates)} templates chargés")
    return templates


def match_icon(crop: np.ndarray, templates: list, threshold: float = 0.3) -> tuple:
    """
    Compare un crop avec tous les templates et retourne le meilleur match.
    """
    if crop is None or crop.size == 0:
        return "", 0
    
    best_match = ""
    best_score = 0
    
    # Convertir en gris
    if len(crop.shape) == 3:
        crop_gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    else:
        crop_gray = crop
    
    for tmpl_info in templates:
        template = tmpl_info["template"]
        
        if template is None:
            continue
        
        # Convertir template en gris
        if len(template.shape) == 3:
            template_gray = cv2.cvtColor(template, cv2.COLOR_BGR2GRAY)
        else:
            template_gray = template
        
        # Tester différentes échelles
        for scale in [0.3, 0.4, 0.5, 0.6, 0.7, 0.8, 0.9, 1.0]:
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
                    best_match = tmpl_info["description"]
            except:
                continue
    
    if best_score >= threshold:
        return best_match, best_score
    
    return "", best_score


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


def find_map_for_json(json_path: Path, maps_dir: Path) -> Path | None:
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


def process_json_file(json_path: Path, maps_dir: Path, cities_rel: list, 
                      templates: list, output_dir: Path = None, threshold: float = 0.3) -> int:
    """Traite un fichier JSON avec template matching."""
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
    
    # Zone de la carte
    try:
        x0, y0, x1, y1 = detect_map_bbox(img)
    except:
        x0, y0, x1, y1 = 0, 0, img.shape[1], img.shape[0]
    
    map_w = x1 - x0
    map_h = y1 - y0
    CROP_SIZE = 40  # Zone pour capturer l'icône près de la ville
    
    # Charger JSON
    with open(json_path, "r", encoding="utf-8") as f:
        json_data = json.load(f)
    
    count = 0
    stations = json_data.get("stations", [])
    
    for i, station in enumerate(stations):
        city_name = station["nom"]
        
        # Coordonnées
        city_info = next((c for c in cities_rel if c["name"] == city_name), None)
        if city_info is None:
            continue
        
        # Crop - légèrement au-dessus et à gauche de la ville (où se trouve l'icône)
        xr, yr = city_info["x_rel"], city_info["y_rel"]
        cx = int(x0 + xr * map_w) - 20  # décalage à gauche
        cy = int(y0 + yr * map_h) - 15  # décalage vers le haut
        h_img, w_img = img.shape[:2]
        
        x1c = max(0, cx - CROP_SIZE)
        y1c = max(0, cy - CROP_SIZE)
        x2c = min(w_img, cx + CROP_SIZE)
        y2c = min(h_img, cy + CROP_SIZE)
        crop = img[y1c:y2c, x1c:x2c]
        
        if crop.size == 0:
            continue
        
        # Template matching
        description, score = match_icon(crop, templates, threshold)
        
        if description:
            stations[i]["weather_icon"] = description
            stations[i]["match_score"] = round(score, 3)
            count += 1
            print(f"   ✓ {city_name:<15} -> {description} ({score:.2f})")
        else:
            print(f"   ✗ {city_name:<15} -> Pas de match (score: {score:.2f})")
    
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
    
    with file_lock:
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(json_data, f, ensure_ascii=False, indent=2)
    
    print(f"   💾 {count} icônes -> {out_path.name}")
    return count


def main():
    parser = argparse.ArgumentParser(description="Extraction d'icônes par Template Matching")
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--maps-dir", type=Path, default=DEFAULT_MAPS_DIR)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--icons-dir", type=Path, default=ICONS_DIR)
    parser.add_argument("--extract-icons", action="store_true", help="Extraire les icônes de la légende")
    parser.add_argument("--threshold", type=float, default=0.3, help="Seuil de correspondance (0-1)")
    parser.add_argument("--limit", type=int, default=0, help="Limiter le nombre de fichiers")
    args = parser.parse_args()
    
    print("=" * 60)
    print("🎯 EXTRACTION D'ICÔNES - TEMPLATE MATCHING v2")
    print("=" * 60)
    
    # Mode extraction des icônes
    if args.extract_icons:
        print(f"\n📤 EXTRACTION DES ICÔNES DEPUIS {LEGEND_ICONS}")
        print("-" * 60)
        
        icons = extract_icons_from_legend(LEGEND_ICONS, ICONS_DEFINITIONS, args.icons_dir)
        
        print(f"\n✅ {len(icons)} icônes extraites dans {args.icons_dir}/")
        print("\nMaintenant lancez sans --extract-icons pour traiter les fichiers.")
        return
    
    # Charger les templates
    templates = load_icon_templates(args.icons_dir)
    if not templates:
        print("\n⚠️ Aucun template trouvé!")
        print("Exécutez d'abord: python fix_icons_template.py --extract-icons")
        return
    
    # Charger les villes
    with open(CITIES_REL_FILE, "r", encoding="utf-8") as f:
        all_cities = json.load(f)
    cities_rel = [c for c in all_cities if c["name"] in TARGET_CITIES]
    print(f"📍 {len(cities_rel)} villes")
    
    if args.output_dir:
        os.makedirs(args.output_dir, exist_ok=True)
        print(f"📂 Sortie: {args.output_dir}")
    
    # Fichiers JSON
    json_files = sorted(args.input_dir.rglob("*.json"))
    json_files = [f for f in json_files if ".cache" not in str(f)]
    
    if args.limit > 0:
        json_files = json_files[:args.limit]
        print(f"⚠️ Limité à {args.limit} fichiers")
    
    print(f"🗂️ {len(json_files)} fichiers à traiter")
    print(f"📊 Seuil: {args.threshold}")
    
    if not json_files:
        print("✅ Rien à traiter!")
        return
    
    # Traitement
    start = datetime.now()
    total = 0
    
    for jf in json_files:
        total += process_json_file(jf, args.maps_dir, cities_rel, templates, args.output_dir, args.threshold)
    
    elapsed = (datetime.now() - start).total_seconds()
    print(f"\n{'='*60}")
    print(f"✅ {total} icônes | ⏱️ {elapsed:.1f}s")
    if args.output_dir:
        print(f"📂 Résultats: {args.output_dir}")
    print("=" * 60)


if __name__ == "__main__":
    main()
