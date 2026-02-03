# crop_maps_recursive.py
from pathlib import Path
from PIL import Image
import os
import unicodedata
import re
import argparse

# Coordonnées relatives, ajustées sur ton exemple
MAP1_X0 = 0.45
MAP1_Y0 = 0.23
MAP1_X1 = 0.97
MAP1_Y1 = 0.55

MAP2_X0 = 0.45
MAP2_Y0 = 0.56
MAP2_X1 = 0.97
MAP2_Y1 = 0.90


def slugify(name: str) -> str:
    """ Nettoie un nom de fichier en supprimant accents et caractères spéciaux. """
    nfkd = unicodedata.normalize("NFKD", name)
    no_accents = "".join(c for c in nfkd if not unicodedata.combining(c))
    no_spaces  = no_accents.replace(" ", "_").replace(":", "h")
    safe = re.sub(r"[^a-zA-Z0-9._-]", "_", no_spaces)
    safe = re.sub(r"_+", "_", safe).strip("_")
    return safe


def crop_maps(image_path: Path):
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
    parser = argparse.ArgumentParser(description="Extrait les cartes météo des images de pages")
    parser.add_argument("--input", type=Path, default=Path("2024_fullpage"), help="Dossier source des images")
    parser.add_argument("--output", type=Path, default=Path("2024_maps"), help="Dossier de sortie")
    args = parser.parse_args()

    ROOT_PAGES = args.input
    OUTPUT_ROOT = args.output

    os.makedirs(OUTPUT_ROOT, exist_ok=True)

    page_images = list(ROOT_PAGES.rglob("*.png")) + \
                  list(ROOT_PAGES.rglob("*.jpg")) + \
                  list(ROOT_PAGES.rglob("*.jpeg"))

    if not page_images:
        print(f"Aucune image trouvée dans {ROOT_PAGES}")
        return

    print(f"🖼️ {len(page_images)} images trouvées dans {ROOT_PAGES}")

    for img_path in page_images:
        print(f"Traitement de : {img_path}")

        # Normalisation du nom
        safe_stem = slugify(img_path.stem)

        # Exemple : 2024_fullpage/JANVIER/...  => out: 2024_maps/JANVIER
        rel_dir = img_path.parent.relative_to(ROOT_PAGES)
        out_dir = OUTPUT_ROOT / rel_dir
        os.makedirs(out_dir, exist_ok=True)

        maps = crop_maps(img_path)

        for key, cropped_img in maps.items():
            out_name = f"{safe_stem}_{key}.png"   # nom propre
            out_path = out_dir / out_name
            cropped_img.save(out_path)
            print(f"   ✅ Carte {key} -> {out_path}")


if __name__ == "__main__":
    main()

