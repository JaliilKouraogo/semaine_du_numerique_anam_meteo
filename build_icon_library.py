"""
build_icon_library.py - Construction automatique de la bibliothèque d'icônes

Ce script:
1. Parcourt les cartes météo
2. Extrait automatiquement la légende de chaque carte
3. Détecte le nombre d'icônes (4-7)
4. Lit les noms avec Qwen OCR
5. Accumule les icônes uniques dans une bibliothèque

La bibliothèque finale contient tous les types d'icônes possibles avec leurs noms.

Usage:
    python build_icon_library.py --maps-dir 2023_maps --limit 10
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
from datetime import datetime

# ---------- CONFIG ----------
ICON_LIBRARY_FILE = "icon_library.json"
ICON_LIBRARY_DIR = Path("icon_library")
LEGEND_CONFIG_FILE = "legend_config.json"

OLLAMA_URL = "http://localhost:11434/api/generate"
DEFAULT_MODEL = "qwen3-vl:8b"
TIMEOUT_SECONDS = 60


def image_to_base64(img):
    """Convertit une image OpenCV en base64."""
    ok, buf = cv2.imencode(".png", img)
    if ok:
        return base64.b64encode(buf.tobytes()).decode("ascii")
    return ""


def compute_image_hash(img):
    """Calcule un hash simple pour comparer les images."""
    # Redimensionner à une taille fixe
    small = cv2.resize(img, (32, 32))
    gray = cv2.cvtColor(small, cv2.COLOR_BGR2GRAY)
    # Hash basé sur les valeurs moyennes
    mean = np.mean(gray)
    return hash(tuple((gray > mean).flatten().astype(int)))


def load_legend_config():
    """Charge la configuration de la légende calibrée."""
    if Path(LEGEND_CONFIG_FILE).exists():
        with open(LEGEND_CONFIG_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return None


def extract_legend_region(img, config):
    """Extrait la zone de légende selon la config calibrée."""
    h, w = img.shape[:2]
    
    rel = config.get("legend_rect_rel", {})
    x1 = int(rel.get("x1_rel", 0.4) * w)
    y1 = int(rel.get("y1_rel", 0.8) * h)
    x2 = int(rel.get("x2_rel", 0.95) * w)
    y2 = int(rel.get("y2_rel", 0.95) * h)
    
    return img[y1:y2, x1:x2]


def detect_num_icons(legend_img):
    """
    Détecte automatiquement le nombre d'icônes dans la légende.
    Analyse les séparations verticales.
    """
    h, w = legend_img.shape[:2]
    
    # Convertir en gris
    gray = cv2.cvtColor(legend_img, cv2.COLOR_BGR2GRAY)
    
    # Chercher les lignes verticales séparant les icônes
    # Projeter verticalement
    projection = np.sum(gray, axis=0)
    
    # Normaliser
    projection = projection / np.max(projection)
    
    # Compter les pics (séparations)
    # Simple heuristique basée sur la largeur
    # Les légendes ont généralement 4-7 icônes de largeur similaire
    
    # Tester différentes divisions
    best_score = 0
    best_num = 6
    
    for num in range(4, 8):
        col_width = w // num
        # Vérifier si les colonnes ont des contenus similaires
        cols = []
        for i in range(num):
            col = legend_img[:, i*col_width:(i+1)*col_width]
            if col.size > 0:
                cols.append(np.mean(col))
        
        if len(cols) == num:
            # Vérifier la variance (colonnes similaires = bonne division)
            variance = np.var(cols) if cols else float('inf')
            score = 1.0 / (variance + 1)
            
            if score > best_score:
                best_score = score
                best_num = num
    
    return best_num


def read_text_with_qwen(text_img, model=DEFAULT_MODEL):
    """Utilise Qwen pour lire le texte français sous une icône."""
    img_b64 = image_to_base64(text_img)
    
    prompt = """Read the French text in this image.
The text describes a weather condition.
Reply with ONLY the text, nothing else.
If there are multiple lines, combine them.

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
        
        result = text.split('\n')[0].strip()
        result = re.sub(r'^[-•]\s*', '', result)
        
        return result
        
    except Exception as e:
        pass
    
    return ""


def extract_icons_from_legend(legend_img, num_icons, model):
    """Extrait les icônes individuelles et lit les noms."""
    h, w = legend_img.shape[:2]
    col_width = w // num_icons
    
    icons = []
    
    for i in range(num_icons):
        icon_x = i * col_width
        icon_w = col_width
        
        # Zone de l'icône (partie supérieure - 55%)
        icon_h_ratio = 0.55
        icon_region = legend_img[0:int(h * icon_h_ratio), icon_x:icon_x + icon_w]
        
        # Zone du texte (partie inférieure)
        text_region = legend_img[int(h * icon_h_ratio):h, icon_x:icon_x + icon_w]
        
        # Lire le nom
        name = read_text_with_qwen(text_region, model)
        
        if not name or len(name) < 3:
            name = f"Icone_{i+1}"
        
        # Hash pour identifier l'icône
        icon_hash = compute_image_hash(icon_region)
        
        icons.append({
            "name": name,
            "hash": icon_hash,
            "icon_img": icon_region,
            "text_img": text_region
        })
    
    return icons


