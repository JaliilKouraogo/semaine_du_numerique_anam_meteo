import logging
import os
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

def process_file(filename, expected_type):
    pdf_path = f"app/data/pdfs/{filename}"
    if not os.path.exists(pdf_path):
        # Fallback local testing
        pdf_path = f"data/pdfs/{filename}"
        if not os.path.exists(pdf_path):
            logger.error(f"Fichier inexistant : {filename}")
            return

    logger.info(f"Traitement de {filename} comme {expected_type}...")
    
    # 1. OCR
    temp_data, icon_data = ocr.process_pdf(pdf_path)
    if not temp_data:
        logger.error("OCR échoué (vide).")
        return

    # 2. Integrate
    # On mocke la structure attendue par data_integrator
    # temperature_data expects: [{'pdf_path': ..., 'data': [...]}]
    # icon_data expects: similar or list of items
    
    # Correction : integrate_data attend (temperature_data_list, icon_data_list)
    # Et chaque élément doit avoir 'pdf_path'.
    
    for t in temp_data: t['pdf_path'] = str(pdf_path)
    # icon_data might be a list of dicts, let's normalize
    if isinstance(icon_data, list):
        for i in icon_data: i['pdf_path'] = str(pdf_path)
    
    # On force le type en passant 'type' dans l'appel (si modification faite)
    # Mais DataIntegrator déduit le type du nom de fichier.
    # Comme le fichier s'appelle "Bulletin_du_03_Fevrier", il verra la date 03.
    # MAIS le type "Forecast"/"Observation" est déterminé par le contenu ou la détection.
    # On va laisser DataIntegrator faire son job, car il utilise determine_bulletin_type.
    
    # Hack : Si on veut forcer le type, on peut le faire en post-update si besoin,
    # mais DataIntegrator le fait via `_determine_map_type`.
    
    processed = integrator.integrate_data(temp_data, icon_data)
    logger.info(f"Resultat integration : {len(processed)} items.")

# Fichiers cibles
files = [
    ("Bulletin_du_02_Fevrier_2026_a_12h00_1770423746.pdf", "forecast"),
    ("Bulletin_du_03_Fevrier_2026_a_12h00_2_1770554715.pdf", "observation")
]

logger.info("Début Force Import...")
for f, t in files:
    process_file(f, t)

logger.info("Recalcul des métriques...")
res = evaluator.evaluate_forecasts(force_recalculate=True)
logger.info(f"Métriques calculées : {res}")
print("DONE")
