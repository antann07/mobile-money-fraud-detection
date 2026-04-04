# ============================================================
# React/Vite Frontend — Production Dockerfile
# ============================================================
# Stage 1: Build the SPA with Node
# Stage 2: Serve static files with Nginx
# ============================================================

# ── Stage 1: Build ───────────────────────────────────────────
FROM node:20-alpine AS builder

WORKDIR /app

# Install deps (cached unless package files change)
COPY package.json package-lock.json ./
RUN npm ci

# Copy source and build
COPY . .

# At build time, VITE_API_BASE tells the SPA where to call the backend.
# In production behind the Nginx reverse proxy it's just "" (same origin).
ARG VITE_API_BASE=""
ENV VITE_API_BASE=$VITE_API_BASE

RUN npm run build


# ── Stage 2: Serve with Nginx ────────────────────────────────
FROM nginx:1.27-alpine

# Remove default site
RUN rm /etc/nginx/conf.d/default.conf

# Copy our config
COPY nginx.conf /etc/nginx/conf.d/default.conf

# Copy built assets from Stage 1
COPY --from=builder /app/dist /usr/share/nginx/html

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
