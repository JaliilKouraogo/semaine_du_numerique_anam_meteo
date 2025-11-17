# ANAM-MÉTÉO-EVAL Dashboard

Dashboard web pour évaluation de bulletins météorologiques ANAM avec extraction automatique, calcul de métriques et génération de textes en langues nationales.

## 🎯 Objectifs

- Ingérer automatiquement des bulletins météo PDF ANAM
- Extraire Tmin/Tmax et pictogrammes
- Calculer des métriques d'évaluation (MAE, RMSE, matrice de confusion)
- Générer des interprétations en langues nationales via LLM
- Visualiser la qualité des prévisions par station

## 📋 Prérequis

- Node.js 18+ et npm
- Git

## 🚀 Installation rapide

```bash
# Cloner le repo
git clone <repo-url>
cd anam_meteo

# Installer toutes les dépendances (frontend + backend)
npm run install-all

# Créer le fichier .env (copier .env.example)
cp .env.example .env
```

## 🏃 Démarrage

### Développement (frontend + backend simultanés)

```bash
npm run dev
```

### Backend uniquement

```bash
npm run server
# Le serveur démarre sur http://localhost:3001
```

### Frontend uniquement

```bash
npm run client
# Le frontend démarre sur http://localhost:3000
```

## 📁 Structure du projet

```
anam_meteo/
├── frontend/              # Application React
│   ├── src/
│   │   ├── components/    # Composants réutilisables
│   │   ├── pages/         # Pages principales
│   │   ├── services/      # Services API
│   │   └── utils/         # Utilitaires
│   └── package.json
├── api/                   # Backend Express
│   ├── routes/            # Routes API
│   ├── models/            # Modèles Sequelize
│   ├── controllers/       # Contrôleurs
│   ├── db/                # Base de données SQLite
│   └── server.js          # Point d'entrée
├── docs/                  # Documentation (Swagger, etc.)
└── package.json
```

## 🔌 Endpoints API principaux

### Upload & Ingestion
- `POST /api/v1/upload-bulletin` - Upload un PDF bulletin
- `GET /api/v1/job/:jobId` - Statut d'un job d'ingestion
- `GET /api/v1/bulletin/:id` - Détails d'un bulletin

### Stations
- `GET /api/v1/stations` - Liste des stations
- `GET /api/v1/station/:id` - Détails d'une station
- `GET /api/v1/station/:id/metrics` - Métriques d'une station

### Évaluation
- `GET /api/v1/evaluation` - Métriques globales
- `GET /api/v1/report/:date` - Rapport pour une date

### LLM
- `POST /api/v1/llm/generate` - Générer texte en langue nationale

Voir `docs/swagger.json` pour la documentation complète de l'API.

## 🗄️ Base de données

SQLite avec les tables suivantes :
- `stations` - Informations des stations météo
- `bulletins` - Bulletins ingérés
- `observations` - Observations réelles
- `previsions` - Prévisions extraites
- `evals` - Métriques d'évaluation
- `jobs` - Jobs d'ingestion

La base de données est créée automatiquement au premier démarrage du serveur.

## 🎨 Technologies

### Frontend
- React 18
- Tailwind CSS
- ECharts (graphiques)
- Leaflet (cartes)
- React Router

### Backend
- Node.js + Express
- Sequelize ORM
- SQLite
- Multer (upload fichiers)

## 📝 Utilisation avec votre backend

Pour remplacer le backend mock par votre implémentation :

1. Modifiez les URLs dans `frontend/src/services/api.js`
2. Adaptez les endpoints dans `api/routes/` selon votre architecture
3. Remplacez les modèles Sequelize si nécessaire

## 🧪 Tests

```bash
# Tests backend (à implémenter)
npm test

# Tests frontend
cd frontend && npm test
```

Une collection Postman est disponible dans `docs/postman_collection.json`.

## 📦 Docker (optionnel)

```bash
docker build -t anam-meteo .
docker run -p 3000:3000 -p 3001:3001 anam-meteo
```

## 🎯 Fonctionnalités MVP

- ✅ Upload PDF → extraction → JSON structuré
- ✅ Dashboard avec KPIs
- ✅ Page détails station (graphiques + métriques)
- ✅ Calcul MAE/RMSE et export CSV
- ✅ Interface responsive

## 📊 Données de démonstration

Des données mock sont fournies pour démonstration. Remplacez-les par vos données réelles via l'API.

## 📞 Support

Pour le hackathon, consultez la documentation dans `docs/` ou les commentaires dans le code.

## 📄 Licence

MIT

