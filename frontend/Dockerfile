# Storyteller-V2 SvelteKit Frontend
FROM node:20-slim AS build

WORKDIR /app
COPY package*.json ./
RUN npm ci
COPY . .
ARG VITE_API_BASE_URL=http://localhost:8000
ENV VITE_API_BASE_URL=${VITE_API_BASE_URL}
RUN npm run build

FROM node:20-slim AS runtime
WORKDIR /app
COPY --from=build /app/build build/
COPY --from=build /app/package.json .
EXPOSE 3000
ENV PORT=3000

# Serve with a simple static server
RUN npm install -g sirv-cli
CMD ["sirv", "build", "--host", "0.0.0.0", "--port", "3000", "--single"]
