"""
delete_18h_bulletins.py - Supprime les bulletins de 18h00

Usage:
    python delete_18h_bulletins.py --input "BULLETIN 2023" --dry-run
    python delete_18h_bulletins.py --input "BULLETIN 2023" --delete
"""

import os
import re
import argparse
from pathlib import Path


def find_18h_bulletins(input_dir: Path) -> list:
    """Trouve tous les fichiers bulletins de 18h00."""
    pattern = re.compile(r"18h00", re.IGNORECASE)
    
    bulletins_18h = []
    for file_path in input_dir.rglob("*"):
        if file_path.is_file() and pattern.search(file_path.name):
            bulletins_18h.append(file_path)
    
    return sorted(bulletins_18h)


def main():
    parser = argparse.ArgumentParser(description="Supprime les bulletins de 18h00")
    parser.add_argument("--input", type=Path, required=True, help="Dossier source contenant les bulletins")
    parser.add_argument("--dry-run", action="store_true", help="Affiche les fichiers sans les supprimer")
    parser.add_argument("--delete", action="store_true", help="Supprime réellement les fichiers")
    args = parser.parse_args()
    
    if not args.input.exists():
        print(f"❌ Dossier introuvable: {args.input}")
        return
    
    if not args.dry_run and not args.delete:
        print("⚠️  Spécifiez --dry-run pour lister ou --delete pour supprimer")
        return
    
    print("=" * 60)
    print("🗑️  SUPPRESSION DES BULLETINS 18h00")
    print("=" * 60)
    print(f"📁 Dossier: {args.input}")
    print(f"🔍 Mode: {'DRY-RUN (simulation)' if args.dry_run else 'SUPPRESSION RÉELLE'}")
    print("=" * 60)
    
    bulletins = find_18h_bulletins(args.input)
    
    if not bulletins:
        print("✅ Aucun bulletin 18h00 trouvé.")
        return
    
    print(f"\n📋 {len(bulletins)} fichiers 18h00 trouvés:\n")
    
    deleted = 0
    for path in bulletins:
        rel_path = path.relative_to(args.input)
        size_kb = path.stat().st_size / 1024
        
        if args.delete:
            try:
                os.remove(path)
                print(f"  🗑️  SUPPRIMÉ: {rel_path} ({size_kb:.1f} KB)")
                deleted += 1
            except Exception as e:
                print(f"  ❌ ERREUR: {rel_path} - {e}")
        else:
            print(f"  📄 {rel_path} ({size_kb:.1f} KB)")
    
    print("\n" + "=" * 60)
    if args.delete:
        print(f"✅ {deleted} fichiers supprimés")
    else:
        print(f"ℹ️  {len(bulletins)} fichiers à supprimer")
        print("💡 Lancez avec --delete pour supprimer réellement")
    print("=" * 60)


if __name__ == "__main__":
    main()
