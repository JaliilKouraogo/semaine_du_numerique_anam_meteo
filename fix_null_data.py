"""
fix_null_data.py - Script de correction pour les données nulles et timeouts

Ce script:
1. Scanne tous les fichiers JSON de sortie
2. Identifie les stations avec des valeurs null (tmin=null, tmax=null)
3. Relance l'extraction UNIQUEMENT pour ces stations
4. Met à jour le fichier JSON avec les nouvelles valeurs
5. Utilise un timeout de 180s pour éviter les timeouts

Usage:
    python fix_null_data.py
    python fix_null_data.py --input-dir 2023_temps_specific --maps-dir 2023_maps
    python fix_null_data.py --model qwen3-vl:8b --retry-count 3
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

# ---------- CONFIG PAR DÉFAUT ----------
CITIES_REL_FILE = "cities_rel.json"
DEFAULT_INPUT_DIR = Path("2024_temps_specific")
DEFAULT_MAPS_DIR = Path("2024_maps")

OLLAMA_URL = "http://localhost:11434/api/generate"
DEFAULT_MODEL = "qwen3-vl:8b"
TIMEOUT_SECONDS = 180  # Timeout augmenté à 180 secondes

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
        return 0, 0, w, h
    
    x, y, cw, ch = best
    return x, y, x + cw, y + ch


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
    
    return raw_icon


def call_qwen_for_crop(crop_bgr, city_name, model: str, retry_count: int = 1) -> dict:
    """
    Appel Ollama pour un PETIT crop autour d'une ville.
    Utilise un timeout de 180s et permet des retries.
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
    
    for attempt in range(retry_count):
        try:
            print(f"      [TENTATIVE {attempt + 1}/{retry_count}] Envoi requête Ollama pour {city_name} (timeout={TIMEOUT_SECONDS}s)...")
            resp = requests.post(OLLAMA_URL, json=payload, timeout=TIMEOUT_SECONDS)
            resp.raise_for_status()
            data = resp.json()
            text = data.get("response", "").strip()
            print(f"      [DEBUG] Raw Response for {city_name}: {text[:100]}")
            match = re.search(r"\{.*\}", text, re.DOTALL)
            if match:
                result = json.loads(match.group(0))
                # Vérifier si on a des données valides
                if result.get("tmin") is not None or result.get("tmax") is not None:
                    return result
                print(f"      [WARNING] Données nulles retournées, retry...")
        except requests.exceptions.Timeout:
            print(f"      [TIMEOUT] Tentative {attempt + 1} échouée pour {city_name}")
        except Exception as e:
            print(f"      [ERROR] Tentative {attempt + 1} échouée pour {city_name}: {e}")
    
    return {"tmin": None, "tmax": None, "icon": ""}


def find_map_for_json(json_path: Path, maps_dir: Path) -> Path | None:
    """Trouve le fichier image source pour un fichier JSON."""
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    source_image = data.get("source_image", "")
    if not source_image:
        return None
    
    # Chercher l'image dans le dossier des cartes (même structure de sous-dossiers)
    rel_dir = json_path.parent.name
    possible_paths = [
        maps_dir / rel_dir / source_image,
        maps_dir / source_image,
    ]
    
    # Aussi chercher récursivement
    for p in maps_dir.rglob(source_image):
        possible_paths.append(p)
    
    for p in possible_paths:
        if p.exists():
            return p
    
    return None


def get_null_stations(json_path: Path) -> list[dict]:
    """Retourne la liste des stations avec des données nulles dans un fichier JSON."""
    with open(json_path, "r", encoding="utf-8") as f:
        data = json.load(f)
    
    null_stations = []
    stations = data.get("stations", [])
    
    for station in stations:
        tmin = station.get("tmin")
        tmax = station.get("tmax")
        icon = station.get("weather_icon", "")
        
        # Considérer comme "à corriger" si tmin ET tmax sont null
        if tmin is None and tmax is None:
            null_stations.append(station)
    
    return null_stations


