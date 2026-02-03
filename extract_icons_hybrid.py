"""
extract_icons_hybrid.py - Extraction hybride (Template + Qwen)

Stratégie:
1. Template matching avec icon_templates/ (rapide)
2. Si score < seuil : fallback sur Qwen avec la légende de la carte
3. Détection des combinaisons avec poussière

Usage:
    python extract_icons_hybrid.py --input-dir 2023_temps_specific --maps-dir 2023_maps --limit 5
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

# ---------- CONFIG ----------
CITIES_REL_FILE = "cities_rel.json"
ICON_ZONES_FILE = "icon_zones.json"
LEGEND_CONFIG_FILE = "legend_config.json"
ICON_TEMPLATES_DIR = Path("icon_templates")

DEFAULT_INPUT_DIR = Path("2024_temps_specific")
DEFAULT_MAPS_DIR = Path("2024_maps")

OLLAMA_URL = "http://localhost:11434/api/generate"
DEFAULT_MODEL = "qwen3-vl:8b"
TIMEOUT_SECONDS = 90

# Seuils
TEMPLATE_THRESHOLD = 0.45  # Au-dessus = accepté direct
QWEN_THRESHOLD = 0.35      # En-dessous = fallback Qwen

# Villes cibles
TARGET_CITIES = [
    "DORI", "OUAHIGOUYA", "OUAGADOUGOU", "BOGANDE", "DEDOUGOU",
    "FADA NGOURMA", "BOBO DIOULASSO", "BOROMO", "PO", "GAOUA"
]

# Mapping des templates
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

# Codes des icônes météo (codes officiels)
ICON_CODES = {
    # Icônes de base
    "Temps ensoleillé": "NSW",
    "Ciel dégagé": "NSW",
    "Temps partiellement nuageux": "NSW",
    "Temps nuageux": "NSW",
    "Ciel nuageux": "NSW",
    "Ciel couvert": "NSW",
    "Orages": "TS",
    "Orage": "TS",
    "Orages isolés": "TS",
    "Pluie": "RA",
    "Pluies": "RA",
    "Pluies faibles": "RA",
    "Orages avec pluies": "TSRA",
    "Orage avec pluie": "TSRA",
    "Pluie orageuse": "TSRA",
    "Orages avec pluies isolés": "TSRA",
    "Pluies orageuses isolées": "TSRA",
    "Poussière en suspension": "DU",
    "Poussière": "DU",
    
    # Combinaisons avec poussière (DU prefix)
    "Temps ensoleillé avec poussière": "DU",
    "Ciel dégagé avec poussière": "DU",
    "Temps partiellement nuageux avec poussière": "DU",
    "Temps nuageux avec poussière": "DU",
    "Ciel nuageux avec poussière": "DU",
    "Ciel couvert avec poussière": "DU",
    "Orages avec poussière": "DUTS",
    "Orage avec poussière": "DUTS",
    "Orages isolés avec poussière": "DUTS",
    "Pluies avec poussière": "DURA",
    "Pluie avec poussière": "DURA",
    "Pluies faibles avec poussière": "DURA",
    "Orages avec pluies avec poussière": "DUTSRA",
    "Pluie orageuse avec poussière": "DUTSRA",
    "Pluies orageuses isolées avec poussière": "DUTSRA",
    "Orages avec pluies isolés avec poussière": "DUTSRA",
}


def get_icon_code(icon_name):
    """Retourne le code d'une icône."""
    if icon_name in ICON_CODES:
        return ICON_CODES[icon_name]
    
    # Essayer sans accents
    for name, code in ICON_CODES.items():
        if name.lower() == icon_name.lower():
            return code
    
    return "00"  # Code inconnu


def load_templates():
    """Charge tous les templates d'icônes."""
    templates = []
    
    if not ICON_TEMPLATES_DIR.exists():
        return templates
    
    for png_file in sorted(ICON_TEMPLATES_DIR.glob("*.png")):
        data = np.fromfile(str(png_file), dtype=np.uint8)
        img = cv2.imdecode(data, cv2.IMREAD_COLOR)
        
        if img is not None:
            name = TEMPLATE_NAMES.get(png_file.name, png_file.stem.replace("_", " "))
            templates.append({
                "name": name,
                "image": img,
                "gray": cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
            })
    
    return templates


def load_icon_zones():
    if Path(ICON_ZONES_FILE).exists():
        with open(ICON_ZONES_FILE, "r", encoding="utf-8") as f:
            return json.load(f).get("cities", {})
    return {}


def load_cities_rel():
    if Path(CITIES_REL_FILE).exists():
        with open(CITIES_REL_FILE, "r", encoding="utf-8") as f:
            all_cities = json.load(f)
        return {c["name"]: c for c in all_cities if c["name"] in TARGET_CITIES}
    return {}


