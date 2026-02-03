"""
fix_icons_only.py - Script OPTIMISÉ pour extraire les icônes météo

Utilise les images de légende comme référence UNIQUE pour identifier les icônes.
Le modèle se concentre UNIQUEMENT sur la reconnaissance d'icônes.

Légende sans poussière (codes standards):
- TSRA = Orages avec pluies Isoles | Orages avec pluies
- RA = Pluies
- TS = Orages | Orages Isoles
- NSW = Temps partiellement nuageux | Temps nuageux | Temps ensoleille

Légende avec poussière (préfixe DU):
- DUTSRA = Orages avec pluies Isoles avec poussiere
- DURA = Pluies avec poussiere
- DUTS = Orages isoles avec poussiere | Orages avec poussiere
- DU = Temps partiellement nuageux avec poussiere | Temps nuageux avec poussiere | Temps ensoleille avec poussiere | poussiere

Usage:
    python fix_icons_only.py --input-dir 2023_temps_specific --maps-dir 2023_maps
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
DEFAULT_INPUT_DIR = Path("2024_temps_specific")
DEFAULT_MAPS_DIR = Path("2024_maps")
LEGEND_ICONS_1 = "legend-icons-1.png"
LEGEND_ICONS_2 = "legend-icons-2.png"

OLLAMA_URL = "http://localhost:11434/api/generate"
DEFAULT_MODEL = "qwen3-vl:8b"
TIMEOUT_SECONDS = 120  # Réduit car prompt plus simple

file_lock = threading.Lock()

# ---------- VILLES CIBLÉES ----------
TARGET_CITIES = [
    "DORI", "OUAHIGOUYA", "OUAGADOUGOU", "BOGANDE", "DEDOUGOU",
    "FADA NGOURMA", "BOBO DIOULASSO", "BOROMO", "PO", "GAOUA"
]

# ---------- MAPPING CODE -> DESCRIPTION ----------
# Basé sur les images de légende fournies
ICON_MAPPING = {
    # Sans poussière
    "TSRA": "Orages avec pluies",
    "RA": "Pluies", 
    "TS": "Orages",
    "NSW_sunny": "Temps ensoleille",
    "NSW_cloudy": "Temps nuageux",
    "NSW_partly": "Temps partiellement nuageux",
    # Avec poussière
    "DUTSRA": "Orages avec pluies avec poussiere",
    "DURA": "Pluies avec poussiere",
    "DUTS": "Orages avec poussiere",
    "DU_sunny": "Temps ensoleille avec poussiere",
    "DU_cloudy": "Temps nuageux avec poussiere",
    "DU_partly": "Temps partiellement nuageux avec poussiere",
    "DU": "poussiere",
}


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


def load_image_as_base64(path: str) -> str:
    """Charge une image en base64."""
    if not Path(path).exists():
        return ""
    try:
        data = np.fromfile(path, dtype=np.uint8)
        img = cv2.imdecode(data, cv2.IMREAD_COLOR)
        ok, buf = cv2.imencode(".png", img)
        if ok:
            return base64.b64encode(buf.tobytes()).decode("ascii")
    except Exception:
        pass
    return ""


def call_qwen_icon_only(crop_bgr, city_name, legend1_b64: str, legend2_b64: str, model: str) -> str:
    """
    Appel Qwen FOCALISÉ sur l'identification d'icône.
    Prompt simplifié et direct.
    """
    ok, buf = cv2.imencode(".png", crop_bgr)
    if not ok:
        return ""
    
    crop_b64 = base64.b64encode(buf.tobytes()).decode("ascii")
    
    # Images: crop + légendes
    images = [crop_b64]
    if legend1_b64:
        images.append(legend1_b64)
    if legend2_b64:
        images.append(legend2_b64)
    
    # Prompt ULTRA simplifié et direct
    prompt = f"""Look at IMAGE 1 showing the weather icon near "{city_name}".
