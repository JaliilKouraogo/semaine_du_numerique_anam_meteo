"""
calibrate_legend.py - Outil de Calibration de la Légende (v2)

Ce script permet de:
1. Ouvrir une carte exemple
2. Sélectionner visuellement la zone de la légende
3. Choisir le nombre d'icônes (4-7)
4. Extraire chaque icône + lire le nom français avec Qwen
5. Sauvegarder les coordonnées et noms pour utilisation ultérieure

Usage:
    python calibrate_legend.py --map "2023_maps/JUILLET/Bulletin_du_01_Juillet_2023_a_12h00_page1_map1.png"

Contrôles:
- Clic gauche + drag: Sélectionner la zone de légende
- 4/5/6/7: Définir le nombre d'icônes
- 'e': Extraire les icônes et lire les noms avec Qwen
- 's': Sauvegarder la configuration
- 'r': Réinitialiser la sélection
- 'q': Quitter
"""

import cv2
import json
import numpy as np
from pathlib import Path
import argparse
import os
import base64
import requests
import re

# ---------- CONFIG ----------
LEGEND_CONFIG_FILE = "legend_config.json"
LEGEND_ICONS_DIR = Path("legend_extracted")
OLLAMA_URL = "http://localhost:11434/api/generate"
DEFAULT_MODEL = "qwen3-vl:8b"
TIMEOUT_SECONDS = 60

# Variables globales
drawing = False
start_point = None
end_point = None
legend_rect = None
img_display = None
img_original = None
extracted_icons = []
num_icons = 6  # Nombre d'icônes par défaut


def image_to_base64(img):
    """Convertit une image OpenCV en base64."""
    ok, buf = cv2.imencode(".png", img)
    if ok:
        return base64.b64encode(buf.tobytes()).decode("ascii")
    return ""


def read_text_with_qwen(text_img, model=DEFAULT_MODEL):
    """Utilise Qwen pour lire le texte français sous une icône."""
    img_b64 = image_to_base64(text_img)
    
    prompt = """Read the French text in this image.
The text describes a weather condition.
Reply with ONLY the text, nothing else.

Example responses:
- Temps partiellement nuageux
- Ciel nuageux
- Pluies faibles
- Orages isoles
- Pluies orageuses isolees

Text:"""

    payload = {
        "model": model,
        "prompt": prompt,
        "images": [img_b64],
        "stream": False,
    }
    
    try:
        resp = requests.post(OLLAMA_URL, json=payload, timeout=TIMEOUT_SECONDS)
        resp.raise_for_status()
        data = resp.json()
        text = data.get("response", "").strip()
        
        # Nettoyer
        if "<think>" in text:
            text = re.sub(r"<think>.*?</think>", "", text, flags=re.DOTALL).strip()
        
        # Prendre la première ligne
        result = text.split('\n')[0].strip()
        # Retirer les tirets ou bullets au début
        result = re.sub(r'^[-•]\s*', '', result)
        
        return result
        
    except Exception as e:
        print(f"      [ERROR OCR]: {str(e)[:40]}")
    
    return ""


def mouse_callback(event, x, y, flags, param):
    """Callback pour les clics de souris."""
    global drawing, start_point, end_point, legend_rect, img_display
    
    if event == cv2.EVENT_LBUTTONDOWN:
        drawing = True
        start_point = (x, y)
        end_point = (x, y)
    
    elif event == cv2.EVENT_MOUSEMOVE:
        if drawing:
            end_point = (x, y)
            update_display()
    
    elif event == cv2.EVENT_LBUTTONUP:
        drawing = False
        end_point = (x, y)
        
        # Normaliser les coordonnées
        x1 = min(start_point[0], end_point[0])
        y1 = min(start_point[1], end_point[1])
        x2 = max(start_point[0], end_point[0])
        y2 = max(start_point[1], end_point[1])
        
        if x2 - x1 > 10 and y2 - y1 > 10:  # Taille minimale
            legend_rect = (x1, y1, x2, y2)
            print(f"✓ Légende sélectionnée: ({x1}, {y1}) -> ({x2}, {y2})")
            print(f"  Taille: {x2-x1}x{y2-y1} px")
        
        update_display()


def update_display():
    """Met à jour l'affichage."""
    global img_display
    
    img_display = img_original.copy()
    
    # Dessiner le rectangle en cours de sélection
    if drawing and start_point and end_point:
        cv2.rectangle(img_display, start_point, end_point, (0, 255, 0), 2)
    
    # Dessiner la légende sélectionnée
    if legend_rect:
        x1, y1, x2, y2 = legend_rect
        cv2.rectangle(img_display, (x1, y1), (x2, y2), (0, 255, 255), 3)
        cv2.putText(img_display, f"LEGENDE ({num_icons} icones)", (x1, y1 - 10), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.7, (0, 255, 255), 2)
    
    # Dessiner les icônes extraites
    for i, icon_info in enumerate(extracted_icons):
        x, y, w, h = icon_info["rect"]
        cv2.rectangle(img_display, (x, y), (x+w, y+h), (255, 0, 0), 2)
        name_short = icon_info.get("name", "")[:15]
        cv2.putText(img_display, f"{i+1}: {name_short}", (x, y - 5), 
                    cv2.FONT_HERSHEY_SIMPLEX, 0.4, (255, 0, 0), 1)
    
    # Instructions
    cv2.putText(img_display, f"Drag: Selectionner | 4-7: Nb icones ({num_icons}) | e: Extraire | s: Sauver | q: Quitter", 
                (10, 25), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 1)


