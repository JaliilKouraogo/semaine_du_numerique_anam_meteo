FROM node:18-alpine

WORKDIR /app

# Copier les fichiers de dépendances
COPY package*.json ./
COPY frontend/package*.json ./frontend/

# Installer les dépendances
RUN npm install
RUN cd frontend && npm install

# Copier le code source
COPY . .

# Build du frontend
RUN cd frontend && npm run build

# Exposer les ports
EXPOSE 3001

# Variables d'environnement
ENV NODE_ENV=production
ENV PORT=3001

# Démarrer le serveur
CMD ["npm", "start"]

