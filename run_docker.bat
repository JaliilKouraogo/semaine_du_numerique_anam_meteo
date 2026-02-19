@echo off
echo --- Preparation de l'environnement Docker ---

:: Verifier si docker est installe
docker --version >nul 2>&1
if %errorlevel% neq 0 (
    echo Erreur: Docker n'est pas installe.
    pause
    exit /b 1
)

:: Creer les repertoires pour les volumes
if not exist data\pdfs mkdir data\pdfs
if not exist data\output mkdir data\output
if not exist data\temp mkdir data\temp

echo --- Lancement des conteneurs ---
docker-compose up --build -d

echo.
echo L'application est en cours de démarrage !
echo ------------------------------------------------
echo Frontend : http://localhost
echo Backend  : http://localhost:8000
echo ------------------------------------------------
echo.
echo Pour voir les logs : docker-compose logs -f
echo Pour arreter : docker-compose down
pause
