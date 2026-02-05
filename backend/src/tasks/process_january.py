
import pandas as pd
import json
from pathlib import Path
import sys
import os

# Set up paths
BASE_DIR = Path(__file__).resolve().parent.parent.parent.parent
sys.path.append(str(BASE_DIR / "backend" / "src"))

from engine import recognize_icons

# Configuration
EXCEL_FILE = BASE_DIR / "backend" / "data" / "Saisie_Data_evaluation_prevision_2023.xlsx"
MAPS_DIR = BASE_DIR / "2023_maps_extracted" / "Janvier"
OUTPUT_REPORT = BASE_DIR / "january_test_report.json"

def load_ground_truth_january(excel_path):
    print(f"📖 Reading Excel for January 2023...")
    df = pd.read_excel(excel_path, sheet_name='Data_evaluation_prevision_2023')
    # Filter for Jan 2023
    jan_data = df[(df['ANNEE'] == 2023) & (df['MOIS'].str.strip() == 'Janvier')]
    
    truth = {}
    for _, row in jan_data.iterrows():
        try:
            day = int(row['JOUR'])
            city = str(row['LOCALITES']).strip().upper()
            obs = str(row['OBSERVATIONS']).strip().upper()
            if day not in truth: truth[day] = {}
            truth[day][city] = obs
        except: continue
    return truth

def find_map_file(day, maps_dir):
    patterns = [f"* {day:02d} Janvier *map1.png", f"* {day} Janvier *map1.png"]
    for p in patterns:
        matches = list(maps_dir.glob(p))
        if matches: return matches[0]
    return None

def unify_code(c):
    c = str(c).upper()
    if any(x in c for x in ["TS", "RA", "ORAGE", "PLUIE"]): return "TSRA"
    if any(x in c for x in ["DU", "FU", "POUSSIERE", "SABLE", "BRUME"]): return "DUFU"
    return "NSW"

def run_test():
    truth = load_ground_truth_january(EXCEL_FILE)
    if not truth:
        print("❌ No data found for January.")
        return

    results = []
    total_correct = 0
    total_compared = 0

    print("\n🚀 Starting AI processing for January maps...")
    
    # Process only the first 5 days for the test as requested
    sample_days = sorted(truth.keys())[:5]
    
    for day in sample_days:
        map_path = find_map_file(day, MAPS_DIR)
        if not map_path:
            print(f"⚠️ Map not found for day {day}")
            continue
            
        print(f"  [AI] Processing Day {day}: {map_path.name}")
        predictions = recognize_icons(map_path)
        
        day_truth = truth[day]
        for city, true_obs in day_truth.items():
            mapped_city = city
            if city == "FADA" and "FADA NGOURMA" in predictions: mapped_city = "FADA NGOURMA"
            if city == "BOBO" and "BOBO DIOULASSO" in predictions: mapped_city = "BOBO DIOULASSO"
            
            if mapped_city not in predictions: continue
            
            p_code = unify_code(predictions[mapped_city])
            t_code = unify_code(true_obs)
            
            is_correct = (p_code == t_code)
            if is_correct: total_correct += 1
            total_compared += 1
            
            results.append({
                "day": day,
                "city": city,
                "predicted": p_code,
                "truth": t_code,
                "correct": is_correct
            })

    accuracy = (total_correct / total_compared * 100) if total_compared > 0 else 0
    print(f"\n✅ January Test Result: {accuracy:.2f}% ({total_correct}/{total_compared})")
    
    report = {
        "month": "January 2023",
        "sample_size_days": len(sample_days),
        "accuracy": accuracy,
        "total_compared": total_compared,
        "total_correct": total_correct,
        "details": results
    }
    
    with open(OUTPUT_REPORT, "w", encoding="utf-8") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)
    print(f"💾 Report saved to {OUTPUT_REPORT}")

if __name__ == "__main__":
    run_test()
