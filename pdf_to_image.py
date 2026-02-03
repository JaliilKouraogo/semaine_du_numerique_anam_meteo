import fitz  # PyMuPDF
from pathlib import Path
from PIL import Image
import os

INPUT_PDF_DIR = "bulletins_pdf"      # dossier avec tes PDF
OUTPUT_IMG_DIR = "bulletins_fullpage"  # on mettra les pages complètes ici

os.makedirs(OUTPUT_IMG_DIR, exist_ok=True)

def pdf_to_images(pdf_path, output_dir, dpi=200):
    doc = fitz.open(pdf_path)
    for i, page in enumerate(doc):
        pix = page.get_pixmap(dpi=dpi)
        out_name = f"{Path(pdf_path).stem}_page{i+1}.png"
        out_path = Path(output_dir) / out_name
        pix.save(str(out_path))
        print(f"✅ Page {i+1} -> {out_path}")

def main():
    pdf_dir = Path(INPUT_PDF_DIR)
    pdf_files = list(pdf_dir.glob("*.pdf"))

    if not pdf_files:
        print(f"Aucun PDF trouvé dans {INPUT_PDF_DIR}")
        return

    for pdf in pdf_files:
        print(f"\n=== Conversion PDF -> images : {pdf.name} ===")
        pdf_to_images(str(pdf), OUTPUT_IMG_DIR)

if __name__ == "__main__":
    main()
