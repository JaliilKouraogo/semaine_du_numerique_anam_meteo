
import sys
import os
from pathlib import Path

# Ajouter le répertoire racine au sys.path pour pouvoir importer les modules du backend
root_path = Path(__file__).resolve().parent
sys.path.append(str(root_path))

try:
    from backend.modules.language_interpreter import LanguageInterpreter
    import logging

    # Configurer le logging pour voir les messages
    logging.basicConfig(level=logging.INFO)

    def test_api():
        print("--- Test de l'API de traduction Moore ---")
        interpreter = LanguageInterpreter(db_manager=None)
        
        test_text = "Je suis ravi de vous revoir"
        print(f"Texte source : {test_text}")
        
        # On force la traduction pour ne pas utiliser le cache (qui est None ici de toute façon)
        result = interpreter.translate(test_text, "moore", force=True)
        
        if result:
            print(f"Traduction réussie : {result}")
        else:
            print("Échec de la traduction.")

    if __name__ == "__main__":
        test_api()

except Exception as e:
    print(f"Erreur lors de l'exécution du test : {e}")
    import traceback
    traceback.print_exc()
