"""
calibrate_icon_zones.py - Outil de Calibration des Zones d'Icônes

Ce script permet de:
1. Ouvrir une carte exemple
2. Cliquer pour définir la zone de l'icône pour chaque ville
3. Découper automatiquement la légende en bas de la carte
4. Sauvegarder les coordonnées pour utilisation avec Qwen

Usage:
    python calibrate_icon_zones.py --map 2023_maps/JUILLET/Bulletin_du_01_Juillet_2023_a_12h00_page1_map1.png
    python calibrate_icon_zones.py --map 2023_maps/Mars/Bulletin_du_01_Mars_2023_a_12h00_page1_map1.png

Contrôles:
- Clic gauche: Définir le centre de la zone d'icône pour la ville actuelle
- 'n': Passer à la ville suivante
- 'p': Revenir à la ville précédente
- 's': Sauvegarder les coordonnées
- 'l': Découper et sauvegarder la légende
- 'q': Quitter
- '+'/'-': Augmenter/diminuer la taille de la zone
"""

import cv2
import json
import numpy as np
from pathlib import Path
import argparse

# ---------- CONFIG ----------
CITIES_REL_FILE = "cities_rel.json"
ICON_ZONES_FILE = "icon_zones.json"
LEGEND_OUTPUT = "extracted_legend.png"

# Villes cibles
TARGET_CITIES = [
    "DORI", "OUAHIGOUYA", "OUAGADOUGOU", "BOGANDE", "DEDOUGOU",
    "FADA NGOURMA", "BOBO DIOULASSO", "BOROMO", "PO", "GAOUA"
]

# Variables globales pour le callback de souris
current_city_idx = 0
icon_zones = {}
zone_size = 40  # Taille par défaut de la zone d'icône
img_display = None
img_original = None
legend_rect = None  # Pour la légende


def load_cities_rel():
    """Charge les coordonnées relatives des villes."""
    if Path(CITIES_REL_FILE).exists():
        with open(CITIES_REL_FILE, "r", encoding="utf-8") as f:
            all_cities = json.load(f)
        return [c for c in all_cities if c["name"] in TARGET_CITIES]
    return []


def mouse_callback(event, x, y, flags, param):
    """Callback pour les clics de souris."""
    global icon_zones, img_display, current_city_idx
    
    if event == cv2.EVENT_LBUTTONDOWN:
        city_name = TARGET_CITIES[current_city_idx]
        
        # Calculer les coordonnées relatives
        h, w = img_original.shape[:2]
        x_rel = x / w
        y_rel = y / h
        
        # Sauvegarder la zone
        icon_zones[city_name] = {
            "x_rel": round(x_rel, 4),
            "y_rel": round(y_rel, 4),
            "x_abs": x,
            "y_abs": y,
            "zone_size": zone_size
        }
        
        print(f"✓ {city_name}: ({x}, {y}) -> ({x_rel:.4f}, {y_rel:.4f})")
        
        # Actualiser l'affichage
        update_display()


