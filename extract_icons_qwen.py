import cv2
import json
import os
import re
import base64
import requests
from pathlib import Path

# ---------- CONFIG ----------
CITIES_REL_FILE = "cities_rel.json"        # fichier avec x_rel / y_rel
MAPS_ROOT       = Path("2024_maps")        # dossier *_map1/_map2
OUTPUT_ROOT     = Path("2024_temps_qwen")  # sortie JSON
os.makedirs(OUTPUT_ROOT, exist_ok=True)

# taille du crop autour de chaque ville (en px)
CROP_HALF_SIZE = 80  # plus large pour aider le modèle

# config Ollama
OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "qwen3-vl:8b"  # adapte si ton modèle a un autre nom

# Active la détection des icônes météo
DETECT_WEATHER_ICONS = True


# ---------- Normalisation & catégories météo ----------
# Catégories finales autorisées dans le JSON
CANONICAL_ICONS = [
    "pluie orageuse isolé",
    "orage isolé",
    "pluie isolée",
    "temps partiellement nuageux",
    "ciel couvert",
    "ciel degagé",
    "pousiere en suspension",
]

# Termes possibles dans la légende / par défaut (ce que tu as donné)
DEFAULT_LEGEND_TERMS = [
    "pluie orageuse isolé",
    "orage isolé",
    "pluie isolée",
    "temps partiellement nuageux",
    "ciel couvert",
    "ciel degagé",
    "pousiere en suspension",
    "pluie orageux",
    "orage",
    "plui",
    "ciel couvert",
    "ciel nuageux",
]

def _strip_accents(s: str) -> str:
    """Retire les accents principaux (simplifié, sans unidecode)."""
    repl = {
        "é": "e", "è": "e", "ê": "e", "ë": "e",
        "à": "a", "â": "a",
        "î": "i", "ï": "i",
        "ô": "o",
        "ù": "u", "û": "u",
        "ç": "c",
    }
    for k, v in repl.items():
        s = s.replace(k, v)
    return s

def normalize_weather_icon(raw_icon):
    """
    Transforme un texte brut ("pluie orageux", "Orage", "ciel nuageux", "ensoleillé", etc.)
    en une des 7 catégories CANONICAL_ICONS ou None.
    """
    if not raw_icon:
        return None

    s = str(raw_icon).strip().lower()
    s = _strip_accents(s)

    # Poussière en suspension
    if "poussi" in s:
        return "pousiere en suspension"

    # Pluie orageuse (pluie + orage / orageux)
    if ("pluie" in s or "plui" in s) and ("orage" in s or "orageux" in s):
        return "pluie orageuse isolé"

    # Orage simple
    if "orage" in s or "orageux" in s:
        return "orage isolé"

    # Pluie simple
    if "pluie" in s or "plui" in s:
        return "pluie isolée"

    # Ciel couvert
    if "couvert" in s:
        return "ciel couvert"

    # Nuageux -> temps partiellement nuageux
    if "nuageux" in s or "nuageuse" in s or "nuage" in s:
        return "temps partiellement nuageux"

    # Ciel dégagé / ensoleillé
    if "degage" in s or "ensole" in s:
        return "ciel degagé"

    return None


# ---------- 1. Détection automatique de la boîte carte ----------
def detect_map_bbox(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)

    _, thresh = cv2.threshold(
        blur, 0, 255,
        cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU
    )

    contours, _ = cv2.findContours(
        thresh, cv2.RETR_EXTERNAL,
        cv2.CHAIN_APPROX_SIMPLE
    )

    h, w = gray.shape
    img_area = w * h

    best = None
    best_area = 0

    for cnt in contours:
        x, y, cw, ch = cv2.boundingRect(cnt)
        area = cw * ch

        # on ignore les petits/immenses trucs
        if area < 0.05 * img_area:
            continue
        if area > 0.9 * img_area:
            continue

        if area > best_area:
            best_area = area
            best = (x, y, cw, ch)

    if best is None:
        raise RuntimeError("Impossible de trouver la carte dans cette image")

    x, y, cw, ch = best
    return x, y, x + cw, y + ch


