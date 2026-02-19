
import os
import sys
import logging

# Sys path hack
sys.path.append(os.path.abspath(os.path.join(os.path.dirname(__file__), 'backend')))

from backend.utils.database import DatabaseManager
from backend.modules.pipeline_runner import PipelineRunner
from backend.modules.pipeline_runner import _list_pending_pdfs, _normalize_path

# Logging
logging.basicConfig(level=logging.INFO)

# Init
db = DatabaseManager(os.getenv('DATABASE_URL'))
config = type('Config', (), {'output_directory': 'data/output', 'pdf_directory': 'app/data/pdfs'})()

# Check DB state
processed_in_db = db.list_processed_pdf_paths()
print(f"Processed PDFs in DB: {len(processed_in_db)}")

# Check Local Files
processed_paths = {
    _normalize_path(p) for p in processed_in_db
}

# Find pending
pdf_dir = "app/data/pdfs"
if not os.path.exists(pdf_dir):
    pdf_dir = "data/pdfs"

print(f"Scanning PDF dir: {pdf_dir}")

pending = _list_pending_pdfs(pdf_dir, processed_paths)
print(f"Pending PDFs count: {len(pending)}")
print("Pending PDFs sample:", pending[:5])

# Check specifically for our files
targets = [
    "Bulletin_du_02_Fevrier_2026_a_12h00_1770423746.pdf",
    "Bulletin_du_03_Fevrier_2026_a_12h00_2_1770554715.pdf"
]

for t in targets:
    norm = _normalize_path(t)
    in_db = norm in processed_paths
    print(f"File {t} -> Normalized: {norm} -> In DB? {in_db}")

