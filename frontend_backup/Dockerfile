FROM node:20-slim

WORKDIR /app

# Installation des dépendances
COPY package*.json ./
RUN npm install

# Copie du reste du code
COPY . .

# Exposition du port de développement Vite
EXPOSE 5173

# Commande de démarrage
CMD ["npm", "run", "dev", "--", "--host", "0.0.0.0"]
