# Events Query API - Dockerfile
# Multi-stage build: Node.js para frontend + Python para backend

# ============================================
# Stage 1: Build del frontend con Node.js
# ============================================
FROM node:20-slim AS frontend-builder

WORKDIR /frontend

# Copiar archivos de dependencias
COPY frontend/package*.json frontend/pnpm-lock.yaml* ./

# Instalar dependencias (usa npm si no hay pnpm-lock)
RUN npm install

# Copiar código del frontend
COPY frontend/ ./

# Build de producción
RUN npm run build

# ============================================
# Stage 2: Aplicación Python con frontend
# ============================================
FROM python:3.11-slim

WORKDIR /app

# Instalar dependencias del sistema
RUN apt-get update && apt-get install -y \
    gcc \
    default-libmysqlclient-dev \
    pkg-config \
    && rm -rf /var/lib/apt/lists/*

# Copiar requirements
COPY requirements.txt .

# Instalar dependencias Python
RUN pip install --no-cache-dir -r requirements.txt

# Copiar código de la aplicación
COPY . .

# Copiar frontend compilado desde stage anterior
COPY --from=frontend-builder /frontend/dist /app/frontend/dist

# Exponer puerto (Railway usa variable PORT)
EXPOSE 8000

# Comando por defecto - usa PORT de Railway o 8000 por defecto
CMD ["sh", "-c", "uvicorn app.main:app --host 0.0.0.0 --port ${PORT:-8000}"]
