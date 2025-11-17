import cv2
import json
import os

# ========= CONFIG =========
IMAGE_PATH = "base_map_cities.png"   # ta carte de référence avec NOMS des villes
OUTPUT_JSON = "cities_positions.json"

cities = []

def mouse_callback(event, x, y, flags, param):
    global cities

    if event == cv2.EVENT_LBUTTONDOWN:
        print(f"\nClique détecté en x={x}, y={y}")
        city_name = input("Nom de la ville (ENTER pour ignorer) : ").strip()
        if city_name:
            cities.append({"name": city_name, "x": x, "y": y})
            print(f"Ville ajoutée : {city_name} -> ({x},{y})")
        else:
            print("Ignoré.")

def main():
    if not os.path.exists(IMAGE_PATH):
        print(f"Image introuvable: {IMAGE_PATH}")
        return

    img = cv2.imread(IMAGE_PATH)
    cv2.namedWindow("Cliquez sur les villes")
    cv2.setMouseCallback("Cliquez sur les villes", mouse_callback)

    print("Instructions :")
    print("- Clique GAUCHE sur le centre du chiffre de chaque ville")
    print("- Tape le NOM EXACT de la ville dans le terminal puis ENTER")
    print("- Quand tu as fini, appuie sur la touche 'q' dans la fenêtre")

    while True:
        temp = img.copy()
        # Dessiner les points déjà enregistrés
        for c in cities:
            cv2.circle(temp, (c["x"], c["y"]), 4, (0, 0, 255), -1)
            cv2.putText(temp, c["name"], (c["x"] + 5, c["y"] - 5),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.4, (0, 0, 255), 1)

        cv2.imshow("Cliquez sur les villes", temp)
        key = cv2.waitKey(50) & 0xFF
        if key == ord('q'):
            break

    cv2.destroyAllWindows()

    # Sauvegarde JSON
    with open(OUTPUT_JSON, "w", encoding="utf-8") as f:
        json.dump(cities, f, ensure_ascii=False, indent=2)

    print(f"\n✅ Coordonnées des villes sauvegardées dans {OUTPUT_JSON}")
    print("Exemple :")
    print(json.dumps(cities[:3], ensure_ascii=False, indent=2))

if __name__ == "__main__":
    main()