def load_icon_library():
    """Charge la bibliothèque d'icônes existante."""
    if Path(ICON_LIBRARY_FILE).exists():
        with open(ICON_LIBRARY_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    return {"icons": [], "last_updated": None}


def save_icon_library(library):
    """Sauvegarde la bibliothèque d'icônes."""
    library["last_updated"] = datetime.now().isoformat()
    
    with open(ICON_LIBRARY_FILE, "w", encoding="utf-8") as f:
        json.dump(library, f, ensure_ascii=False, indent=2)


def is_icon_in_library(library, icon_name):
    """Vérifie si une icône avec ce nom existe déjà."""
    name_lower = icon_name.lower().strip()
    
    for existing in library["icons"]:
        existing_lower = existing["name"].lower().strip()
        # Comparaison flexible
        if name_lower == existing_lower:
            return True
        # Noms similaires (pour variations mineures)
        if name_lower in existing_lower or existing_lower in name_lower:
            if len(name_lower) > 5 and len(existing_lower) > 5:
                return True
    
    return False


def add_icon_to_library(library, icon_name, icon_img, source_file):
    """Ajoute une nouvelle icône à la bibliothèque."""
    # Créer le dossier
    os.makedirs(ICON_LIBRARY_DIR, exist_ok=True)
    
    # Nom de fichier sûr
    safe_name = re.sub(r'[^\w\s-]', '', icon_name)[:30].strip().replace(' ', '_')
    idx = len(library["icons"]) + 1
    filename = f"icon_{idx:03d}_{safe_name}.png"
    filepath = ICON_LIBRARY_DIR / filename
    
    # Sauvegarder l'image
    cv2.imwrite(str(filepath), icon_img)
    
    # Ajouter à la bibliothèque
    library["icons"].append({
        "index": idx,
        "name": icon_name,
        "image_path": str(filepath),
        "source_file": source_file
    })
    
    return idx


def process_map(map_path, legend_config, model, library):
    """Traite une carte et extrait ses icônes."""
    print(f"\n📄 {map_path.name}")
    
    # Charger l'image
    try:
        data = np.fromfile(str(map_path), dtype=np.uint8)
        img = cv2.imdecode(data, cv2.IMREAD_COLOR)
    except Exception as e:
        print(f"   ❌ Erreur: {e}")
        return 0
    
    if img is None:
        return 0
    
    # Extraire la légende
    legend_img = extract_legend_region(img, legend_config)
    
    if legend_img.size == 0:
        print(f"   ❌ Légende vide")
        return 0
    
    # Détecter le nombre d'icônes
    num_icons = detect_num_icons(legend_img)
    print(f"   📊 {num_icons} icônes détectées")
    
    # Extraire les icônes et lire les noms
    icons = extract_icons_from_legend(legend_img, num_icons, model)
    
    added = 0
    for icon in icons:
        name = icon["name"]
        
        if not is_icon_in_library(library, name):
            idx = add_icon_to_library(library, name, icon["icon_img"], str(map_path))
            print(f"   ✓ NOUVEAU: {name}")
            added += 1
        else:
            print(f"   · Existe: {name}")
    
    return added


def main():
    parser = argparse.ArgumentParser(description="Construction de la bibliothèque d'icônes")
    parser.add_argument("--maps-dir", type=Path, default=Path("2023_maps"))
    parser.add_argument("--model", type=str, default=DEFAULT_MODEL)
    parser.add_argument("--limit", type=int, default=0)
    args = parser.parse_args()
    
    print("=" * 60)
    print("🎯 CONSTRUCTION DE LA BIBLIOTHÈQUE D'ICÔNES")
    print("=" * 60)
    
    # Charger la config de légende
    legend_config = load_legend_config()
    if not legend_config:
        print("❌ Pas de configuration de légende trouvée!")
        print("   Exécutez d'abord: python calibrate_legend.py --map <carte>")
        return
    
    print(f"✓ Configuration légende chargée")
    
    # Charger la bibliothèque existante
    library = load_icon_library()
    existing_count = len(library.get("icons", []))
    print(f"📚 Bibliothèque: {existing_count} icônes existantes")
    
    # Trouver les cartes
    map_files = sorted(args.maps_dir.rglob("*.png"))
    
    if args.limit > 0:
        map_files = map_files[:args.limit]
    
    print(f"🗂️ {len(map_files)} cartes à traiter")
    print(f"🤖 {args.model}")
    print("=" * 60)
    
    if not map_files:
        print("✅ Aucune carte à traiter")
        return
    
    # Traitement
    start = datetime.now()
    total_added = 0
    
    for map_path in map_files:
        added = process_map(map_path, legend_config, args.model, library)
        total_added += added
        
        # Sauvegarder régulièrement
        if total_added > 0:
            save_icon_library(library)
    
    elapsed = (datetime.now() - start).total_seconds()
    
    print(f"\n{'='*60}")
    print(f"✅ {total_added} nouvelles icônes ajoutées")
    print(f"📚 Total: {len(library['icons'])} icônes")
    print(f"⏱️ {elapsed:.1f}s")
    print(f"📁 Bibliothèque: {ICON_LIBRARY_FILE}")
    print("=" * 60)
    
    # Afficher la liste finale
    print("\n📋 Icônes dans la bibliothèque:")
    for icon in library["icons"]:
        print(f"   {icon['index']:2d}. {icon['name']}")


if __name__ == "__main__":
    main()
