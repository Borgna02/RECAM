# Usa un'immagine base di Node.js per la build
FROM node:23.6.1 AS builder

# Imposta la directory di lavoro
WORKDIR /app

# Copia i file package.json e package-lock.json
COPY package.json package-lock.json ./

# Installa le dipendenze
RUN npm install

# Copia tutto il codice del frontend
COPY . .

# Compila il frontend
RUN npm run build

# Seconda fase: Usa Nginx per servire il frontend
FROM nginx:latest
COPY --from=builder /app/build /usr/share/nginx/html

# Esponi la porta 80
EXPOSE 80

# Avvia Nginx
CMD ["nginx", "-g", "daemon off;"]