# ---------- Extraction et analyse de la légende ----------
def extract_legend_area(img):
    """Extrait la zone de légende (généralement en bas de l'image)"""
    h, w = img.shape[:2]
    # Prendre les 30% du bas de l'image
    legend_zone = img[int(h * 0.7):h, :]
    return legend_zone


def detect_weather_legend(legend_crop):
    """
    Analyse la légende pour détecter les types d'icônes météo.
    On ne fait que lire le texte, ensuite on normalise avec normalize_weather_icon.
    """
    ok, buf = cv2.imencode(".png", legend_crop)
    if not ok:
        return {}

    img_bytes = buf.tobytes()
    img_b64 = base64.b64encode(img_bytes).decode("ascii")

    prompt = """
You see the legend of a weather map (Burkina Faso).

Your only job:
- Read the FRENCH text labels of each weather icon, exactly as they appear.
- Do NOT interpret, only transcribe the legend texts.

Return ONLY a JSON array like:
[
  {"icon": "icon1", "label": "Pluie orageuse isolée"},
  {"icon": "icon2", "label": "Ciel nuageux"},
  {"icon": "icon3", "label": "Ciel dégagé"}
]

If no legend is visible, return [].
""".strip()

    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "images": [img_b64],
        "stream": False,
    }

    try:
        resp = requests.post(OLLAMA_URL, json=payload, timeout=120)
        resp.raise_for_status()
        data = resp.json()
        text = data.get("response", "").strip()
        
        # Extraire le JSON array
        match = re.search(r"\[.*\]", text, re.DOTALL)
        if match:
            legend_data = json.loads(match.group(0))
            # Convertir en dictionnaire {icon_key: label_texte}
            legend_dict = {}
            for item in legend_data:
                icon_key = item.get("icon")
                label_raw = item.get("label")
                if icon_key and label_raw:
                    legend_dict[icon_key] = label_raw
            return legend_dict
    except Exception as e:
        print(f"  ⚠ Erreur détection légende: {e}")
    
    return {}


