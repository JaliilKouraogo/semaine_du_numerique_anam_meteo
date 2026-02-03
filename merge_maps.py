import json
import os
from pathlib import Path

# ---------- CONFIG ----------
CITIES_REL_FILE    = "cities_rel_with_coords.json"   # doit contenir name + latitude + longitude
INPUT_ROOT         = Path("2024_temps_qwen")         # là où sont les JSON map1_observed / map2_forecast
OUTPUT_MERGED_ROOT = Path("2024_temps_merged")       # là où on écrit les JSON fusionnés
os.makedirs(OUTPUT_MERGED_ROOT, exist_ok=True)


# ---------- Charger les infos villes (lat/lon) ----------
def load_cities_meta():
    with open(CITIES_REL_FILE, "r", encoding="utf-8") as f:
        cities = json.load(f)
    by_name = {}
    for c in cities:
        name = c.get("name")
        if not name:
            continue
        key = name.strip().upper()
        by_name[key] = c
    return by_name


# ---------- Fusionner les stations pour UNE paire (obs/prev) ----------
def merge_stations_for_pair(date_bulletin, data_obs, data_prev, cities_meta):
    """
    data_obs : dict JSON pour map1_observed (peut être None)
    data_prev: dict JSON pour map2_forecast (peut être None)
    cities_meta : dict name_upper -> meta (lat/lon, etc.)

    On suppose que chaque station dans data_obs/data_prev peut contenir:
      - "nom"
      - "tmin", "tmax"
      - "weather_icon"  -> qu'on mappe vers temps_obs / temps_prev
    """
    stations_obs = data_obs.get("stations", []) if data_obs else []
    stations_prev = data_prev.get("stations", []) if data_prev else []

    # indexation par nom (normalisé)
    obs_by_name = {}
    for s in stations_obs:
        nom = s.get("nom")
        if not isinstance(nom, str):
            continue
        key = nom.strip().upper()
        obs_by_name[key] = s

    prev_by_name = {}
    for s in stations_prev:
        nom = s.get("nom")
        if not isinstance(nom, str):
            continue
        key = nom.strip().upper()
        prev_by_name[key] = s

    # union de tous les noms
    all_names_keys = set(obs_by_name.keys()) | set(prev_by_name.keys())

    merged_stations = []

    for key in sorted(all_names_keys):
        # nom "propre"
        if key in obs_by_name and isinstance(obs_by_name[key].get("nom"), str):
            base_name = obs_by_name[key]["nom"].strip()
        elif key in prev_by_name and isinstance(prev_by_name[key].get("nom"), str):
            base_name = prev_by_name[key]["nom"].strip()
        else:
            base_name = key

        obs = obs_by_name.get(key)
        prev = prev_by_name.get(key)

        # Tmin/Tmax observed (map1)
        tmin_obs = obs.get("tmin") if obs else None
        tmax_obs = obs.get("tmax") if obs else None

        # Tmin/Tmax forecast (map2)
        tmin_prev = prev.get("tmin") if prev else None
        tmax_prev = prev.get("tmax") if prev else None

        # 🔥 Récupérer weather_icon -> temps_obs / temps_prev
        temps_obs = obs.get("weather_icon") if obs else None
        temps_prev = prev.get("weather_icon") if prev else None

        # lat/lon
        meta = cities_meta.get(key, {})
        lat = meta.get("lat") or meta.get("latitude")
        lon = meta.get("lon") or meta.get("longitude") or meta.get("lng")

        merged_stations.append({
            "nom": base_name,
            "latitude": lat,
            "longitude": lon,

            "Tmin_obs": tmin_obs,
            "Tmax_obs": tmax_obs,
            "temps_obs": temps_obs or "",   # si None -> ""

            "Tmin_prev": tmin_prev,
            "Tmax_prev": tmax_prev,
            "temps_prev": temps_prev or "",  # si None -> ""

            "interpretation_moore": "",
            "interpretation_dioula": ""
        })

    merged_obj = {
        "date_bulletin": date_bulletin,
        "stations": merged_stations
    }
    return merged_obj


def main():
    cities_meta = load_cities_meta()

    # On boucle sur tous les fichiers *_map1_observed.json
    obs_files = list(INPUT_ROOT.rglob("*_map1_observed.json"))
    if not obs_files:
        print("⚠ Aucun fichier *_map1_observed.json trouvé dans", INPUT_ROOT)
        return

    for obs_path in obs_files:
        stem = obs_path.stem  # sans extension .json
        if "_map1_observed" not in stem:
            continue

        base_id = stem.replace("_map1_observed", "")
        rel_dir = obs_path.parent.relative_to(INPUT_ROOT)

        # Fichier forecast correspondant dans le même dossier
        prev_path = obs_path.parent / f"{base_id}_map2_forecast.json"

        # Charger observed
        try:
            with open(obs_path, "r", encoding="utf-8") as f:
                data_obs = json.load(f)
        except Exception as e:
            print(f"⚠ Impossible de lire observed {obs_path}: {e}")
            continue

        # Charger forecast si existe
        data_prev = None
        if prev_path.exists():
            try:
                with open(prev_path, "r", encoding="utf-8") as f:
                    data_prev = json.load(f)
            except Exception as e:
                print(f"⚠ Impossible de lire forecast {prev_path}: {e}")
        else:
            print(f"⚠ Aucun fichier forecast correspondant pour {obs_path.name}")

        # Récupérer la date_bulletin
        date_bulletin = (
            data_obs.get("date_bulletin")
            or (data_prev.get("date_bulletin") if data_prev else None)
        )
        if not date_bulletin:
            print(f"⚠ Pas de date_bulletin pour {obs_path}, on skip.")
            continue

        print(f"\n=== Fusion pour {base_id} (date={date_bulletin}, dossier={rel_dir}) ===")

        merged = merge_stations_for_pair(date_bulletin, data_obs, data_prev, cities_meta)

        # Dossier de sortie identique à la structure d'entrée (ex: MAI)
        out_dir = OUTPUT_MERGED_ROOT / rel_dir
        os.makedirs(out_dir, exist_ok=True)

        # Nom de fichier fusionné
        out_file = out_dir / f"{base_id}_merged.json"

        with open(out_file, "w", encoding="utf-8") as f:
            json.dump(merged, f, ensure_ascii=False, indent=2)

        print(f"  ✅ Fusion sauvegardée -> {out_file}")


if __name__ == "__main__":
    main()
