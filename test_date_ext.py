from backend.utils.date_utils import extract_date_from_filename
from datetime import datetime

filenames = [
    "Bulletin_du_04_Février_2026_à_12h00_1770376104.pdf",
    "Bulletin_du_04_Fevrier_2026_a_12h00_1770376104.pdf",
    "bulletin du 04 fevrier 2026 a 12h00 1770376104.pdf"
]

for f in filenames:
    dt = extract_date_from_filename(f)
    print(f"File: {f} -> Date: {dt}")