def load_legend_config():
    if Path(LEGEND_CONFIG_FILE).exists():
        with open(LEGEND_CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def image_to_base64(img):
    ok, buf = cv2.imencode(".png", img)
    if ok:
        return base64.b64encode(buf.tobytes()).decode("ascii")
    return ""


def detect_map_bbox(img):
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


def extract_legend_from_map(img, legend_config):
    """Extrait la légende de la carte."""
    h, w = img.shape[:2]
    
    if legend_config:
        rel = legend_config.get("legend_rect_rel", {})
        x1 = int(rel.get("x1_rel", 0.4) * w)
        y1 = int(rel.get("y1_rel", 0.75) * h)
        x2 = int(rel.get("x2_rel", 0.95) * w)
        y2 = int(rel.get("y2_rel", 0.95) * h)
    else:
        # Estimation par défaut
        x1 = int(w * 0.35)
        y1 = int(h * 0.75)
        x2 = w
        y2 = h
    
    legend = img[y1:y2, x1:x2]
    return legend if legend.size > 0 else None


def crop_icon_zone(img, city_name, icon_zones, cities_rel, zone_size=50):
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


def match_template(crop, templates):
    """
    Template matching - détecte l'icône météo ET la poussière si les deux sont présentes.
    Fusion uniquement si les deux icônes sont vraiment détectées au-dessus du seuil.
    """
    if crop is None or crop.size == 0:
        return "", 0.0
    
    crop_gray = cv2.cvtColor(crop, cv2.COLOR_BGR2GRAY)
    crop_h, crop_w = crop_gray.shape
    
    best_weather_name = ""
    best_weather_score = 0.0
    dust_score = 0.0
    
    DUST_THRESHOLD = 0.35  # Seuil pour détecter la poussière
    
    for tmpl in templates:
        template_gray = tmpl["gray"]
        tmpl_h, tmpl_w = template_gray.shape
        tmpl_name = tmpl["name"]
        
        is_dust = "poussière" in tmpl_name.lower() or "poussiere" in tmpl_name.lower()
        
        for scale in [0.15, 0.2, 0.25, 0.3, 0.35, 0.4, 0.5]:
            new_w = int(tmpl_w * scale)
            new_h = int(tmpl_h * scale)
            
            if new_w <= 0 or new_h <= 0 or new_w > crop_w or new_h > crop_h:
                continue
            
            resized = cv2.resize(template_gray, (new_w, new_h))
            
            try:
                result = cv2.matchTemplate(crop_gray, resized, cv2.TM_CCOEFF_NORMED)
                _, max_val, _, _ = cv2.minMaxLoc(result)
                
                if is_dust:
                    # Mettre à jour le score poussière
                    if max_val > dust_score:
                        dust_score = max_val
                else:
                    # Mettre à jour le meilleur score météo
                    if max_val > best_weather_score:
                        best_weather_score = max_val
                        best_weather_name = tmpl_name
            except:
                continue
    
    # Fusion si les DEUX icônes sont détectées au-dessus du seuil
    if best_weather_score >= TEMPLATE_THRESHOLD or best_weather_score >= QWEN_THRESHOLD:
        if dust_score >= DUST_THRESHOLD:
            # Les deux icônes sont présentes -> fusion
            return f"{best_weather_name} avec poussière", best_weather_score
        else:
            # Seulement l'icône météo
            return best_weather_name, best_weather_score
    
    # Si seulement la poussière est détectée avec un bon score
    if dust_score >= DUST_THRESHOLD and dust_score > best_weather_score:
        return "Poussière en suspension", dust_score
    
    return best_weather_name, best_weather_score


def identify_with_qwen(crop, legend_img, city_name, model):
    """Fallback: identification avec Qwen + légende."""
    crop_b64 = image_to_base64(crop)
    
    images = [crop_b64]
    legend_text = ""
    
    if legend_img is not None and legend_img.size > 0:
        legend_b64 = image_to_base64(legend_img)
        images.append(legend_b64)
        legend_text = "IMAGE 2 montre la légende de cette carte."
    
    prompt = f"""IMAGE 1: Icône météo pour la ville "{city_name}".
{legend_text}

Identifie le type de temps. Réponds avec UN SEUL nom parmi:
- Ciel dégagé
- Ciel nuageux
- Ciel couvert
- Temps partiellement nuageux
- Pluie
- Pluies faibles
- Orage
- Orages isolés
- Pluies orageuses isolées
- Pluie orageuse
- Poussière en suspension

Si combiné avec poussière, ajoute "avec poussière".
Exemple: Ciel dégagé avec poussière

Réponse:"""

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
        
        if "<think>" in text:
            text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
        
        result = text.split('\n')[0].strip()
        result = re.sub(r'^[-•*]\s*', '', result)
        return result[:60] if result else ""
        
    except:
        pass
    
    return ""


def find_map_for_json(json_path: Path, maps_dir: Path):
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
                      templates, legend_config, model, output_dir=None):
    """Traite un fichier JSON avec l'approche hybride."""
    print(f"\n📄 {json_path.name}")
    
    map_path = find_map_for_json(json_path, maps_dir)
    if map_path is None:
        print(f"   ❌ Image source introuvable")
        return 0
    
    try:
        data = np.fromfile(str(map_path), dtype=np.uint8)
        img = cv2.imdecode(data, cv2.IMREAD_COLOR)
    except Exception as e:
        print(f"   ❌ Erreur: {e}")
        return 0
    
    if img is None:
        return 0
    
    # Extraire la légende (pour fallback)
    legend_img = extract_legend_from_map(img, legend_config)
    
    with open(json_path, "r", encoding="utf-8") as f:
        json_data = json.load(f)
    
    count = 0
    stations = json_data.get("stations", [])
    
    for i, station in enumerate(stations):
        city_name = station["nom"]
        
        if city_name not in TARGET_CITIES:
            continue
        
        crop = crop_icon_zone(img, city_name, icon_zones, cities_rel)
        
        if crop is None:
            print(f"   ✗ {city_name:<15} -> Crop échoué")
            continue
        
        # 1. Essayer template matching d'abord
        icon_name, score = match_template(crop, templates)
        
        if score >= TEMPLATE_THRESHOLD:
            # Score assez élevé, on accepte
            stations[i]["weather_icon"] = icon_name
            stations[i]["icon_code"] = get_icon_code(icon_name)
            stations[i]["match_score"] = round(score, 3)
            stations[i]["method"] = "template"
            count += 1
            code = get_icon_code(icon_name)
            print(f"   ✓ {city_name:<15} -> {icon_name} [{code}] ({score:.2f})")
        
        elif score < QWEN_THRESHOLD:
            # Score trop bas, fallback Qwen
            icon_name = identify_with_qwen(crop, legend_img, city_name, model)
            if icon_name:
                stations[i]["weather_icon"] = icon_name
                stations[i]["icon_code"] = get_icon_code(icon_name)
                stations[i]["method"] = "qwen"
                count += 1
                code = get_icon_code(icon_name)
                print(f"   ✓ {city_name:<15} -> {icon_name} [{code}] (qwen)")
            else:
                print(f"   ✗ {city_name:<15} -> Échec ({score:.2f})")
        
        else:
            # Score moyen, accepter template mais marquer
            if icon_name:
                stations[i]["weather_icon"] = icon_name
                stations[i]["icon_code"] = get_icon_code(icon_name)
                stations[i]["match_score"] = round(score, 3)
                stations[i]["method"] = "template_low"
                count += 1
                code = get_icon_code(icon_name)
                print(f"   ~ {city_name:<15} -> {icon_name} [{code}] ({score:.2f})")
            else:
                print(f"   ✗ {city_name:<15} -> Score: {score:.2f}")
    
    json_data["stations"] = stations
    json_data["_icons_hybrid_extracted"] = datetime.now().isoformat()
    
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
    parser = argparse.ArgumentParser(description="Extraction hybride (Template + Qwen)")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--maps-dir", type=Path, default=DEFAULT_MAPS_DIR)
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--limit", type=int, default=0)
    parser.add_argument("--skip-done", action="store_true")
    args = parser.parse_args()
    
    print("=" * 60)
    print("🎯 EXTRACTION HYBRIDE (TEMPLATE + QWEN)")
    print("=" * 60)
    
    templates = load_templates()
    icon_zones = load_icon_zones()
    cities_rel = load_cities_rel()
    legend_config = load_legend_config()
    
    print(f"📚 {len(templates)} templates")
    print(f"📍 {len(icon_zones)} zones calibrées")
    print(f"📍 {len(cities_rel)} villes")
    print(f"🤖 {args.model}")
    print(f"⚡ Seuil template: {TEMPLATE_THRESHOLD} | Seuil Qwen: {QWEN_THRESHOLD}")
    
    if args.output_dir:
        os.makedirs(args.output_dir, exist_ok=True)
        print(f"📂 Sortie: {args.output_dir}")
    
    json_files = sorted(args.input_dir.rglob("*.json"))
    json_files = [f for f in json_files if ".cache" not in str(f)]
    
    if args.skip_done:
        filtered = []
        for jf in json_files:
            with open(jf, "r", encoding="utf-8") as f:
                d = json.load(f)
            if "_icons_hybrid_extracted" not in d:
                filtered.append(jf)
        json_files = filtered
    
    if args.limit > 0:
        json_files = json_files[:args.limit]
    
    print(f"🗂️ {len(json_files)} fichiers")
    print("=" * 60)
    
    if not json_files:
        print("✅ Rien à traiter!")
        return
    
    start = datetime.now()
    total = 0
    
    for jf in json_files:
        total += process_json_file(
            jf, args.maps_dir, icon_zones, cities_rel,
            templates, legend_config, args.model, args.output_dir
        )
    
    elapsed = (datetime.now() - start).total_seconds()
    print(f"\n{'='*60}")
    print(f"✅ {total} icônes | ⏱️ {elapsed:.1f}s")
    print("=" * 60)


if __name__ == "__main__":
    main()
