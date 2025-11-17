import cv2
import json
import os
import re
import base64
import requests
from pathlib import Path

# ---------- CONFIG ----------
CITIES_REL_FILE = "cities_rel.json"        # fichier avec x_rel / y_rel
MAPS_ROOT = Path("2024_maps")             # dossier *_map1/_map2
OUTPUT_ROOT = Path("2024_temps_qwen")     # sortie JSON
os.makedirs(OUTPUT_ROOT, exist_ok=True)

# taille du crop autour de chaque ville (en px)
CROP_HALF_SIZE = 80  # plus large pour aider le modèle

# config Ollama
OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "qwen3-vl:8b"  # adapte si ton modèle a un autre nom


# ---------- 1. Détection automatique de la boîte carte ----------
def detect_map_bbox(img):
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)

    # Si résultat nul, tu pourras tester THRESH_BINARY à la place
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


# ---------- 2. Appel Qwen3-VL via Ollama pour un crop ----------
def call_qwen_for_crop(crop_bgr, city_name, map_path_str):
    # encode le crop en PNG + base64
    ok, buf = cv2.imencode(".png", crop_bgr)
    if not ok:
        return None, None

    img_bytes = buf.tobytes()
    img_b64 = base64.b64encode(img_bytes).decode("ascii")

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

Answer with valid JSON only, no extra text, in this format:
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
        print(f" ⚠ Erreur appel Ollama pour {city_name} ({map_path_str}): {e}")
        return None, None

    data = resp.json()
    text = data.get("response", "").strip()

    # Essayer d'isoler un JSON dans la réponse
    match = re.search(r"\{.*\}", text, re.DOTALL)
    if not match:
        print(f" ⚠ Réponse non JSON pour {city_name}: {text[:100]}...")
        return None, None

    json_str = match.group(0)
    try:
        obj = json.loads(json_str)
    except Exception as e:
        print(f" ⚠ Erreur parse JSON pour {city_name}: {e} / raw={json_str}")
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
    return tmin, tmax


# ---------- 3. Deviner date + type de carte ----------
def infer_date_from_filename(path: Path) -> str:
    # essaie de trouver AAAA-MM-JJ dans le nom de fichier
    m = re.search(r"(20\d{2})[^\d]([01]\d)[^\d]([0-3]\d)", path.name)
    if m:
        y, mo, d = m.groups()
        return f"{y}-{mo}-{d}"
    return path.stem


def main():
    # 1) Charger les coords relatives des villes
    with open(CITIES_REL_FILE, "r", encoding="utf-8") as f:
        cities_rel = json.load(f)

    # 2) Lister toutes les cartes (triées pour traitement dans l'ordre)
    map_files = (
        list(MAPS_ROOT.rglob("*.png"))
        + list(MAPS_ROOT.rglob("*.jpg"))
        + list(MAPS_ROOT.rglob("*.jpeg"))
    )
    map_files = sorted(map_files, key=lambda p: str(p))

    if not map_files:
        print(f"Aucune carte trouvée dans {MAPS_ROOT}")
        return

    for map_path in map_files:
        # --- déterminer date + type de carte pour savoir quel JSON devrait exister ---
        date_bulletin = infer_date_from_filename(map_path)

        if "_map1" in map_path.stem:
            map_type = "observed"
        elif "_map2" in map_path.stem:
            map_type = "forecast"
        else:
            map_type = "map"

        # dossier de sortie relatif
        rel_dir = map_path.parent.relative_to(MAPS_ROOT)
        out_dir = OUTPUT_ROOT / rel_dir
        os.makedirs(out_dir, exist_ok=True)

        out_file = out_dir / f"{date_bulletin}_{map_type}.json"

        # ---------- ICI : SKIP SI DÉJÀ TRAITÉ ----------
        if out_file.exists():
            print(f"\n=== SKIP (déjà traité) : {map_path} ===")
            print(f"    -> JSON existe déjà : {out_file}")
            continue

        print(f"\n=== Traitement de : {map_path} ===")

        img = cv2.imread(str(map_path))
        if img is None:
            print(" ⚠ Impossible de charger l'image, ignoré.")
            continue

        # 3) Détecter la carte dans cette image
        try:
            x0, y0, x1, y1 = detect_map_bbox(img)
        except RuntimeError as e:
            print(f" ⚠ {e}")
            continue

        map_w = x1 - x0
        map_h = y1 - y0

        stations = []

        for c in cities_rel:
            name = c["name"]
            xr = c["x_rel"]
            yr = c["y_rel"]

            # 5) Calcul (x, y) dans l'image courante
            x = int(x0 + xr * map_w)
            y = int(y0 + yr * map_h)

            h, w = img.shape[:2]
            x1c = max(0, x - CROP_HALF_SIZE)
            y1c = max(0, y - CROP_HALF_SIZE)
            x2c = min(w, x + CROP_HALF_SIZE)
            y2c = min(h, y + CROP_HALF_SIZE)
            crop = img[y1c:y2c, x1c:x2c]

            if crop.size == 0:
                print(f" ⚠ Crop vide pour {name}, on skip.")
                tmin = tmax = None
            else:
                tmin, tmax = call_qwen_for_crop(crop, name, str(map_path))

            print(f" {name:<15} -> Tmin={tmin}, Tmax={tmax}")
            stations.append(
                {
                    "nom": name,
                    "tmin": tmin,
                    "tmax": tmax,
                }
            )

        bulletin_obj = {
            "date_bulletin": date_bulletin,
            "map_type": map_type,
            "source_image": map_path.name,
            "stations": stations,
        }

        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(bulletin_obj, f, ensure_ascii=False, indent=2)

        print(f"✅ JSON sauvegardé -> {out_file}")


if __name__ == "__main__":
    main()
