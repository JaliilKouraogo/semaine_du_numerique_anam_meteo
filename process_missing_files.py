
import os
import sys
import logging
from datetime import datetime

# Adjust path
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), 'backend')))

from backend.utils.database import DatabaseManager
from backend.modules.pipeline_runner import PipelineRunner

# Logging config
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("ForceProcess")

# Init
db = DatabaseManager(os.getenv('DATABASE_URL'))
# Create a dummy config object needed by PipelineRunner
class Config:
    output_directory = "data/output"
    pdf_directory = "app/data/pdfs"

config = Config()
runner = PipelineRunner(db, config)

def force_process():
    logger.info("--- FORCING PROCESS FOR 2 & 3 FEB ---")
    
    # 1. Clean DB again just in case (Safety first)
    conn = db.get_connection()
    with conn.cursor() as cursor:
        cursor.execute("DELETE FROM bulletins WHERE date IN ('2026-02-02', '2026-02-03')")
        conn.commit()
    logger.info("Cleaned DB for 2026-02-02/03.")

    # 2. List target files
    target_files = [
        "Bulletin_du_02_Fevrier_2026_a_12h00_1770423746.pdf",
        "Bulletin_du_03_Fevrier_2026_a_12h00_2_1770554715.pdf"
    ]
    
    # Fallback paths
    base_dir = "app/data/pdfs"
    if not os.path.exists(base_dir):
        base_dir = "data/pdfs"
        
    abs_targets = []
    for f in target_files:
        p = os.path.join(base_dir, f)
        # Try to find exactly this file or one starting with same prefix if hash differs
        if not os.path.exists(p):
            # Try finding any file with similar name
            candidates = [cf for cf in os.listdir(base_dir) if cf.startswith(f[:25])] # "Bulletin_du_02_Fevrier_..."
            if candidates:
                p = os.path.join(base_dir, candidates[0])
                logger.info(f"Found alternative for {f}: {candidates[0]}")
            else:
                logger.error(f"Cannot find file for {f} in {base_dir}")
                continue
        
        abs_targets.append(os.path.abspath(p))

    if not abs_targets:
        logger.error("No files found to process!")
        return

    # 3. Running Pipeline Steps Manually on specific files
    logger.info(f"Processing {len(abs_targets)} files manually...")
    
    # OCR
    logger.info("Starting OCR...")
    pdf_results, temperature_data = runner._execute_ocr(abs_targets)
    if not pdf_results:
        logger.error("OCR yielded no results.")
        return

    # Classification
    logger.info("Starting Classification...")
    icon_data = runner._execute_classification(pdf_results)

    # Integration
    from backend.modules.data_integrator import DataIntegrator
    integrator = DataIntegrator(db)
    logger.info("Starting Integration...")
    integrated_data = runner._execute_integration(integrator, temperature_data, icon_data)
    
    logger.info(f"Integrated {len(integrated_data)} bulletins.")
    
    # Evaluation
    from backend.modules.forecast_evaluator import ForecastEvaluator
    evaluator = ForecastEvaluator(db)
    logger.info("Starting Evaluation...")
    # Force recalc
    eval_res = evaluator.evaluate_forecasts(force_recalculate=True)
    logger.info(f"Evaluation finished: {eval_res}")

if __name__ == "__main__":
    force_process()