# ---------- 2. Appel Qwen3-VL via Ollama pour un crop ----------
def call_qwen_for_crop(
    crop_bgr,
    city_name,
    map_path_str,
    detect_icon=False,
    allowed_icons_for_map=None
):
    ok, buf = cv2.imencode(".png", crop_bgr)
    if not ok:
        if detect_icon:
            return None, None, None
        return None, None

    img_bytes = buf.tobytes()
    img_b64 = base64.b64encode(img_bytes).decode("ascii")

    if detect_icon:
        # Si aucune liste spécifique n'est donnée, on utilise toutes les catégories
        if not allowed_icons_for_map:
            allowed_icons_for_map = CANONICAL_ICONS

        # Liste sous forme de texte pour le prompt
        icons_list_str = ", ".join(f'"{x}"' for x in allowed_icons_for_map)

        prompt = f"""
You are a very strict OCR assistant for weather maps of Burkina Faso.

This image is a small crop around the city "{city_name}" on a weather map.

You ALREADY know the legend of this map.
The ONLY possible weather labels are in this list (FRENCH):

POSSIBLE_WEATHER = [{icons_list_str}]

Your tasks:
1. Read the temperature range near the city (format "A/B" for min/max, or single number).
2. Choose "weather_icon" as:
   - EXACTLY one of the strings from POSSIBLE_WEATHER, OR
   - null if you cannot clearly identify it.

RULES (VERY IMPORTANT):
- You MUST NOT invent any other label outside POSSIBLE_WEATHER.
- If you are not sure, set "weather_icon": null.
- Temperatures must be integers between -5 and 60 °C.

Return ONLY valid JSON like:
{{
  "tmin": 25,
  "tmax": 39,
  "weather_icon": "ciel couvert"
}}

If unreadable:
{{
  "tmin": null,
  "tmax": null,
  "weather_icon": null
}}
""".strip()
    else:
        prompt = f"""
You are a precise OCR assistant for weather maps of Burkina Faso.

This image is a small crop around the city "{city_name}" on a weather map.
Near the city name, there is a temperature range written like "25/39" (min/max in °C).

Your task:
- Read the temperature range for this city ONLY.
- If you see exactly "A/B", then tmin = A and tmax = B.
- If you see only one number (e.g. "37"), then tmin = tmax = 37.
- Temperatures are integers in °C and must be between -5 and 60.
- If you cannot clearly read the value, return null for both.

Answer with **valid JSON only**, no extra text, in this format:

{{
  "tmin": 25,
  "tmax": 39
}}

If unreadable, answer:

{{
  "tmin": null,
  "tmax": null
}}
""".strip()

    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "images": [img_b64],
        "stream": False,
    }

    try:
        resp = requests.post(OLLAMA_URL, json=payload, timeout=120)
        resp.raise_for_status()
    except Exception as e:
        print(f"  ⚠ Erreur appel Ollama pour {city_name} ({map_path_str}): {e}")
        if detect_icon:
            return None, None, None
        return None, None

    data = resp.json()
    text = data.get("response", "").strip()

    # Essayer d'isoler un JSON dans la réponse
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        print(f"  ⚠ Réponse non JSON pour {city_name}: {text[:100]}...")
        if detect_icon:
            return None, None, None
        return None, None

    json_str = match.group(0)
    try:
        obj = json.loads(json_str)
    except Exception as e:
        print(f"  ⚠ Erreur parse JSON pour {city_name}: {e} / raw={json_str}")
        if detect_icon:
            return None, None, None
        return None, None

    tmin = obj.get("tmin")
    tmax = obj.get("tmax")

    # filtre simple valeurs aberrantes
    def clean(v):
        if v is None:
            return None
        try:
            v = int(v)
        except Exception:
            return None
        if -5 <= v <= 60:
            return v
        return None

    tmin = clean(tmin)
    tmax = clean(tmax)

    if detect_icon:
        raw_icon = obj.get("weather_icon")
        # Normalisation vers une catégorie finale
        canon = normalize_weather_icon(raw_icon)

        # On impose aussi qu'elle soit bien dans allowed_icons_for_map
        if canon and allowed_icons_for_map and canon not in allowed_icons_for_map:
            canon = None

        return tmin, tmax, canon
    
    return tmin, tmax


# ---------- 3. Deviner date + type de carte ----------
def infer_date_from_filename(path: Path) -> str:
    m = re.search(r"(20\d{2})[^\d]([01]\d)[^\d]([0-3]\d)", path.name)
    if m:
        y, mo, d = m.groups()
        return f"{y}-{mo}-{d}"
    return path.stem


