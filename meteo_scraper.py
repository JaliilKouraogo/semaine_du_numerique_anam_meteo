import os
import re
import requests
from urllib.parse import urljoin, urlparse
from bs4 import BeautifulSoup
from datetime import datetime
import time

BASE_URL = "https://meteoburkina.bf"
LIST_BASE_URL = f"{BASE_URL}/produits/bulletin-quotidien/"
OUTPUT_DIR = "bulletins_pdf"

os.makedirs(OUTPUT_DIR, exist_ok=True)

# ============================================================================
# RÈGLE DÉFINITIVE POUR LES PDF DE BULLETINS MÉTÉO
# ============================================================================
# Le site fonctionne en 2 étapes :
# 1. Liste des bulletins : /produits/bulletin-quotidien/?page=N
# 2. Page individuelle : /produits/bulletin-quotidien/bulletin-meteo-du-XX/
# 3. PDF sur la page : /documents/{ID}/Bulletin_du_*.pdf
# ============================================================================

PDF_PATTERN = re.compile(
    r"^https://meteoburkina\.bf/documents/\d+/Bulletin_du_.+\.pdf$",
    re.IGNORECASE
)

BULLETIN_PAGE_PATTERN = re.compile(
    r"^/produits/bulletin-quotidien/bulletin-meteo-du-.+/$",
    re.IGNORECASE
)

found_pdfs = set()
visited_pages = set()
stats = {
    "pages_scanned": 0,
    "bulletin_pages_found": 0,
    "bulletin_pages_visited": 0,
    "total_links": 0,
    "valid_pdfs": 0,
    "downloaded": 0,
    "skipped": 0,
    "errors": 0
}


def is_valid_bulletin_pdf(url: str) -> bool:
    """Vérifie si l'URL correspond à un bulletin PDF valide."""
    url = url.strip()
    
    if not PDF_PATTERN.match(url):
        return False
    
    parsed = urlparse(url)
    
    if parsed.netloc != "meteoburkina.bf":
        return False
    
    if not parsed.path.startswith("/documents/"):
        return False
    
    if not parsed.path.lower().endswith(".pdf"):
        return False
    
    if "Bulletin_du_" not in parsed.path:
        return False
    
    return True


def is_bulletin_page(href: str) -> bool:
    """Vérifie si c'est une page de bulletin individuel."""
    return bool(BULLETIN_PAGE_PATTERN.match(href))


def extract_pdf_from_bulletin_page(url: str):
    """Extrait le PDF d'une page de bulletin individuel."""
    if url in visited_pages:
        return
    
    visited_pages.add(url)
    stats["bulletin_pages_visited"] += 1
    
    print(f"  📄 Analyse bulletin : {url.split('/')[-2]}")
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        resp = requests.get(url, timeout=20, headers=headers)
        resp.raise_for_status()
        
    except Exception as e:
        print(f"    ✗ Erreur d'accès : {e}")
        stats["errors"] += 1
        return
    
    soup = BeautifulSoup(resp.text, "html.parser")
    
    # Chercher tous les liens PDF
    for a in soup.find_all("a", href=True):
        href = a["href"].strip()
        full_url = urljoin(BASE_URL, href)
        
        if is_valid_bulletin_pdf(full_url):
            if full_url not in found_pdfs:
                found_pdfs.add(full_url)
                stats["valid_pdfs"] += 1
                download_pdf(full_url)
                return  # Un seul PDF par bulletin


