"""
Calcule des métriques (MAE, RMSE, accuracy, F1-score) à partir de all_merged.json.

Usage :
    python evaluate_forecasts.py
    python evaluate_forecasts.py --file data/all_merged.json --output data/metrics.json
"""

from __future__ import annotations

import argparse
import json
import math
from collections import Counter
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Tuple

DEFAULT_FILE = Path("data") / "all_merged.json"
DEFAULT_OUTPUT = Path("data") / "evaluation_metrics.json"


def load_payload(path: Path) -> Dict:
    if not path.exists():
        raise FileNotFoundError(f"Fichier introuvable : {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def collect_numeric_pairs(
    payload: Dict, obs_key: str, prev_key: str
) -> List[Tuple[float, float]]:
    pairs: List[Tuple[float, float]] = []
    for bulletin in payload.get("bulletins", []):
        stations = bulletin.get("stations", [])
        for station in stations:
            obs = station.get(obs_key)
            prev = station.get(prev_key)
            if obs is None or prev is None:
                continue
            try:
                obs_val = float(obs)
                prev_val = float(prev)
            except (ValueError, TypeError):
                continue
            pairs.append((obs_val, prev_val))
    return pairs


def compute_mae(values: Iterable[Tuple[float, float]]) -> Optional[float]:
    values = list(values)
    if not values:
        return None
    total = sum(abs(obs - pred) for obs, pred in values)
    return total / len(values)


def compute_rmse(values: Iterable[Tuple[float, float]]) -> Optional[float]:
    values = list(values)
    if not values:
        return None
    total = sum((obs - pred) ** 2 for obs, pred in values)
    return math.sqrt(total / len(values))


def normalize_label(label: Optional[str]) -> Optional[str]:
    if not label:
        return None
    return label.strip().lower()


def collect_labels(payload: Dict) -> List[Tuple[str, str]]:
    pairs: List[Tuple[str, str]] = []
    for bulletin in payload.get("bulletins", []):
        for station in bulletin.get("stations", []):
            obs = normalize_label(station.get("temps_obs"))
            pred = normalize_label(station.get("temps_prev"))
            if obs is None or pred is None:
                continue
            pairs.append((obs, pred))
    return pairs


def compute_accuracy(pairs: Iterable[Tuple[str, str]]) -> Optional[float]:
    pairs = list(pairs)
    if not pairs:
        return None
    correct = sum(1 for obs, pred in pairs if obs == pred)
    return correct / len(pairs)


def compute_macro_f1(pairs: Iterable[Tuple[str, str]]) -> Optional[float]:
    pairs = list(pairs)
    if not pairs:
        return None

    labels = sorted(set(obs for obs, _ in pairs) | set(pred for _, pred in pairs))
    if not labels:
        return None

    f1_scores: List[float] = []
    for label in labels:
        tp = sum(1 for obs, pred in pairs if obs == label and pred == label)
        fp = sum(1 for obs, pred in pairs if obs != label and pred == label)
        fn = sum(1 for obs, pred in pairs if obs == label and pred != label)

        if tp == 0 and fp == 0 and fn == 0:
            continue

        precision = tp / (tp + fp) if (tp + fp) > 0 else 0.0
        recall = tp / (tp + fn) if (tp + fn) > 0 else 0.0

        if precision + recall == 0:
            f1 = 0.0
        else:
            f1 = 2 * precision * recall / (precision + recall)
        f1_scores.append(f1)

    if not f1_scores:
        return None
    return sum(f1_scores) / len(f1_scores)


def main():
    parser = argparse.ArgumentParser(
        description="Calcule les métriques (MAE, RMSE, Accuracy, F1) à partir de all_merged.json."
    )
    parser.add_argument(
        "--file",
        type=Path,
        default=DEFAULT_FILE,
        help="Chemin vers all_merged.json (par défaut data/all_merged.json).",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=DEFAULT_OUTPUT,
        help="Chemin de sortie du rapport JSON (par défaut data/evaluation_metrics.json).",
    )
    args = parser.parse_args()

    payload = load_payload(args.file)

    tmin_pairs = collect_numeric_pairs(payload, "Tmin_obs", "Tmin_prev")
    tmax_pairs = collect_numeric_pairs(payload, "Tmax_obs", "Tmax_prev")
    icon_pairs = collect_labels(payload)

    results = {
        "file": str(args.file),
        "total_bulletins": len(payload.get("bulletins", [])),
        "pairs_tmin": len(tmin_pairs),
        "pairs_tmax": len(tmax_pairs),
        "pairs_icons": len(icon_pairs),
        "Tmin_MAE": compute_mae(tmin_pairs),
        "Tmin_RMSE": compute_rmse(tmin_pairs),
        "Tmax_MAE": compute_mae(tmax_pairs),
        "Tmax_RMSE": compute_rmse(tmax_pairs),
        "Icon_accuracy": compute_accuracy(icon_pairs),
        "Icon_macro_F1": compute_macro_f1(icon_pairs),
    }

    output_path = args.output
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding="utf-8")
    print(f"✅ Rapport de métriques écrit dans {output_path}")


if __name__ == "__main__":
    main()
