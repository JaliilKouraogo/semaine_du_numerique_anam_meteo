"""
Nettoie les fichiers *_merged.json en supprimant les stations dont
Tmin/Tmax observed ET forecast sont totalement vides (null).

Usage :
    python clean_merged_reports.py

Options :
    --dry-run   : affiche le résultat sans réécrire les fichiers
"""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any, Dict, List

MERGED_ROOT = Path("2024_temps_merged")


def should_drop_station(station: Dict[str, Any]) -> bool:
    fields = (
        station.get("Tmin_obs"),
        station.get("Tmax_obs"),
        station.get("Tmin_prev"),
        station.get("Tmax_prev"),
    )
    return all(value is None for value in fields)


def clean_file(path: Path, dry_run: bool = False) -> int:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        print(f"❌ Impossible de parser {path}: {exc}")
        return 0

    stations = payload.get("stations", [])
    if not isinstance(stations, list):
        print(f"⚠️  Format inattendu (pas de liste 'stations') pour {path}")
        return 0

    cleaned: List[Dict[str, Any]] = []
    dropped = 0
    for st in stations:
        if should_drop_station(st):
            dropped += 1
            continue
        cleaned.append(st)

    if dropped == 0:
        return 0

    print(f"🧹 {path}: {dropped} station(s) supprimée(s)")
    payload["stations"] = cleaned

    if not dry_run:
        path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
    return dropped


def main():
    parser = argparse.ArgumentParser(
        description="Nettoie les rapports fusionnés des stations entièrement vides."
    )
    parser.add_argument("--dry-run", action="store_true", help="Affiche les suppressions sans modifier les fichiers.")
    args = parser.parse_args()

    if not MERGED_ROOT.exists():
        print(f"❌ Dossier {MERGED_ROOT} introuvable.")
        return

    total_dropped = 0
    files = sorted(MERGED_ROOT.rglob("*_merged.json"))
    if not files:
        print("⚠️  Aucun fichier *_merged.json à nettoyer.")
        return

    for json_file in files:
        total_dropped += clean_file(json_file, dry_run=args.dry_run)

    if total_dropped == 0:
        print("✅ Aucun enregistrement vide détecté.")
    else:
        if args.dry_run:
            print(f"🔎 DRY RUN terminé : {total_dropped} station(s) seraient supprimées.")
        else:
            print(f"✅ Nettoyage terminé : {total_dropped} station(s) supprimée(s).")


if __name__ == "__main__":
    main()
