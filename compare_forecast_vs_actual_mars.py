
import json
import os
from pathlib import Path

# Configuration
DATA_DIR = Path(r"c:\Users\koura\Downloads\semaine_du_numerique_anam_meteo-main\semaine_du_numerique_anam_meteo-main\2023_temps_specific\Mars")
OUTPUT_FILE = Path(r"c:\Users\koura\Downloads\semaine_du_numerique_anam_meteo-main\semaine_du_numerique_anam_meteo-main\comparison_forecast_actual_mars.json")

def load_json(path):
    if not path.exists():
        return None
    with open(path, 'r', encoding='utf-8') as f:
        return json.load(f)

def get_file_path(day, map_type):
    # Handle "1er" for the first day
    day_str = "1er" if day == 1 else f"{day:02d}"
    filename = f"Bulletin_du_{day_str}_Mars_2023_a_12h00_page1_map{map_type}.json"
    
    # map_type 1 is observed, map_type 2 is forecast
    suffix = "observed" if map_type == 1 else "forecast"
    actual_filename = f"Bulletin_du_{day_str}_Mars_2023_a_12h00_page1_map{map_type}_{suffix}.json"
    return DATA_DIR / actual_filename

def compare():
    results_by_city = {}
    
    for day in range(2, 32):
        prev_day = day - 1
        forecast_file = get_file_path(prev_day, 2)
        actual_file = get_file_path(day, 1)
        
        forecast_data = load_json(forecast_file)
        actual_data = load_json(actual_file)
        
        if not forecast_data or not actual_data:
            continue
            
        f_map = {s.get('nom', 'UNKNOWN').upper(): s for s in forecast_data.get('stations', [])}
        a_map = {s.get('nom', 'UNKNOWN').upper(): s for s in actual_data.get('stations', [])}
        
        for city_name in f_map:
            if city_name in a_map:
                f_station = f_map[city_name]
                a_station = a_map[city_name]
                
                def normalize(code):
                    code = str(code).upper()
                    if any(x in code for x in ["TS", "RA", "ORAGE", "PLUIE"]): return "TSRA"
                    if any(x in code for x in ["DU", "FU", "POUSSIERE", "SABLE"]): return "DUFU"
                    return "NSW"

                f_icon = normalize(f_station.get('icon_code', 'NSW'))
                a_icon = normalize(a_station.get('icon_code', 'NSW'))
                
                f_tmin = f_station.get('tmin')
                f_tmax = f_station.get('tmax')
                a_tmin = a_station.get('tmin')
                a_tmax = a_station.get('tmax')
                
                comparison = {
                    "date_observation_JJ": f"{day:02d}/03/2023",
                    "date_prevision_JJ-1": f"{prev_day:02d}/03/2023",
                    "meteo": {
                        "prevision_JJ-1": f_icon,
                        "observation_JJ": a_icon,
                        "correct": (f_icon == a_icon)
                    },
                    "tmin": {
                        "prevision_JJ-1": f_tmin,
                        "observation_JJ": a_tmin,
                        "correct": (f_tmin == a_tmin)
                    },
                    "tmax": {
                        "prevision_JJ-1": f_tmax,
                        "observation_JJ": a_tmax,
                        "correct": (f_tmax == a_tmax)
                    }
                }
                
                if city_name not in results_by_city:
                    results_by_city[city_name] = []
                results_by_city[city_name].append(comparison)

    with open(OUTPUT_FILE, "w", encoding="utf-8") as f:
        json.dump(results_by_city, f, indent=4, ensure_ascii=False)
    
    print(f"\n✅ Comparaison terminée pour MARS par VILLE. Résultats sauvegardés dans {OUTPUT_FILE}")

    # Stats calculation
    stats = {"meteo": 0, "tmin": 0, "tmax": 0, "total": 0}
    for city in results_by_city:
        for comp in results_by_city[city]:
            stats["total"] += 1
            if comp["meteo"]["correct"]: stats["meteo"] += 1
            if comp["tmin"]["correct"]: stats["tmin"] += 1
            if comp["tmax"]["correct"]: stats["tmax"] += 1
            
    if stats["total"] > 0:
        print("\n--- Statistiques de Performance Mars 2023 ---")
        print(f"Précision Icônes (JJ-1 vs JJ) : {stats['meteo']/stats['total']*100:.2f}%")
        print(f"Précision Tmin (JJ-1 vs JJ)   : {stats['tmin']/stats['total']*100:.2f}%")
        print(f"Précision Tmax (JJ-1 vs JJ)   : {stats['tmax']/stats['total']*100:.2f}%")

if __name__ == "__main__":
    compare()
