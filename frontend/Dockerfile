# ─── Stage 1: Build ───────────────────────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app

COPY package*.json ./
RUN npm ci

COPY . .

# In Docker, the browser hits nginx on port 80 which proxies /api/ → backend
# So VITE_API_URL should be empty (same origin) not localhost:8000
ARG VITE_API_URL=
ENV VITE_API_URL=$VITE_API_URL

RUN npm run build

# ─── Stage 2: Serve with Nginx ────────────────────────────────────────────
FROM nginx:alpine

COPY --from=builder /app/dist /usr/share/nginx/html

# SPA routing + proxy /api/ and /ws/ to backend
RUN printf 'server {\n\
    listen 80;\n\
\n\
    # Proxy API calls to backend\n\
    location /api/ {\n\
        proxy_pass http://kalpi_backend:8000;\n\
        proxy_set_header Host $host;\n\
        proxy_set_header X-Real-IP $remote_addr;\n\
    }\n\
\n\
    # Proxy WebSocket to backend\n\
    location /ws/ {\n\
        proxy_pass http://kalpi_backend:8000;\n\
        proxy_http_version 1.1;\n\
        proxy_set_header Upgrade $http_upgrade;\n\
        proxy_set_header Connection "upgrade";\n\
        proxy_set_header Host $host;\n\
        proxy_read_timeout 86400;\n\
    }\n\
\n\
    # Proxy health/docs to backend\n\
    location /health {\n\
        proxy_pass http://kalpi_backend:8000;\n\
    }\n\
\n\
    # SPA — serve React app, redirect 404s to index.html\n\
    location / {\n\
        root /usr/share/nginx/html;\n\
        index index.html;\n\
        try_files $uri $uri/ /index.html;\n\
    }\n\
}' > /etc/nginx/conf.d/default.conf

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]



