"""
Automatise l’exécution complète du pipeline (scraper -> OCR -> fusion)
et importe automatiquement les JSON fusionnés dans l’API FastAPI.

Usage basique :
    python automate_pipeline.py --api-url http://127.0.0.1:8000

Options utiles :
    --skip-scraper       : saute meteo_scraper.py (si les PDF sont déjà prêts)
    --skip-convert       : saute pdf_to_images_recursive.py
    --skip-crop          : saute crop_map_from_page.py
    --skip-extract       : saute extract_temps_qwen.py
    --skip-merge         : saute merge_maps.py
    --force-reimport     : réimporte tous les JSON fusionnés (replace_existing=True)
"""

from __future__ import annotations

import argparse
import json
import subprocess
import sys
from pathlib import Path
from typing import Iterable, List, Sequence, Set

import requests

ROOT = Path(__file__).resolve().parent
MERGED_ROOT = ROOT / "2024_temps_merged"
DATA_DIR = ROOT / "data"
DATA_DIR.mkdir(exist_ok=True)
IMPORT_LOG = DATA_DIR / "imported_files.log"

# Commandes à exécuter dans l’ordre
PIPELINE_STEPS = [
    ("scraper", ["python", "meteo_scraper.py"]),
    ("convert", ["python", "pdf_to_images_recursive.py"]),
    ("crop", ["python", "crop_map_from_page.py"]),
    ("extract", ["python", "extract_temps_qwen.py"]),
    ("merge", ["python", "merge_maps.py"]),
]


def run_command(cmd: Sequence[str], cwd: Path) -> None:
    """Exécute une commande en affichant le flux stdout/stderr."""
    print(f"\n=== Exécution : {' '.join(cmd)} ===")
    try:
        subprocess.run(cmd, cwd=str(cwd), check=True)
    except subprocess.CalledProcessError as exc:
        print(f"❌ Commande échouée : {cmd} (code={exc.returncode})")
        sys.exit(exc.returncode)


def iter_merged_files(root: Path) -> Iterable[Path]:
    if not root.exists():
        return []
    return sorted(root.rglob("*_merged.json"))


def load_import_log(path: Path) -> Set[str]:
    if not path.exists():
        return set()
    return {line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()}


def append_import_log(path: Path, entries: List[str]) -> None:
    if not entries:
        return
    with path.open("a", encoding="utf-8") as fh:
        for entry in entries:
            fh.write(entry + "\n")


def import_into_api(
    json_path: Path,
    api_url: str,
    replace_existing: bool,
) -> bool:
    payload = json.loads(json_path.read_text(encoding="utf-8"))
    if replace_existing:
        payload["replace_existing"] = True
    print(f"→ Import API : {json_path}")
    resp = requests.post(
        f"{api_url.rstrip('/')}/bulletins/import",
        json=payload,
        timeout=120,
    )
    if resp.status_code >= 400:
        print(f"⚠️  Import échoué ({resp.status_code}) : {resp.text[:200]}...")
        return False
    print(f"✅ Bulletin importé ({resp.json().get('date_bulletin')})")
    return True


def main():
    parser = argparse.ArgumentParser(description="Automatisation complète du pipeline météo.")
    parser.add_argument("--api-url", default="http://127.0.0.1:8000", help="URL de base de l’API FastAPI.")
    parser.add_argument("--skip-scraper", action="store_true")
    parser.add_argument("--skip-convert", action="store_true")
    parser.add_argument("--skip-crop", action="store_true")
    parser.add_argument("--skip-extract", action="store_true")
    parser.add_argument("--skip-merge", action="store_true")
    parser.add_argument(
        "--force-reimport",
        action="store_true",
        help="Réimporte tous les JSON fusionnés (replace_existing=True).",
    )
    args = parser.parse_args()

    skip_flags = {
        "scraper": args.skip_scraper,
        "convert": args.skip_convert,
        "crop": args.skip_crop,
        "extract": args.skip_extract,
        "merge": args.skip_merge,
    }

    # 1. Exécuter chaque script dans l’ordre (sauf si skip)
    for name, command in PIPELINE_STEPS:
        if skip_flags.get(name):
            print(f"⏭  Étape sautée : {name}")
            continue
        run_command(command, ROOT)

    # 2. Importer les fichiers fusionnés
    merged_files = list(iter_merged_files(MERGED_ROOT))
    if not merged_files:
        print("⚠️  Aucun fichier *_merged.json trouvé, rien à importer.")
        return

    already_imported = load_import_log(IMPORT_LOG)
    imported_now: List[str] = []
    total_success = 0

    for merged_path in merged_files:
        key = str(merged_path.relative_to(ROOT))
        if not args.force_reimport and key in already_imported:
            print(f"⏩  Déjà importé (skip) : {key}")
            continue

        success = import_into_api(
            merged_path,
            api_url=args.api_url,
            replace_existing=args.force_reimport,
        )
        if success:
            total_success += 1
            imported_now.append(key)

    append_import_log(IMPORT_LOG, imported_now)
    print(f"\n✅ Import terminé : {total_success} bulletin(s) envoyé(s) à l’API.")
    if imported_now:
        print(f"Journal mis à jour : {IMPORT_LOG}")
    else:
        print("Aucun nouveau bulletin à importer.")


if __name__ == "__main__":
    main()
