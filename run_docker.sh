#!/bin/bash

# Script pour lancer l'application avec Docker Compose

echo "--- Préparation de l'environnement Docker ---"

# Vérifier si docker est installé
if ! command -v docker &> /dev/null
then
    echo "Erreur: Docker n'est pas installé."
    exit 1
fi

# Vérifier si docker-compose est installé
if ! command -v docker-compose &> /dev/null
then
    echo "Erreur: docker-compose n'est pas installé."
    exit 1
fi

# Créer les répertoires nécessaires pour les volumes
mkdir -p data/pdfs data/output data/temp

# Lancer les conteneurs
echo "--- Lancement des conteneurs ---"
docker-compose up --build -d

echo ""
echo "L'application est en cours de démarrage !"
echo "------------------------------------------------"
echo "Frontend : http://localhost"
echo "Backend  : http://localhost:8000"
echo "------------------------------------------------"
echo ""
echo "Pour voir les logs : docker-compose logs -f"
echo "Pour arrêter : docker-compose down"
