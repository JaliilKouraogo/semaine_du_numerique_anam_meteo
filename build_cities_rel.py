import cv2
import json

# ---------- À ADAPTER SELON TON FICHIER ----------
REFERENCE_MAP = "base_map_cities.png"     # une carte où tu as déjà les villes cliquées
CITIES_POS_FILE = "cities_positions.json" # ton fichier actuel (x, y absolus)
OUTPUT_REL_FILE = "cities_rel.json"       # fichier de sortie (x_rel, y_rel)

def detect_map_bbox(img):
    """
    Détecte automatiquement le rectangle qui entoure la carte du Burkina.
    Retourne (x0, y0, x1, y1).
    """
    gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
    blur = cv2.GaussianBlur(gray, (5, 5), 0)

    # IMPORTANT : si le résultat est mauvais, essaye THRESH_BINARY au lieu de THRESH_BINARY_INV
    _, thresh = cv2.threshold(blur, 0, 255,
                              cv2.THRESH_BINARY_INV + cv2.THRESH_OTSU)

    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL,
                                   cv2.CHAIN_APPROX_SIMPLE)

    h, w = gray.shape
    img_area = w * h

    best = None
    best_area = 0

    for cnt in contours:
        x, y, cw, ch = cv2.boundingRect(cnt)
        area = cw * ch

        # on ignore les trucs trop petits ou trop grands (bordure entière)
        if area < 0.05 * img_area:
            continue
        if area > 0.9 * img_area:
            continue

        if area > best_area:
            best_area = area
            best = (x, y, cw, ch)

    if best is None:
        raise RuntimeError("Impossible de trouver la carte dans l'image")

    x, y, cw, ch = best
    return x, y, x + cw, y + ch


def main():
    img = cv2.imread(REFERENCE_MAP)
    if img is None:
        print(f"❌ Impossible de charger {REFERENCE_MAP}")
        return

    x0, y0, x1, y1 = detect_map_bbox(img)
    print(f"Boîte carte détectée: x0={x0}, y0={y0}, x1={x1}, y1={y1}")
    map_w = x1 - x0
    map_h = y1 - y0

    with open(CITIES_POS_FILE, "r", encoding="utf-8") as f:
        cities = json.load(f)

    cities_rel = []
    for c in cities:
        x = c["x"]
        y = c["y"]
        x_rel = (x - x0) / map_w
        y_rel = (y - y0) / map_h
        cities_rel.append({
            "name": c["name"],
            "x_rel": x_rel,
            "y_rel": y_rel
        })
        print(f'{c["name"]}: x_rel={x_rel:.3f}, y_rel={y_rel:.3f}')

    with open(OUTPUT_REL_FILE, "w", encoding="utf-8") as f:
        json.dump(cities_rel, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Coordonnées relatives sauvegardées dans {OUTPUT_REL_FILE}")

if __name__ == "__main__":
    main()