def update_display():
    """Met à jour l'affichage avec les zones définies."""
    global img_display
    
    img_display = img_original.copy()
    h, w = img_display.shape[:2]
    
    # Dessiner toutes les zones définies
    for city, zone in icon_zones.items():
        cx = int(zone["x_rel"] * w)
        cy = int(zone["y_rel"] * h)
        size = zone.get("zone_size", zone_size)
        
        # Rectangle de la zone
        x1, y1 = cx - size, cy - size
        x2, y2 = cx + size, cy + size
        
        color = (0, 255, 0) if city == TARGET_CITIES[current_city_idx] else (255, 0, 0)
        cv2.rectangle(img_display, (x1, y1), (x2, y2), color, 2)
        cv2.putText(img_display, city[:10], (x1, y1 - 5), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
    
    # Afficher la ville courante
    city_name = TARGET_CITIES[current_city_idx]
    cv2.putText(img_display, f"Ville: {city_name} ({current_city_idx+1}/{len(TARGET_CITIES)})", 
                (10, 30), cv2.FONT_HERSHEY_SIMPLEX, 0.8, (0, 255, 255), 2)
    cv2.putText(img_display, f"Zone: {zone_size}px | +/- pour changer", 
                (10, 60), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 1)
    cv2.putText(img_display, "Clic: definir zone | n/p: nav | s: sauver | l: legende | q: quitter", 
                (10, 90), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (200, 200, 200), 1)
    
    # Dessiner la zone de légende si définie
    if legend_rect:
        x1, y1, x2, y2 = legend_rect
        cv2.rectangle(img_display, (x1, y1), (x2, y2), (255, 255, 0), 2)
        cv2.putText(img_display, "LEGENDE", (x1, y1 - 5), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.6, (255, 255, 0), 2)


def detect_legend_area(img):
    """Détecte automatiquement la zone de légende en bas de l'image."""
    h, w = img.shape[:2]
    
    # La légende est généralement dans le bas de l'image
    # On cherche une zone horizontale avec des bordures
    
    # Prendre le dernier quart de l'image
    bottom_section = img[int(h * 0.75):, :]
    
    gray = cv2.cvtColor(bottom_section, cv2.COLOR_BGR2GRAY)
    
    # Détecter les contours
    _, thresh = cv2.threshold(gray, 200, 255, cv2.THRESH_BINARY_INV)
    contours, _ = cv2.findContours(thresh, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
    
    if contours:
        # Trouver le plus grand contour horizontal
        best = None
        best_area = 0
        for cnt in contours:
            x, y, cw, ch = cv2.boundingRect(cnt)
            area = cw * ch
            # La légende est généralement large et pas très haute
            if cw > w * 0.3 and area > best_area:
                best = (x, y + int(h * 0.75), x + cw, y + int(h * 0.75) + ch)
                best_area = area
        
        return best
    
    # Par défaut, prendre les 15% du bas
    return (0, int(h * 0.85), w, h)


def extract_legend(img, output_path):
    """Extrait et sauvegarde la légende."""
    rect = detect_legend_area(img)
    if rect:
        x1, y1, x2, y2 = rect
        legend = img[y1:y2, x1:x2]
        cv2.imwrite(output_path, legend)
        print(f"✓ Légende extraite: {output_path}")
        return rect
    return None


def save_icon_zones():
    """Sauvegarde les zones d'icônes dans un fichier JSON."""
    data = {
        "zone_size_default": zone_size,
        "cities": icon_zones
    }
    
    with open(ICON_ZONES_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, ensure_ascii=False, indent=2)
    
    print(f"✓ Zones sauvegardées: {ICON_ZONES_FILE}")
    print(f"  {len(icon_zones)} villes définies")


def load_existing_zones():
    """Charge les zones existantes si le fichier existe."""
    global icon_zones, zone_size
    
    if Path(ICON_ZONES_FILE).exists():
        with open(ICON_ZONES_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
        
        icon_zones = data.get("cities", {})
        zone_size = data.get("zone_size_default", 40)
        print(f"✓ {len(icon_zones)} zones chargées depuis {ICON_ZONES_FILE}")


def main():
    global current_city_idx, zone_size, img_original, img_display, legend_rect
    
    parser = argparse.ArgumentParser(description="Calibration des zones d'icônes")
    parser.add_argument("--map", type=str, required=True, help="Chemin vers une carte exemple")
    parser.add_argument("--auto-legend", action="store_true", help="Extraire auto la légende")
    args = parser.parse_args()
    
    # Charger l'image
    map_path = Path(args.map)
    if not map_path.exists():
        print(f"❌ Fichier non trouvé: {map_path}")
        return
    
    data = np.fromfile(str(map_path), dtype=np.uint8)
    img_original = cv2.imdecode(data, cv2.IMREAD_COLOR)
    
    if img_original is None:
        print(f"❌ Impossible de lire: {map_path}")
        return
    
    print("=" * 60)
    print("🎯 CALIBRATION DES ZONES D'ICÔNES")
    print("=" * 60)
    print(f"📄 Image: {map_path}")
    print(f"📐 Taille: {img_original.shape[1]}x{img_original.shape[0]}")
    print("=" * 60)
    print("\nContrôles:")
    print("  Clic gauche: Définir la zone d'icône")
    print("  n/p: Ville suivante/précédente")
    print("  +/-: Agrandir/réduire la zone")
    print("  s: Sauvegarder")
    print("  l: Extraire la légende")
    print("  q: Quitter")
    print("=" * 60)
    
    # Charger les zones existantes
    load_existing_zones()
    
    # Extraire auto la légende si demandé
    if args.auto_legend:
        legend_rect = extract_legend(img_original, LEGEND_OUTPUT)
    
    # Initialiser l'affichage
    update_display()
    
    # Créer la fenêtre
    cv2.namedWindow("Calibration", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("Calibration", 1200, 800)
    cv2.setMouseCallback("Calibration", mouse_callback)
    
    while True:
        cv2.imshow("Calibration", img_display)
        key = cv2.waitKey(1) & 0xFF
        
        if key == ord('q'):
            break
        elif key == ord('n'):
            current_city_idx = (current_city_idx + 1) % len(TARGET_CITIES)
            print(f"→ Ville: {TARGET_CITIES[current_city_idx]}")
            update_display()
        elif key == ord('p'):
            current_city_idx = (current_city_idx - 1) % len(TARGET_CITIES)
            print(f"← Ville: {TARGET_CITIES[current_city_idx]}")
            update_display()
        elif key == ord('s'):
            save_icon_zones()
        elif key == ord('l'):
            legend_rect = extract_legend(img_original, LEGEND_OUTPUT)
            update_display()
        elif key == ord('+') or key == ord('='):
            zone_size += 5
            print(f"Zone: {zone_size}px")
            update_display()
        elif key == ord('-'):
            zone_size = max(10, zone_size - 5)
            print(f"Zone: {zone_size}px")
            update_display()
    
    cv2.destroyAllWindows()
    
    # Sauvegarder automatiquement à la fin
    if icon_zones:
        save_icon_zones()


if __name__ == "__main__":
    main()
