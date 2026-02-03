"""
extract_specific_cities.py - Extraction pour 10 villes spécifiques uniquement

Villes ciblées:
    Dori, Ouahigouya, Ouagadougou, Bogandé, Dédougou, 
    Fada N'Gourma, Bobo Dioulasso, Boromo, Po, Gaoua

Usage:
    python extract_specific_cities.py
    python extract_specific_cities.py --workers 1 --city-workers 5 --model qwen3-vl:8b
"""

import cv2
import json
import os
import re
import base64
import requests
import numpy as np
from pathlib import Path
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime
import argparse
import threading

# ---------- CONFIG PAR DÉFAUT ----------
CITIES_REL_FILE = "cities_rel.json"
MAPS_ROOT = Path("2024_maps")
OUTPUT_ROOT = Path("2024_temps_specific")
CACHE_DIR = Path("2024_temps_specific/.cache")

OLLAMA_URL = "http://localhost:11434/api/generate"
DEFAULT_MODEL = "qwen3-vl:8b"

# Lock pour écriture thread-safe
file_lock = threading.Lock()

# ---------- VILLES CIBLÉES (10 villes) ----------
TARGET_CITIES = [
    "DORI",
    "OUAHIGOUYA",
    "OUAGADOUGOU",
    "BOGANDE",
    "DEDOUGOU",
    "FADA NGOURMA",
    "BOBO DIOULASSO",
    "BOROMO",
    "PO",
    "GAOUA"
]

# ---------- ICÔNES MÉTÉO CANONIQUES ----------
CANONICAL_ICONS = [
    "ensoleille",
    "partiellement_nuageux", 
    "nuageux",
    "pluie",
    "orage",
    "brume_brouillard",
    "vent_sable"
]


def ensure_dirs():
    """Crée les dossiers nécessaires."""
    os.makedirs(OUTPUT_ROOT, exist_ok=True)
    os.makedirs(CACHE_DIR, exist_ok=True)


def detect_map_bbox(img):
    """Détecte automatiquement les limites de la carte dans l'image."""
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
        return 0, 0, w, h  # Fallback: utiliser l'image entière
    
    x, y, cw, ch = best
    return x, y, x + cw, y + ch


def get_cache_path(map_path: Path) -> Path:
    """Retourne le chemin du fichier cache pour une carte."""
    cache_name = f"{map_path.stem}_cache.json"
    return CACHE_DIR / map_path.parent.name / cache_name


def load_cache(cache_path: Path) -> dict:
    """Charge le cache existant pour une carte."""
    if cache_path.exists():
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            pass
    return {}


def save_cache(cache_path: Path, data: dict):
    """Sauvegarde le cache de manière thread-safe."""
    with file_lock:
        os.makedirs(cache_path.parent, exist_ok=True)
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(data, f, ensure_ascii=False, indent=2)


def infer_date_from_filename(path: Path) -> str:
    """Extrait la date du nom de fichier."""
    m = re.search(r"(20\d{2})[^\d]([01]\d)[^\d]([0-3]\d)", path.name)
    if m:
        y, mo, d = m.groups()
        return f"{y}-{mo}-{d}"
    return path.stem


def clean_temperature(v):
    """Nettoie et valide une valeur de température."""
    if v is None:
        return None
    try:
        v = int(v)
    except (ValueError, TypeError):
        return None
    if -5 <= v <= 60:
        return v
    return None


def normalize_icon(raw_icon: str) -> str:
    """Normalise une icône météo vers les catégories canoniques."""
    if not raw_icon:
        return ""
    
    text = raw_icon.lower().strip()
    
    # Mapping des variations
    if any(x in text for x in ["soleil", "ensoleill", "clair", "degag"]):
        return "ensoleille"
    if any(x in text for x in ["partiel", "eclair"]):
        return "partiellement_nuageux"
    if any(x in text for x in ["nuag", "couvert"]):
        return "nuageux"
    if any(x in text for x in ["orag"]):
        return "orage"
    if any(x in text for x in ["plui", "pluie", "averse"]):
        return "pluie"
    if any(x in text for x in ["brum", "brouillard"]):
        return "brume_brouillard"
    if any(x in text for x in ["vent", "sable", "poussi"]):
        return "vent_sable"
    
    return raw_icon  # Retourne tel quel si non reconnu