Compare it to the legend icons in IMAGE 2 and IMAGE 3.

What is the weather icon code? Answer with ONLY the code from this list:
TSRA, RA, TS, NSW, DUTSRA, DURA, DUTS, DU

Then describe if it's sunny, cloudy, or partly cloudy.

Format your answer as: CODE - description
Example: NSW - Temps ensoleille
Example: RA - Pluies
Example: TS - Orages
Example: DU - poussiere

Answer:""".strip()

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
        
        # Nettoyer les balises <think>
        if "<think>" in text:
            text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
        
        # Extraire le résultat
        result = parse_icon_response(text)
        print(f"      {city_name:<15} -> {result}")
        return result
        
    except requests.exceptions.Timeout:
        print(f"      [TIMEOUT] {city_name}")
    except Exception as e:
        print(f"      [ERROR] {city_name}: {str(e)[:50]}")
    
    return ""


def parse_icon_response(text: str) -> str:
    """Parse la réponse du modèle pour extraire l'icône."""
    text_upper = text.upper()
    text_lower = text.lower()
    
    # Détection du code principal
    code = ""
    if "DUTSRA" in text_upper:
        code = "DUTSRA"
    elif "DURA" in text_upper:
        code = "DURA"
    elif "DUTS" in text_upper:
        code = "DUTS"
    elif "TSRA" in text_upper:
        code = "TSRA"
    elif "NSW" in text_upper:
        code = "NSW"
    elif "RA" in text_upper and "DU" not in text_upper:
        code = "RA"
    elif "TS" in text_upper and "DU" not in text_upper:
        code = "TS"
    elif "DU" in text_upper:
        code = "DU"
    
    # Déterminer le sous-type selon la description
    if "ensoleill" in text_lower or "sunny" in text_lower or "soleil" in text_lower:
        if code == "NSW":
            return "Temps ensoleille"
        elif code == "DU":
            return "Temps ensoleille avec poussiere"
    
    if "partiellement" in text_lower or "partly" in text_lower:
        if code == "NSW":
            return "Temps partiellement nuageux"
        elif code == "DU":
            return "Temps partiellement nuageux avec poussiere"
    
    if "nuageux" in text_lower or "cloudy" in text_lower or "nuage" in text_lower:
        if code == "NSW":
            return "Temps nuageux"
        elif code == "DU":
            return "Temps nuageux avec poussiere"
    
    # Mapping direct des codes
    mapping = {
        "TSRA": "Orages avec pluies",
        "RA": "Pluies",
        "TS": "Orages",
        "DUTSRA": "Orages avec pluies avec poussiere",
        "DURA": "Pluies avec poussiere",
        "DUTS": "Orages avec poussiere",
        "DU": "poussiere",
        "NSW": "Temps partiellement nuageux",  # Default NSW
    }
    
    if code in mapping:
        return mapping[code]
    
    # Si rien trouvé, retourner le texte nettoyé
    return text.split('\n')[0].strip()[:50] if text else ""


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
                      legend1_b64: str, legend2_b64: str, model: str,
                      output_dir: Path = None) -> int:
    """Traite un fichier JSON - extrait TOUTES les icônes."""
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
    CROP_SIZE = 60  # Taille réduite pour plus de précision
    
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
        
        # Crop
        xr, yr = city_info["x_rel"], city_info["y_rel"]
        cx = int(x0 + xr * map_w)
        cy = int(y0 + yr * map_h)
        h_img, w_img = img.shape[:2]
        
        x1c = max(0, cx - CROP_SIZE)
        y1c = max(0, cy - CROP_SIZE)
        x2c = min(w_img, cx + CROP_SIZE)
        y2c = min(h_img, cy + CROP_SIZE)
        crop = img[y1c:y2c, x1c:x2c]
        
        if crop.size == 0:
            continue
        
        # Appel modèle
        icon = call_qwen_icon_only(crop, city_name, legend1_b64, legend2_b64, model)
        
        if icon:
            stations[i]["weather_icon"] = icon
            count += 1
    
    # Sauvegarder
    json_data["stations"] = stations
    json_data["_icons_fixed"] = datetime.now().isoformat()
    
    # Déterminer le chemin de sortie
    if output_dir:
        # Créer sous-dossier avec même structure
        rel_subdir = json_path.parent.name
        out_subdir = output_dir / rel_subdir
        os.makedirs(out_subdir, exist_ok=True)
        out_path = out_subdir / json_path.name
    else:
        out_path = json_path
    
    with file_lock:
        with open(out_path, "w", encoding="utf-8") as f:
            json.dump(json_data, f, ensure_ascii=False, indent=2)
    
    print(f"   ✅ {count} icônes -> {out_path.name}")
    return count


