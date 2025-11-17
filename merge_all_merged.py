"""
Regroupe tous les fichiers *_merged.json présents dans 2024_temps_merged/
en un seul fichier JSON (par défaut all_merged.json).

Usage :
    python merge_all_merged.py
"""

from __future__ import annotations

import json
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List

MERGED_ROOT = Path("2024_temps_merged")
OUTPUT_FILE = MERGED_ROOT / "all_merged.json"
DATA_DIR = Path("data")
DATA_OUTPUT = DATA_DIR / "all_merged.json"


def read_merged_files(root: Path) -> List[Dict[str, Any]]:
    files = sorted(root.rglob("*_merged.json"))
    entries: List[Dict[str, Any]] = []
    if not files:
        print("⚠️  Aucun fichier *_merged.json trouvé.")
        return entries

    for path in files:
        try:
            obj = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            print(f"❌ Impossible de lire {path}: {exc}")
            continue

        obj["_source_file"] = str(path)
        entries.append(obj)

    # Tri par date_bulletin si disponible
    def sort_key(item: Dict[str, Any]):
        date_str = str(item.get("date_bulletin"))
        try:
            return datetime.fromisoformat(date_str)
        except Exception:
            return datetime.min

    entries.sort(key=sort_key)
    return entries


def main():
    if not MERGED_ROOT.exists():
        print(f"❌ Le dossier {MERGED_ROOT} est introuvable.")
        return

    entries = read_merged_files(MERGED_ROOT)
    if not entries:
        return

    payload = {
        "generated_at": datetime.utcnow().isoformat(),
        "bulletin_count": len(entries),
        "bulletins": entries,
    }

    json_blob = json.dumps(payload, ensure_ascii=False, indent=2)

    OUTPUT_FILE.write_text(json_blob, encoding="utf-8")
    print(f"✅ Fusion globale créée : {OUTPUT_FILE} ({len(entries)} bulletins)")

    DATA_DIR.mkdir(parents=True, exist_ok=True)
    DATA_OUTPUT.write_text(json_blob, encoding="utf-8")
    print(f"📂 Copie disponible dans {DATA_OUTPUT}")


if __name__ == "__main__":
    main()