def main():
    # 1) Charger les coords relatives des villes
    with open(CITIES_REL_FILE, "r", encoding="utf-8") as f:
        cities_rel = json.load(f)

    # 2) Lister toutes les cartes
    map_files = list(MAPS_ROOT.rglob("*.png")) \
              + list(MAPS_ROOT.rglob("*.jpg")) \
              + list(MAPS_ROOT.rglob("*.jpeg"))

    if not map_files:
        print(f"Aucune carte trouvée dans {MAPS_ROOT}")
        return

    # Trier les cartes par date (puis par nom)
    map_files.sort(key=lambda p: (infer_date_from_filename(p), p.name))

    for map_path in map_files:
        # D'abord déterminer date + type pour connaître le futur JSON
        rel_dir = map_path.parent.relative_to(MAPS_ROOT)
        out_dir = OUTPUT_ROOT / rel_dir
        os.makedirs(out_dir, exist_ok=True)

        date_bulletin = infer_date_from_filename(map_path)
        if "_map1" in map_path.stem:
            map_type = "observed"
        elif "_map2" in map_path.stem:
            map_type = "forecast"
        else:
            map_type = None

        out_file = out_dir / f"{date_bulletin}_{map_type or 'map'}.json"

        # Si le JSON existe déjà, on saute ce fichier
        if out_file.exists():
            print(f"\n⏩ JSON déjà présent, on saute : {map_path} -> {out_file}")
            continue

        print(f"\n=== Traitement de : {map_path} ===")
        img = cv2.imread(str(map_path))
        if img is None:
            print("  ⚠ Impossible de charger l'image, ignoré.")
            continue

        # 1) Détecter la légende une seule fois par carte
        legend_info = {}
        allowed_icons_for_map = list(CANONICAL_ICONS)

        if DETECT_WEATHER_ICONS:
            print("  📋 Analyse de la légende...")
            legend_crop = extract_legend_area(img)
            legend_info = detect_weather_legend(legend_crop)

            # Si on a une légende, on déduit les icônes disponibles sur CETTE carte
            if legend_info:
                found_canon = set()
                for label in legend_info.values():
                    canon = normalize_weather_icon(label)
                    if canon:
                        found_canon.add(canon)
                if found_canon:
                    allowed_icons_for_map = sorted(found_canon)
                print(f"  ✅ Icônes disponibles sur cette carte: {allowed_icons_for_map}")
            else:
                print("  ⚠ Aucune légende lisible, on utilise les catégories par défaut.")

        # 2) Détecter la carte dans cette image
        try:
            x0, y0, x1, y1 = detect_map_bbox(img)
        except RuntimeError as e:
            print(f"  ⚠ {e}")
            continue

        map_w = x1 - x0
        map_h = y1 - y0

        stations = []

        for c in cities_rel:
            name = c["name"]
            xr = c["x_rel"]
            yr = c["y_rel"]

            # Calcul (x, y) dans l'image courante
            x = int(x0 + xr * map_w)
            y = int(y0 + yr * map_h)

            h, w = img.shape[:2]
            x1c = max(0, x - CROP_HALF_SIZE)
            y1c = max(0, y - CROP_HALF_SIZE)
            x2c = min(w, x + CROP_HALF_SIZE)
            y2c = min(h, y + CROP_HALF_SIZE)

            crop = img[y1c:y2c, x1c:x2c]
            if crop.size == 0:
                print(f"  ⚠ Crop vide pour {name}, on skip.")
                tmin = tmax = weather_icon = None
            else:
                if DETECT_WEATHER_ICONS:
                    tmin, tmax, weather_icon = call_qwen_for_crop(
                        crop,
                        name,
                        str(map_path),
                        detect_icon=True,
                        allowed_icons_for_map=allowed_icons_for_map,
                    )
                else:
                    tmin, tmax = call_qwen_for_crop(
                        crop,
                        name,
                        str(map_path),
                        detect_icon=False,
                    )
                    weather_icon = None

            if DETECT_WEATHER_ICONS:
                print(f"  {name:<15} -> Tmin={tmin}, Tmax={tmax}, Icône={weather_icon}")
            else:
                print(f"  {name:<15} -> Tmin={tmin}, Tmax={tmax}")

            station_data = {
                "nom": name,
                "tmin": tmin,
                "tmax": tmax,
            }
            if DETECT_WEATHER_ICONS:
                station_data["weather_icon"] = weather_icon
            
            stations.append(station_data)

        bulletin_obj = {
            "date_bulletin": date_bulletin,
            "map_type": map_type,
            "source_image": map_path.name,
            "stations": stations,
        }
        
        if legend_info:
            bulletin_obj["legend"] = legend_info

        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(bulletin_obj, f, ensure_ascii=False, indent=2)

        print(f"✅ JSON sauvegardé -> {out_file}")


if __name__ == "__main__":
    main()