def main():
    parser = argparse.ArgumentParser(description="Extraction d'icônes météo optimisée")
    parser.add_argument("--model", default=DEFAULT_MODEL)
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR)
    parser.add_argument("--maps-dir", type=Path, default=DEFAULT_MAPS_DIR)
    parser.add_argument("--output-dir", type=Path, default=None, help="Dossier de sortie (copie les fichiers)")
    parser.add_argument("--skip-done", action="store_true", help="Ignorer fichiers déjà traités")
    parser.add_argument("--limit", type=int, default=0, help="Limiter le nombre de fichiers à traiter (0=tous)")
    args = parser.parse_args()
    
    # Créer le dossier de sortie si spécifié
    if args.output_dir:
        os.makedirs(args.output_dir, exist_ok=True)
        print(f"📂 Sortie: {args.output_dir}")
    
    print("=" * 60)
    print("🎯 EXTRACTION D'ICÔNES MÉTÉO - VERSION OPTIMISÉE")
    print("=" * 60)
    print(f"📁 JSON: {args.input_dir} | Cartes: {args.maps_dir}")
    print(f"🤖 {args.model} | Timeout: {TIMEOUT_SECONDS}s")
    print("=" * 60)
    
    # Légendes
    legend1_b64 = load_image_as_base64(LEGEND_ICONS_1)
    legend2_b64 = load_image_as_base64(LEGEND_ICONS_2)
    print(f"{'✅' if legend1_b64 else '❌'} {LEGEND_ICONS_1}")
    print(f"{'✅' if legend2_b64 else '❌'} {LEGEND_ICONS_2}")
    
    # Villes
    with open(CITIES_REL_FILE, "r", encoding="utf-8") as f:
        all_cities = json.load(f)
    cities_rel = [c for c in all_cities if c["name"] in TARGET_CITIES]
    print(f"📍 {len(cities_rel)} villes")
    
    # Fichiers JSON
    json_files = sorted(args.input_dir.rglob("*.json"))
    json_files = [f for f in json_files if ".cache" not in str(f)]
    
    if args.skip_done:
        filtered = []
        for jf in json_files:
            with open(jf, "r", encoding="utf-8") as f:
                d = json.load(f)
            if "_icons_fixed" not in d:
                filtered.append(jf)
        json_files = filtered
    
    print(f"🗂️ {len(json_files)} fichiers")
    
    if not json_files:
        print("✅ Terminé!")
        return
    
    # Limiter si demandé
    if args.limit > 0:
        json_files = json_files[:args.limit]
        print(f"⚠️ Limité à {args.limit} fichiers pour test")
    
    # Traitement
    start = datetime.now()
    total = 0
    
    for jf in json_files:
        total += process_json_file(jf, args.maps_dir, cities_rel, legend1_b64, legend2_b64, args.model, args.output_dir)
    
    elapsed = (datetime.now() - start).total_seconds()
    print(f"\n{'='*60}")
    print(f"✅ {total} icônes | ⏱️ {elapsed:.0f}s")
    if args.output_dir:
        print(f"📂 Résultats dans: {args.output_dir}")
    print("=" * 60)


if __name__ == "__main__":
    main()
