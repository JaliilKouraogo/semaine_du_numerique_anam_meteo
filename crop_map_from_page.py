from pathlib import Path
from PIL import Image
import os

INPUT_PAGE_DIR = "bulletins_fullpage"   # pages complètes (PNG/JPG)
OUTPUT_MAP_DIR = "bulletins_images"     # cartes découpées (pour l’OCR)

os.makedirs(OUTPUT_MAP_DIR, exist_ok=True)

# --- Coordonnées RELATIVES (0.0 à 1.0) ---

# Carte 1 : en haut à droite (observé / dernières 24h)
MAP1_X0 = 0.45   # 45 % depuis la gauche
MAP1_Y0 = 0.23   # 23 % depuis le haut
MAP1_X1 = 0.97   # 97 % (près du bord droit)
MAP1_Y1 = 0.55   # 55 % depuis le haut

# Carte 2 : en bas à droite (prévisions)
MAP2_X0 = 0.45
MAP2_Y0 = 0.56
MAP2_X1 = 0.97
MAP2_Y1 = 0.90


def crop_maps(image_path: Path):
    """Retourne un dict {'map1': img1, 'map2': img2} découpé dans la page."""
    img = Image.open(image_path)
    w, h = img.size

    def rel_crop(x0, y0, x1, y1):
        return img.crop((
            int(w * x0),
            int(h * y0),
            int(w * x1),
            int(h * y1),
        ))

    map1 = rel_crop(MAP1_X0, MAP1_Y0, MAP1_X1, MAP1_Y1)
    map2 = rel_crop(MAP2_X0, MAP2_Y0, MAP2_X1, MAP2_Y1)

    return {"map1": map1, "map2": map2}


def main():
    input_dir = Path(INPUT_PAGE_DIR)
    image_files = (
        list(input_dir.glob("*.png"))
        + list(input_dir.glob("*.jpg"))
        + list(input_dir.glob("*.jpeg"))
    )

    if not image_files:
        print(f"Aucune image trouvée dans {INPUT_PAGE_DIR}")
        return

    for img_path in image_files:
        print(f"Traitement de {img_path.name}")
        maps = crop_maps(img_path)

        # on sauve deux fichiers : _map1.png et _map2.png
        for key, cropped_img in maps.items():
            out_name = f"{img_path.stem}_{key}.png"
            out_path = Path(OUTPUT_MAP_DIR) / out_name
            cropped_img.save(out_path)
            print(f"✅ Carte découpée ({key}) -> {out_path}")

if __name__ == "__main__":
    main()
