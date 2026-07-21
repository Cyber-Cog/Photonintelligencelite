# Local Docker Compose only — the free-tier deployment serves the frontend as a static
# Vercel build (see vercel.json), not this image.
FROM node:20-alpine

WORKDIR /app

COPY package.json ./
RUN npm install

COPY . .

EXPOSE 5173
CMD ["npm", "run", "dev"]
