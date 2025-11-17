# 1_pdf_to_images_recursive.py
import fitz  # PyMuPDF
from pathlib import Path
import os
import unicodedata
import re

ROOT_PDF_DIR = Path("2024")          # ton dossier avec JANVIER..DECEMBRE
OUTPUT_ROOT  = Path("2024_fullpage") # où on va mettre les pages en PNG


def slugify(name: str) -> str:
    """
    Nettoie le nom de fichier :
    - enlève les accents
    - remplace les espaces par '_'
    - remplace ':' par 'h'
    - remplace les autres caractères spéciaux par '_'
    - évite les '__' multiples
    """
    # 1) Normalisation Unicode, enlève les accents
    nfkd = unicodedata.normalize("NFKD", name)
    no_accents = "".join(c for c in nfkd if not unicodedata.combining(c))

    # 2) Espaces -> underscore
    no_spaces = no_accents.replace(" ", "_")

    # 3) ':' -> 'h' (si jamais il y en a)
    no_spaces = no_spaces.replace(":", "h")

    # 4) Ne garder que [a-zA-Z0-9._-], le reste -> '_'
    safe = re.sub(r"[^a-zA-Z0-9._-]", "_", no_spaces)

    # 5) Nettoyage des underscores multiples + trim
    safe = re.sub(r"_+", "_", safe).strip("_")

    return safe


def pdf_to_images(pdf_path: Path, out_dir: Path, dpi: int = 200):
    doc = fitz.open(pdf_path)
    os.makedirs(out_dir, exist_ok=True)

    # on nettoie le nom du PDF
    safe_stem = slugify(pdf_path.stem)

    for i, page in enumerate(doc):
        pix = page.get_pixmap(dpi=dpi)
        out_name = f"{safe_stem}_page{i+1}.png"
        out_path = out_dir / out_name
        pix.save(str(out_path))
        print(f"   Page {i+1} -> {out_path}")


def main():
    pdf_files = list(ROOT_PDF_DIR.rglob("*.pdf"))
    if not pdf_files:
        print(f"Aucun PDF trouvé dans {ROOT_PDF_DIR}")
        return

    for pdf_path in pdf_files:
        # ex: 2024/JANVIER/Bulletin du 01 aout 2024 à 12h00.pdf
        rel_dir = pdf_path.parent.relative_to(ROOT_PDF_DIR)  # JANVIER, FEVRIER...
        out_dir = OUTPUT_ROOT / rel_dir                      # 2024_fullpage/JANVIER
        print(f"\n=== Conversion : {pdf_path} ===")
        pdf_to_images(pdf_path, out_dir)


if __name__ == "__main__":
    main()
