import sys
import os
from pathlib import Path

# Add backend to path
sys.path.append(os.getcwd())

from backend.modules.language_interpreter import LanguageInterpreter

def test_extraction():
    pdf_path = r"C:\Users\koura\Downloads\Anam\data\pdfs\Bulletin_du_02_Fevrier_2024_a_12h00.pdf"
    if not os.path.exists(pdf_path):
        print(f"File not found: {pdf_path}")
        return
        
    interpreter = LanguageInterpreter()
    obs, prev = interpreter._extraire_texte_pdf(pdf_path)
    
    print("--- OBSERVATION ---")
    print(obs if obs else "[EMPTY]")
    print("\n--- PREVISION ---")
    print(prev if prev else "[EMPTY]")

if __name__ == "__main__":
    test_extraction()
