
import logging
import os
import sys
from datetime import datetime

# Adjust Python path to root if needed
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), 'backend')))

from backend.utils.database import DatabaseManager
from backend.modules.data_integrator import DataIntegrator
from backend.modules.ocr_processor import OCRProcessor
from backend.modules.forecast_evaluator import ForecastEvaluator

# Setup Logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ForceImport")

# Init Modules
db = DatabaseManager(os.getenv('DATABASE_URL'))
integrator = DataIntegrator(db)
ocr = OCRProcessor()
evaluator = ForecastEvaluator(db)

def process_file_manual(filename, forced_type=None):
    # Paths handling
    paths_to_try = [
        f"app/data/pdfs/{filename}",
        f"data/pdfs/{filename}",
        f"./data/pdfs/{filename}"
    ]
    pdf_path = next((p for p in paths_to_try if os.path.exists(p)), None)
    
    if not pdf_path:
        logger.error(f"Fichier introuvable: {filename}")
        return

    logger.info(f"Traitement de {pdf_path}...")
    
    # 1. OCR (Returns raw lists of page/icon data)
    temp_blocks, icon_blocks = ocr.process_pdf(pdf_path)
    
    # 2. Wrap for DataIntegrator
    # DataIntegrator expects inputs like:
    # [{"pdf_path": "path/to.pdf", "data": [block1, block2]}]
    
    temp_wrapper = [{"pdf_path": str(pdf_path), "data": temp_blocks}]
    icon_wrapper = [{"pdf_path": str(pdf_path), "data": icon_blocks}]
    
    # 3. Integrate
    logger.info("Integration...")
    result = integrator.integrate_data(temp_wrapper, icon_wrapper)
    logger.info(f"Resultat integration: {result}")
    
    # Hack: Si le type détecté n'est pas bon, on force le type dans la DB
    # (DataIntegrator determine le type via _determine_map_type, souvent basé sur 'Prevision'/'Observation' dans OCR)
    
    if forced_type:
        # On update le dernier bulletin inséré pour ce fichier
        with db.get_connection().cursor() as cursor:
            # On cherche l'ID du bulletin créé/mis à jour pour ce fichier
            cursor.execute("SELECT id, type, date FROM bulletins WHERE file_path LIKE %s ORDER BY processed_at DESC LIMIT 1", (f"%{filename}%",))
            row = cursor.fetchone()
            if row:
                b_id, b_type, b_date = row
                logger.info(f"Bulletin en base: ID={b_id}, Type={b_type}, Date={b_date}")
                if b_type != forced_type:
                    logger.warning(f"Forcage du type {forced_type} (etait {b_type})")
                    cursor.execute("UPDATE bulletins SET type = %s WHERE id = %s", (forced_type, b_id))
                    db.get_connection().commit()

# LISTE A TRAITER
files = [
    # Prev du 2 Fevrier (pour le 3)
    ("Bulletin_du_02_Fevrier_2026_a_12h00_1770423746.pdf", "forecast"),
    # Obs du 3 Fevrier
    ("Bulletin_du_03_Fevrier_2026_a_12h00_2_1770554715.pdf", "observation")
]

if __name__ == "__main__":
    logger.info("--- DEBUT FORCE IMPORT ---")
    for f, t in files:
        process_file_manual(f, t)
    
    logger.info("--- RECALCUL METRIQUES ---")
    metrics = evaluator.evaluate_forecasts(force_recalculate=True)
    print("METRIQUES FINALES :", metrics)