def download_pdf(url: str):
    """Télécharge un PDF dans OUTPUT_DIR."""
    filename = urlparse(url).path.split("/")[-1]
    dest_path = os.path.join(OUTPUT_DIR, filename)

    if os.path.exists(dest_path):
        print(f"    ✓ Déjà téléchargé : {filename}")
        stats["skipped"] += 1
        return True

    print(f"    ⬇ Téléchargement : {filename}")
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        r = requests.get(url, stream=True, timeout=30, headers=headers)
        r.raise_for_status()
        
        with open(dest_path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                if chunk:
                    f.write(chunk)
        
        file_size = os.path.getsize(dest_path)
        print(f"    ✓ Sauvegardé : {filename} ({file_size:,} octets)")
        stats["downloaded"] += 1
        return True
        
    except Exception as e:
        print(f"    ✗ Erreur : {e}")
        stats["errors"] += 1
        if os.path.exists(dest_path):
            os.remove(dest_path)
        return False


def parse_list_page(url: str, page_num: int) -> bool:
    """Analyse une page de liste et trouve les pages de bulletins."""
    print(f"\n{'='*70}")
    print(f"📋 Page de liste {page_num} : {url}")
    print(f"{'='*70}")
    
    try:
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        }
        resp = requests.get(url, timeout=20, headers=headers)
        resp.raise_for_status()
        stats["pages_scanned"] += 1
        
    except requests.exceptions.HTTPError as e:
        if e.response.status_code == 404:
            print(f"  → Page non trouvée (fin de pagination)")
            return False
        print(f"  → Erreur HTTP {e.response.status_code}")
        return False
        
    except Exception as e:
        print(f"  → Erreur de requête : {e}")
        return False

    soup = BeautifulSoup(resp.text, "html.parser")
    
    # Chercher les liens vers les pages de bulletins
    all_links = soup.find_all("a", href=True)
    stats["total_links"] += len(all_links)
    
    bulletin_pages = []
    for a in all_links:
        href = a["href"].strip()
        
        # Vérifier si c'est une page de bulletin
        if is_bulletin_page(href):
            full_url = urljoin(BASE_URL, href)
            if full_url not in visited_pages:
                bulletin_pages.append(full_url)
                stats["bulletin_pages_found"] += 1
    
    print(f"  → {len(bulletin_pages)} page(s) de bulletin trouvée(s)")
    
    # Extraire les PDFs de chaque page de bulletin
    for bulletin_url in bulletin_pages:
        extract_pdf_from_bulletin_page(bulletin_url)
        time.sleep(0.5)  # Pause pour ne pas surcharger le serveur
    
    return True


def display_summary():
    """Affiche un résumé détaillé de l'exécution."""
    print(f"\n\n{'='*70}")
    print("📊 RÉSUMÉ DE L'EXÉCUTION")
    print(f"{'='*70}")
    print(f"Pages de liste analysées      : {stats['pages_scanned']}")
    print(f"Pages de bulletins trouvées   : {stats['bulletin_pages_found']}")
    print(f"Pages de bulletins visitées   : {stats['bulletin_pages_visited']}")
    print(f"Liens totaux examinés         : {stats['total_links']}")
    print(f"PDFs valides trouvés          : {stats['valid_pdfs']}")
    print(f"PDFs téléchargés              : {stats['downloaded']}")
    print(f"PDFs déjà présents            : {stats['skipped']}")
    print(f"Erreurs                       : {stats['errors']}")
    print(f"\nDossier de sortie             : {os.path.abspath(OUTPUT_DIR)}")
    print(f"{'='*70}")
    
    if found_pdfs:
        print(f"\n📑 Liste des {len(found_pdfs)} PDFs trouvés :")
        for pdf in sorted(found_pdfs):
            filename = urlparse(pdf).path.split("/")[-1]
            print(f"  • {filename}")


if __name__ == "__main__":
    print(f"{'='*70}")
    print("🌤️  SCRAPER DE BULLETINS MÉTÉO - BURKINA FASO")
    print(f"{'='*70}")
    print(f"Source       : {LIST_BASE_URL}")
    print(f"Destination  : {OUTPUT_DIR}")
    print(f"Date         : {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}")
    print(f"{'='*70}\n")
    
    start_time = time.time()
    
    # Page 1 (sans paramètre)
    parse_list_page(LIST_BASE_URL, 1)
    
    # Pages suivantes
    MAX_PAGES = 60
    for page in range(2, MAX_PAGES + 1):
        url = f"{LIST_BASE_URL}?page={page}"
        if not parse_list_page(url, page):
            print(f"\n→ Arrêt à la page {page} (fin de pagination)")
            break
        time.sleep(1)  # Pause entre les pages
    
    elapsed = time.time() - start_time
    stats["duration"] = elapsed
    
    display_summary()
    print(f"\n⏱️  Durée totale : {elapsed:.2f} secondes")
    print(f"{'='*70}\n")