def call_qwen_for_crop(crop_bgr, city_name, model: str) -> dict:
    """
    Appel Ollama pour un PETIT crop autour d'une ville.
    Plus rapide et précis pour les petits modèles.
    """
    ok, buf = cv2.imencode(".png", crop_bgr)
    if not ok:
        return {"tmin": None, "tmax": None, "icon": ""}
    
    img_b64 = base64.b64encode(buf.tobytes()).decode("ascii")
    
    prompt = f"""
You are a precise OCR assistant for weather maps of Burkina Faso.
This image is a small crop around the city "{city_name}" on a weather map.
Near the city name, there is a temperature range written like "25/39" (min/max in °C).

Your task:
- Read the temperature range for this city ONLY.
- If you see exactly "A/B", then tmin = A and tmax = B.
- If you see only one number (e.g. "37"), then tmin = tmax = 37.
- Temperatures are integers in °C and must be between -5 and 60.
- Also identify the weather condition icon (ensoleille, nuageux, pluie, orage, partiellement_nuageux, brume_brouillard, vent_sable).

Answer with valid JSON only, no extra text, in this format:
{{
  "tmin": 25,
  "tmax": 39,
  "icon": "ensoleille"
}}

If unreadable, use null for numeric values and "" for icon.
""".strip()

    payload = {
        "model": model,
        "prompt": prompt,
        "images": [img_b64],
        "stream": False,
    }
    
    try:
        print(f"      [TRACE] Envoi requête Ollama pour {city_name}...")
        resp = requests.post(OLLAMA_URL, json=payload, timeout=120)
        resp.raise_for_status()
        data = resp.json()
        text = data.get("response", "").strip()
        print(f"      [DEBUG] Raw Response for {city_name}: {text[:100]}")
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            return json.loads(match.group(0))
    except Exception as e:
        print(f"      [DEBUG] Error for {city_name}: {e}")
        pass
    return {"tmin": None, "tmax": None, "icon": ""}


def process_single_map(map_path: Path, cities_rel: list, model: str, use_cache: bool = True, city_workers: int = 1) -> dict:
    """
    Traite UNE carte complète avec CROPS.
    Optimisation : On peut paralléliser les villes à l'intérieur de la carte.
    """
    date_bulletin = infer_date_from_filename(map_path)
    if "_map1" in map_path.stem:
        map_type = "observed"
    elif "_map2" in map_path.stem:
        map_type = "forecast"
    else:
        map_type = "map"
    
    cache_path = get_cache_path(map_path)
    cached_data = load_cache(cache_path) if use_cache else {}
    if cached_data.get("_complete"):
        print(f"  ✅ CACHE HIT: {map_path.name}")
        return cached_data
    
    print(f"\n📍 Traitement: {map_path.name}")
    try:
        data = np.fromfile(str(map_path), dtype=np.uint8)
        img = cv2.imdecode(data, cv2.IMREAD_COLOR)
    except Exception as e:
        print(f"  ⚠️ Erreur lecture fichier: {e}")
        return {}

    if img is None:
        return {}

    try:
        x0, y0, x1, y1 = detect_map_bbox(img)
    except Exception:
        x0, y0, x1, y1 = 0, 0, img.shape[1], img.shape[0]

    map_w = x1 - x0
    map_h = y1 - y0
    CROP_SIZE = 80

    # Fonction interne pour traiter une seule ville (pour le pool)
    def task_city(city):
        name = city["name"]
        xr = city["x_rel"]
        yr = city["y_rel"]
        cx = int(x0 + xr * map_w)
        cy = int(y0 + yr * map_h)
        h_img, w_img = img.shape[:2]
        x1c = max(0, cx - CROP_SIZE)
        y1c = max(0, cy - CROP_SIZE)
        x2c = min(w_img, cx + CROP_SIZE)
        y2c = min(h_img, cy + CROP_SIZE)
        crop = img[y1c:y2c, x1c:x2c]

        if crop.size == 0:
            return {"nom": name, "tmin": None, "tmax": None, "weather_icon": ""}
        
        res = call_qwen_for_crop(crop, name, model)
        tmin = clean_temperature(res.get("tmin"))
        tmax = clean_temperature(res.get("tmax"))
        icon = normalize_icon(res.get("icon", ""))
        
        status = "✓" if tmin is not None else "✗"
        print(f"      {status} {name:<15} Tmin={tmin}, Tmax={tmax}, Icon={icon}")
        return {"nom": name, "tmin": tmin, "tmax": tmax, "weather_icon": icon}

    stations = []
    if city_workers > 1:
        print(f"    🚀 Extraction parallèle des villes ({city_workers} threads)...")
        with ThreadPoolExecutor(max_workers=city_workers) as executor:
            futures = [executor.submit(task_city, city) for city in cities_rel]
            for future in as_completed(futures):
                stations.append(future.result())
    else:
        for city in cities_rel:
            stations.append(task_city(city))
    
    result = {
        "date_bulletin": date_bulletin,
        "map_type": map_type,
        "source_image": map_path.name,
        "stations": stations,
        "_complete": True,
        "_processed_at": datetime.now().isoformat()
    }
    save_cache(cache_path, result)
    return result