def extract_icons_from_legend():
    """Extrait les icônes individuelles et lit les noms avec Qwen."""
    global extracted_icons
    
    if legend_rect is None:
        print("⚠️ Sélectionnez d'abord la zone de légende")
        return
    
    x1, y1, x2, y2 = legend_rect
    legend_img = img_original[y1:y2, x1:x2]
    
    # Sauvegarder la légende complète
    os.makedirs(LEGEND_ICONS_DIR, exist_ok=True)
    legend_path = LEGEND_ICONS_DIR / "legend_full.png"
    cv2.imwrite(str(legend_path), legend_img)
    print(f"✓ Légende sauvegardée: {legend_path}")
    
    h, w = legend_img.shape[:2]
    col_width = w // num_icons
    
    extracted_icons = []
    
    print(f"\n📊 Extraction de {num_icons} icônes...")
    
    for i in range(num_icons):
        icon_x = i * col_width
        icon_w = col_width
        
        # Zone de l'icône (partie supérieure - 55%)
        icon_h_ratio = 0.55
        icon_region = legend_img[0:int(h * icon_h_ratio), icon_x:icon_x + icon_w]
        
        # Sauvegarder l'icône
        icon_path = LEGEND_ICONS_DIR / f"icon_{i+1:02d}.png"
        cv2.imwrite(str(icon_path), icon_region)
        
        # Zone du texte (partie inférieure - 45%)
        text_region = legend_img[int(h * icon_h_ratio):h, icon_x:icon_x + icon_w]
        text_path = LEGEND_ICONS_DIR / f"text_{i+1:02d}.png"
        cv2.imwrite(str(text_path), text_region)
        
        # Lire le nom avec Qwen
        print(f"   📖 Lecture icône {i+1}...", end=" ", flush=True)
        name = read_text_with_qwen(text_region)
        if name:
            print(f"-> {name}")
        else:
            print("-> (non lu)")
            name = f"Icone {i+1}"
        
        extracted_icons.append({
            "index": i + 1,
            "rect": (x1 + icon_x, y1, icon_w, int(h * icon_h_ratio)),
            "icon_path": str(icon_path),
            "text_path": str(text_path),
            "name": name
        })
    
    print(f"\n✓ {len(extracted_icons)} icônes extraites dans {LEGEND_ICONS_DIR}/")
    update_display()


def save_config():
    """Sauvegarde la configuration de la légende."""
    if legend_rect is None:
        print("⚠️ Pas de légende sélectionnée")
        return
    
    h, w = img_original.shape[:2]
    x1, y1, x2, y2 = legend_rect
    
    config = {
        "legend_rect_abs": legend_rect,
        "legend_rect_rel": {
            "x1_rel": round(x1 / w, 4),
            "y1_rel": round(y1 / h, 4),
            "x2_rel": round(x2 / w, 4),
            "y2_rel": round(y2 / h, 4)
        },
        "image_size": [w, h],
        "num_icons": num_icons,
        "icons": []
    }
    
    for icon in extracted_icons:
        icon_data = {
            "index": icon["index"],
            "name": icon["name"],
            "icon_path": icon["icon_path"],
            "text_path": icon["text_path"]
        }
        config["icons"].append(icon_data)
    
    with open(LEGEND_CONFIG_FILE, "w", encoding="utf-8") as f:
        json.dump(config, f, ensure_ascii=False, indent=2)
    
    print(f"\n✓ Configuration sauvegardée: {LEGEND_CONFIG_FILE}")
    print(f"  Icônes: {[i['name'] for i in extracted_icons]}")


def main():
    global img_original, img_display, legend_rect, num_icons
    
    parser = argparse.ArgumentParser(description="Calibration de la légende")
    parser.add_argument("--map", type=str, required=True, help="Chemin vers une carte exemple")
    parser.add_argument("--model", type=str, default=DEFAULT_MODEL, help="Modèle Qwen")
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
    print("🎯 CALIBRATION DE LA LÉGENDE (v2)")
    print("=" * 60)
    print(f"📄 Image: {map_path}")
    print(f"📐 Taille: {img_original.shape[1]}x{img_original.shape[0]}")
    print(f"🤖 Modèle: {args.model}")
    print("=" * 60)
    print("\nContrôles:")
    print("  Clic + drag: Sélectionner la zone de légende")
    print("  4/5/6/7: Changer le nombre d'icônes")
    print("  e: Extraire les icônes + lire noms")
    print("  s: Sauvegarder")
    print("  r: Réinitialiser")
    print("  q: Quitter")
    print("=" * 60)
    
    # Charger config existante si présente
    if Path(LEGEND_CONFIG_FILE).exists():
        with open(LEGEND_CONFIG_FILE, "r", encoding="utf-8") as f:
            config = json.load(f)
        if "legend_rect_abs" in config:
            legend_rect = tuple(config.get("legend_rect_abs", []))
            num_icons = config.get("num_icons", 6)
            print(f"✓ Configuration existante chargée ({num_icons} icônes)")
    
    # Initialiser l'affichage
    update_display()
    
    # Créer la fenêtre
    cv2.namedWindow("Calibration Legende", cv2.WINDOW_NORMAL)
    cv2.resizeWindow("Calibration Legende", 1200, 800)
    cv2.setMouseCallback("Calibration Legende", mouse_callback)
    
    while True:
        cv2.imshow("Calibration Legende", img_display)
        key = cv2.waitKey(1) & 0xFF
        
        if key == ord('q'):
            break
        elif key == ord('e'):
            extract_icons_from_legend()
        elif key == ord('s'):
            save_config()
        elif key == ord('r'):
            legend_rect = None
            extracted_icons.clear()
            print("✓ Réinitialisé")
            update_display()
        elif key in [ord('4'), ord('5'), ord('6'), ord('7')]:
            num_icons = int(chr(key))
            print(f"✓ Nombre d'icônes: {num_icons}")
            update_display()
    
    cv2.destroyAllWindows()


if __name__ == "__main__":
    main()