def process_single_station(img, city_dict: dict, cities_rel: list, model: str, retry_count: int) -> dict:
    """Retraite une seule station."""
    city_name = city_dict["nom"]
    
    # Trouver les coordonnées relatives pour cette ville
    city_info = None
    for c in cities_rel:
        if c["name"] == city_name:
            city_info = c
            break
    
    if city_info is None:
        print(f"      ⚠️ Ville {city_name} non trouvée dans cities_rel.json")
        return city_dict
    
    try:
        x0, y0, x1, y1 = detect_map_bbox(img)
    except Exception:
        x0, y0, x1, y1 = 0, 0, img.shape[1], img.shape[0]
    
    map_w = x1 - x0
    map_h = y1 - y0
    CROP_SIZE = 80
    
    xr = city_info["x_rel"]
    yr = city_info["y_rel"]
    cx = int(x0 + xr * map_w)
    cy = int(y0 + yr * map_h)
    h_img, w_img = img.shape[:2]
    x1c = max(0, cx - CROP_SIZE)
    y1c = max(0, cy - CROP_SIZE)
    x2c = min(w_img, cx + CROP_SIZE)
    y2c = min(h_img, cy + CROP_SIZE)
    crop = img[y1c:y2c, x1c:x2c]
    
    if crop.size == 0:
        return city_dict
    
    res = call_qwen_for_crop(crop, city_name, model, retry_count)
    tmin = clean_temperature(res.get("tmin"))
    tmax = clean_temperature(res.get("tmax"))
    icon = normalize_icon(res.get("icon", ""))
    
    # Mettre à jour seulement si on a des valeurs valides
    if tmin is not None:
        city_dict["tmin"] = tmin
    if tmax is not None:
        city_dict["tmax"] = tmax
    if icon:
        city_dict["weather_icon"] = icon
    
    status = "✓" if tmin is not None else "✗"
    print(f"      {status} {city_name:<15} Tmin={tmin}, Tmax={tmax}, Icon={icon}")
    
    return city_dict


def fix_json_file(json_path: Path, maps_dir: Path, cities_rel: list, model: str, retry_count: int) -> tuple[int, int]:
    """
    Corrige un fichier JSON en retraitant les stations avec données nulles.
    Retourne (nb_fixed, nb_still_null).
    """
    print(f"\n📄 Analyse: {json_path.name}")
    
    # Trouver les stations nulles
    null_stations = get_null_stations(json_path)
    
    if not null_stations:
        print(f"   ✅ Aucune donnée nulle, fichier OK")
        return 0, 0
    
    print(f"   ⚠️ {len(null_stations)} stations avec données nulles: {[s['nom'] for s in null_stations]}")
    
    # Trouver l'image source
    map_path = find_map_for_json(json_path, maps_dir)
    
    if map_path is None:
        print(f"   ❌ Image source introuvable")
        return 0, len(null_stations)
    
    print(f"   📍 Image source: {map_path.name}")
    
    # Charger l'image
    try:
        data = np.fromfile(str(map_path), dtype=np.uint8)
        img = cv2.imdecode(data, cv2.IMREAD_COLOR)
    except Exception as e:
        print(f"   ❌ Erreur lecture image: {e}")
        return 0, len(null_stations)
    
    if img is None:
        print(f"   ❌ Impossible de décoder l'image")
        return 0, len(null_stations)
    
    # Charger le JSON complet
    with open(json_path, "r", encoding="utf-8") as f:
        json_data = json.load(f)
    
    # Retraiter chaque station nulle
    fixed_count = 0
    still_null_count = 0
    
    stations = json_data.get("stations", [])
    for i, station in enumerate(stations):
        if station.get("tmin") is None and station.get("tmax") is None:
            print(f"   🔄 Retraitement de {station['nom']}...")
            updated_station = process_single_station(img, station.copy(), cities_rel, model, retry_count)
            
            if updated_station.get("tmin") is not None:
                stations[i] = updated_station
                fixed_count += 1
            else:
                still_null_count += 1
    
    # Sauvegarder le fichier mis à jour
    json_data["stations"] = stations
    json_data["_last_fix_attempt"] = datetime.now().isoformat()
    
    with file_lock:
        with open(json_path, "w", encoding="utf-8") as f:
            json.dump(json_data, f, ensure_ascii=False, indent=2)
    
    print(f"   💾 Fichier mis à jour: {fixed_count} corrigés, {still_null_count} toujours null")
    
    return fixed_count, still_null_count