def process_map_worker(args):
    """Worker pour le traitement parallèle."""
    map_path, cities_rel, model, use_cache, city_workers = args
    try:
        return map_path, process_single_map(map_path, cities_rel, model, use_cache, city_workers)
    except Exception as e:
        print(f"  ❌ Erreur sur {map_path.name}: {e}")
        return map_path, {}


def main():
    global MAPS_ROOT, OUTPUT_ROOT
    parser = argparse.ArgumentParser(description="Extraction pour 10 villes spécifiques")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Modèle Ollama à utiliser")
    parser.add_argument("--workers", type=int, default=1, help="Nombre de CARTES traitées en parallèle")
    parser.add_argument("--city-workers", type=int, default=2, help="Nombre de VILLES traitées en parallèle")
    parser.add_argument("--no-cache", action="store_true", help="Désactiver le cache")
    parser.add_argument("--maps-dir", type=Path, default=MAPS_ROOT, help="Dossier des cartes")
    parser.add_argument("--output-dir", type=Path, default=OUTPUT_ROOT, help="Dossier de sortie")
    args = parser.parse_args()
    
    MAPS_ROOT = args.maps_dir
    OUTPUT_ROOT = args.output_dir
    
    ensure_dirs()
    
    print("=" * 70)
    print("🌤️  EXTRACTEUR MÉTÉO - 10 VILLES SPÉCIFIQUES")
    print("=" * 70)
    print(f"📁 Cartes    : {MAPS_ROOT}")
    print(f"📁 Sortie    : {OUTPUT_ROOT}")
    print(f"🤖 Modèle    : {args.model}")
    print(f"👷 Workers   : {args.workers} (cartes) / {args.city_workers} (villes)")
    print(f"💾 Cache     : {'Désactivé' if args.no_cache else 'Activé'}")
    print("=" * 70)
    
    # Charger les villes
    with open(CITIES_REL_FILE, "r", encoding="utf-8") as f:
        all_cities = json.load(f)
    
    # ========== FILTRAGE DES 10 VILLES CIBLÉES ==========
    cities_rel = [c for c in all_cities if c["name"] in TARGET_CITIES]
    
    print(f"\n🎯 VILLES CIBLÉES: {', '.join(TARGET_CITIES)}")
    print(f"📍 {len(cities_rel)} villes trouvées sur {len(TARGET_CITIES)} demandées")
    
    if len(cities_rel) != len(TARGET_CITIES):
        missing = set(TARGET_CITIES) - {c["name"] for c in cities_rel}
        if missing:
            print(f"⚠️  Villes manquantes dans cities_rel.json: {missing}")
    
    # Lister les cartes
    map_files = sorted(
        list(MAPS_ROOT.rglob("*.png")) + 
        list(MAPS_ROOT.rglob("*.jpg")) + 
        list(MAPS_ROOT.rglob("*.jpeg"))
    )
    
    if not map_files:
        print(f"❌ Aucune carte trouvée dans {MAPS_ROOT}")
        return
    
    print(f"🗺️ {len(map_files)} cartes à traiter")
    
    # Filtrer les cartes déjà traitées (fichier JSON final existe)
    to_process = []
    for map_path in map_files:
        date_bulletin = infer_date_from_filename(map_path)
        if "_map1" in map_path.stem:
            map_type = "observed"
        elif "_map2" in map_path.stem:
            map_type = "forecast"
        else:
            map_type = "map"
        
        rel_dir = map_path.parent.relative_to(MAPS_ROOT)
        out_dir = OUTPUT_ROOT / rel_dir
        out_file = out_dir / f"{date_bulletin}_{map_type}.json"
        
        if out_file.exists():
            print(f"  ⏭️ SKIP (existe): {out_file.name}")
        else:
            to_process.append((map_path, out_dir, out_file))
    
    print(f"\n📊 {len(to_process)} cartes à traiter (après filtrage)")
    
    if not to_process:
        print("✅ Tout est déjà traité !")
        return
    
    # Traitement (parallèle ou séquentiel selon workers)
    start_time = datetime.now()
    processed = 0
    errors = 0
    
    if args.workers > 1:
        # Mode parallèle (cartes)
        print(f"\n🚀 Traitement PARALLÈLE CARTES ({args.workers} workers)...")
        work_items = [(mp, cities_rel, args.model, not args.no_cache, args.city_workers) for mp, _, _ in to_process]
        
        with ThreadPoolExecutor(max_workers=args.workers) as executor:
            futures = {executor.submit(process_map_worker, item): item for item in work_items}
            
            for future in as_completed(futures):
                map_path, result = future.result()
                
                if result and result.get("_complete"):
                    # Trouver le fichier de sortie correspondant
                    for mp, out_dir, out_file in to_process:
                        if mp == map_path:
                            os.makedirs(out_dir, exist_ok=True)
                            # Supprimer les métadonnées internes
                            output = {k: v for k, v in result.items() if not k.startswith("_")}
                            with open(out_file, "w", encoding="utf-8") as f:
                                json.dump(output, f, ensure_ascii=False, indent=2)
                            print(f"  💾 Sauvegardé: {out_file.name}")
                            processed += 1
                            break
                else:
                    errors += 1
    else:
        # Mode séquentiel (cartes) mais peut-être parallèle (villes)
        print("\n🔄 Traitement CARTES séquentiel...")
        for map_path, out_dir, out_file in to_process:
            result = process_single_map(map_path, cities_rel, args.model, not args.no_cache, args.city_workers)
            
            if result and result.get("_complete"):
                os.makedirs(out_dir, exist_ok=True)
                output = {k: v for k, v in result.items() if not k.startswith("_")}
                with open(out_file, "w", encoding="utf-8") as f:
                    json.dump(output, f, ensure_ascii=False, indent=2)
                print(f"  💾 Sauvegardé: {out_file.name}")
                processed += 1
            else:
                errors += 1
    
    # Résumé
    elapsed = (datetime.now() - start_time).total_seconds()
    print("\n" + "=" * 70)
    print("📊 RÉSUMÉ")
    print("=" * 70)
    print(f"✅ Traités avec succès : {processed}")
    print(f"❌ Erreurs             : {errors}")
    print(f"⏱️  Durée totale        : {elapsed:.1f}s ({elapsed/60:.1f} min)")
    if processed > 0:
        print(f"⚡ Moyenne par carte   : {elapsed/processed:.1f}s")
    print("=" * 70)


if __name__ == "__main__":
    main()
