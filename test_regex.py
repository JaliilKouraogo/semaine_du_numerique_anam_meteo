
import re

filenames = [
    "bulletin_du_04_février_2026_à_12h00_1739265432.pdf",
    "bulletin_du_04_fevrier_2026_à_12h00_1739265432.pdf",
    "04_février_2026.pdf"
]

regex_old = r"(\d{1,2})_([a-z]+)_(\d{4})"
regex_new = r"(\d{1,2})_([^\W\d_]+)_(\d{4})"

print("Testing OLD regex:")
for f in filenames:
    match = re.search(regex_old, f)
    print(f"File: {f} -> Match: {match.groups() if match else 'None'}")

print("\nTesting NEW regex:")
for f in filenames:
    match = re.search(regex_new, f)
    print(f"File: {f} -> Match: {match.groups() if match else 'None'}")