def main():
    parser = argparse.ArgumentParser(description="Correction des données nulles et timeouts")
    parser.add_argument("--model", default=DEFAULT_MODEL, help="Modèle Ollama à utiliser")
    parser.add_argument("--input-dir", type=Path, default=DEFAULT_INPUT_DIR, help="Dossier des fichiers JSON")
    parser.add_argument("--maps-dir", type=Path, default=DEFAULT_MAPS_DIR, help="Dossier des cartes images")
    parser.add_argument("--retry-count", type=int, default=2, help="Nombre de tentatives par station")
    parser.add_argument("--dry-run", action="store_true", help="Afficher les fichiers à corriger sans les modifier")
    args = parser.parse_args()
    
    print("=" * 70)
    print("🔧 CORRECTEUR DE DONNÉES NULLES ET TIMEOUTS")
    print("=" * 70)
    print(f"📁 Dossier JSON   : {args.input_dir}")
    print(f"📁 Dossier cartes : {args.maps_dir}")
    print(f"🤖 Modèle         : {args.model}")
    print(f"⏱️  Timeout        : {TIMEOUT_SECONDS}s")
    print(f"🔄 Retries        : {args.retry_count}")
    print(f"🏃 Mode           : {'Dry Run' if args.dry_run else 'Correction'}")
    print("=" * 70)
    
    # Charger les villes
    if not Path(CITIES_REL_FILE).exists():
        print(f"❌ Fichier {CITIES_REL_FILE} introuvable")
        return
    
    with open(CITIES_REL_FILE, "r", encoding="utf-8") as f:
        all_cities = json.load(f)
    
    cities_rel = [c for c in all_cities if c["name"] in TARGET_CITIES]
    print(f"📍 {len(cities_rel)} villes ciblées chargées")
    
    # Scanner tous les fichiers JSON
    json_files = sorted(args.input_dir.rglob("*.json"))
    # Exclure les fichiers de cache
    json_files = [f for f in json_files if ".cache" not in str(f)]
    
    if not json_files:
        print(f"❌ Aucun fichier JSON trouvé dans {args.input_dir}")
        return
    
    print(f"\n🗂️ {len(json_files)} fichiers JSON trouvés")
    
    # Identifier les fichiers avec des données nulles
    files_with_nulls = []
    total_null_stations = 0
    
    for json_path in json_files:
        null_stations = get_null_stations(json_path)
        if null_stations:
            files_with_nulls.append((json_path, null_stations))
            total_null_stations += len(null_stations)
    
    print(f"⚠️ {len(files_with_nulls)} fichiers avec données nulles")
    print(f"📊 {total_null_stations} stations à retraiter au total")
    
    if not files_with_nulls:
        print("\n✅ Tous les fichiers sont complets !")
        return
    
    if args.dry_run:
        print("\n📋 FICHIERS À CORRIGER (dry run):")
        for json_path, null_stations in files_with_nulls:
            print(f"   - {json_path.name}: {[s['nom'] for s in null_stations]}")
        return
    
    # Traitement
    start_time = datetime.now()
    total_fixed = 0
    total_still_null = 0
    
    for json_path, _ in files_with_nulls:
        fixed, still_null = fix_json_file(json_path, args.maps_dir, cities_rel, args.model, args.retry_count)
        total_fixed += fixed
        total_still_null += still_null
    
    # Résumé
    elapsed = (datetime.now() - start_time).total_seconds()
    print("\n" + "=" * 70)
    print("📊 RÉSUMÉ FINAL")
    print("=" * 70)
    print(f"✅ Stations corrigées    : {total_fixed}")
    print(f"❌ Stations encore null  : {total_still_null}")
    print(f"⏱️  Durée totale          : {elapsed:.1f}s ({elapsed/60:.1f} min)")
    print("=" * 70)


if __name__ == "__main__":
    main()
