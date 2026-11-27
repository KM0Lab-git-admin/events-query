# Events Query API

**API REST para búsqueda inteligente de eventos usando lenguaje natural con IA (ES/CAT)**

[![Python](https://img.shields.io/badge/Python-3.11+-blue.svg)](https://www.python.org/)
[![FastAPI](https://img.shields.io/badge/FastAPI-0.115-green.svg)](https://fastapi.tiangolo.com/)
[![OpenAI](https://img.shields.io/badge/OpenAI-GPT--4.1-orange.svg)](https://openai.com/)
[![MySQL](https://img.shields.io/badge/MySQL-8.0-blue.svg)](https://www.mysql.com/)

---

## 🎯 ¿Qué es Events Query API?

Events Query API es un sistema inteligente que permite buscar eventos locales usando **lenguaje natural** en español o catalán. Combina **búsqueda semántica** con **IA generativa** para entender preguntas complejas y devolver eventos relevantes con respuestas naturales.

### Ejemplo

**Pregunta:** *"¿Qué hacer este fin de semana con niños cerca de mi?"*

**Respuesta:** *"He encontrado 5 eventos perfectos para niños este fin de semana en tu zona: Cuentacuentos en la biblioteca (gratis), Taller de manualidades infantiles..."*

---

## ✨ Características Principales

### 🤖 Inteligencia Artificial

- **Búsqueda en lenguaje natural**: Pregunta como hablarías con un amigo
- **OpenAI GPT-4.1-mini**: Extracción inteligente de parámetros
- **Búsqueda semántica**: Embeddings para encontrar eventos relevantes
- **Respuestas naturales**: Explicaciones en lenguaje humano
- **Análisis detallado**: Sistema de diagnóstico para entender decisiones de la IA

### 🌍 Búsqueda Geográfica

- **Filtrado por código postal**: Eventos en tu zona
- **Radio configurable**: Busca en 5, 10, 20 km a la redonda
- **Cálculo de distancias**: Muestra qué tan lejos está cada evento

### 🌐 Bilingüe

- **Español y catalán**: Soporte nativo completo
- **Detección automática**: Responde en el idioma de la pregunta
- **Datos bilingües**: Todos los eventos en ambos idiomas

### ⚡ Performance

- **< 1.5 segundos**: Respuesta típica (objetivo del PoC)
- **Arquitectura asíncrona**: FastAPI + aiomysql
- **Connection pooling**: Optimización de BD
- **ORJSONResponse**: Serialización ultra-rápida

### 🎨 Frontend Interactivo (PoC)

- **React + Vite**: Interfaz moderna
- **Visualización de eventos**: Lista con filtros
- **Chat de consultas**: Pregunta y responde en tiempo real
- **Análisis detallado**: Ve paso a paso cómo la IA toma decisiones

---

## 🔀 Dual Router (Legacy + API v1)

El backend expone **dos conjuntos de rutas** en paralelo:

- **API v1 (recomendada)**: rutas versionadas bajo `/api/v1/*` (para producción y futuro)
- **Legacy (compatibilidad / PoC)**: rutas antiguas (`/query`, `/events/*`, etc.) mantenidas temporalmente

> Estrategia: mantener Legacy mientras migra el frontend/consumidores; después se marca como *deprecated* y se retira.

---

## 🏗️ Arquitectura

```
┌─────────────────┐
│   Frontend      │  React + Vite
│   (Port 3000)   │
└────────┬────────┘
         │ HTTP
         ▼
┌─────────────────┐
│   Backend API   │  FastAPI
│   (Port 8000)   │
└────────┬────────┘
         │
    ┌────┴────┬────────────┐
    ▼         ▼            ▼
┌────────┐ ┌────────┐ ┌─────────┐
│ MySQL  │ │ OpenAI │ │ Análisis│
│  8.0   │ │ API    │ │ Service │
└────────┘ └────────┘ └─────────┘
```

**Componentes:**
- **Backend**: FastAPI + Python 3.11
- **Base de datos**: MySQL 8.0 con 8 tablas relacionales
- **IA**: OpenAI GPT-4.1-mini + text-embedding-3-small
- **Frontend**: React + Vite + TailwindCSS (PoC)
- **Análisis**: Sistema de diagnóstico y propuestas de mejora

---

## 🚀 Quick Start

### Requisitos

- Python 3.11+
- MySQL 8.0+
- Node.js 22+ (para frontend)
- OpenAI API Key

### Instalación Rápida (3 pasos)

```bash
# 1. Backend
cd events-query
python3.11 -m venv venv && source venv/bin/activate
pip install -r requirements.txt
cp .env.example .env  # Edita con tus credenciales
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# 2. Frontend (nueva terminal)
cd events-query/frontend
pnpm install
pnpm dev

# 3. Abrir navegador
open http://localhost:3000
```

**Ver guía completa:** [`docs/QUICKSTART.md`](docs/QUICKSTART.md)

---

## 📚 Documentación

### Para Empezar

- **[🚀 Quick Start](docs/QUICKSTART.md)** — Instalación y primer uso
- **[🏗️ Arquitectura](docs/ARCHITECTURE.md)** — Cómo funciona el sistema end-to-end
- **[🗃️ Modelo de datos + embeddings](docs/DATA_MODEL.md)** — Esquema, protocolo de ingesta, tags y embeddings
- **[👨‍💻 Desarrollo](docs/DEVELOPMENT.md)** — Guía para desarrolladores (scripts, tests, roadmap)
- **[🔧 Troubleshooting](docs/TROUBLESHOOTING.md)** — Solución de problemas

### API / Deploy

- **[📡 API (Legacy + v1)](docs/API.md)** — Guía humana de consumo + ejemplos
- **[🚢 Deployment (Railway)](docs/DEPLOYMENT.md)** — Variables, seed/fake data, embeddings, verificación Swagger

### API Docs (runtime)

- **Swagger UI**: http://localhost:8000/docs
- **ReDoc**: http://localhost:8000/redoc
- **OpenAPI JSON**: http://localhost:8000/openapi.json

---

## 💡 Ejemplo de Uso

### Endpoint recomendado (v1): `POST /api/v1/query`

```bash
curl -X POST "http://localhost:8000/api/v1/query"   -H "Content-Type: application/json"   -d '{
    "pregunta": "Actividades relacionadas con comida?",
    "cp_usuario": "08380",
    "debug": true
  }'
```

### Endpoint Legacy (compatibilidad): `POST /query`

```bash
curl -X POST "http://localhost:8000/query"   -H "Content-Type: application/json"   -d '{
    "pregunta": "Actividades relacionadas con comida?",
    "cp_usuario": "08380",
    "debug": true
  }'
```

### Respuesta (ejemplo)

```json
{
  "respuesta_texto": "He encontrado 3 eventos gastronómicos para ti...",
  "eventos": [
    {
      "id_unico_evento": "abc123",
      "titulo": "Cata de vinos y quesos - Malgrat de Mar",
      "cp_evento": "08380",
      "fecha_inicio": "2026-01-26",
      "es_gratuito": false,
      "precio_euros": 26.95,
      "categorias": ["Gastronomía"],
      "tags": ["#vinos", "#quesos", "#cata"],
      "similitud_score": 0.75
    }
  ],
  "total": 3,
  "idioma_respuesta": "es"
}
```

**Más ejemplos y contratos:** [`docs/API.md`](docs/API.md)

---

## 🧰 Scripts importantes

- `scripts/generate_fake_data.py` — genera datos fake (+ embeddings) e inserta en MySQL
- `scripts/generate_embeddings.py` — (re)genera embeddings para eventos existentes
- `scripts/verify_api_v1.py` — verifica que los endpoints v1 estén montados y visibles en Swagger

---

## 🛠️ Stack Tecnológico

### Backend

| Tecnología | Versión | Propósito |
|------------|---------|-----------|
| **Python** | 3.11+ | Lenguaje principal |
| **FastAPI** | 0.115 | Framework web |
| **Pydantic** | 2.x | Validación de datos |
| **aiomysql** | Latest | Driver MySQL async |
| **OpenAI** | Latest | IA generativa y embeddings |
| **Uvicorn** | Latest | Servidor ASGI |

### Frontend

| Tecnología | Versión | Propósito |
|------------|---------|-----------|
| **React** | 18+ | UI framework |
| **Vite** | 5+ | Build tool |
| **pnpm** | Latest | Package manager |

### Base de Datos

- **MySQL 8.0**: 8 tablas relacionales
- **Esquema**: Ver [`SQL/SCHEMA_SQL_FINAL.sql`](SQL/SCHEMA_SQL_FINAL.sql)

---

## 🎯 Estado Actual del Proyecto

### ✅ Implementado (Fase 1 + PoC)

- [x] Backend API completo con FastAPI
- [x] Dual Router (Legacy + `/api/v1/*`) para compatibilidad y evolución
- [x] Búsqueda en lenguaje natural (español/catalán)
- [x] Búsqueda semántica con embeddings
- [x] Búsqueda geográfica por CP y radio
- [x] Base de datos MySQL con 8 tablas
- [x] Eventos fake para testing
- [x] Frontend React con PoC funcional
- [x] Sistema de análisis detallado de similitud
- [x] Diagnóstico automático de problemas
- [x] Propuestas de mejora con impacto estimado
- [x] Documentación unificada en `docs/`

### 🚧 En Desarrollo

- [ ] Testing automatizado (50+ casos)
- [ ] Mejora de precisión (objetivo: 95%)
- [ ] Generación de embeddings faltantes

### 📋 Roadmap (Fase 2)

- [ ] Redis para cache de embeddings
- [ ] Rate limiting y autenticación
- [ ] Monitoreo (Prometheus + Grafana)
- [ ] Docker Compose para deployment
- [ ] CI/CD con GitHub Actions

**Ver roadmap completo:** [`docs/DEVELOPMENT.md#roadmap`](docs/DEVELOPMENT.md)

---

## 🧪 Testing

```bash
# Backend
pytest
pytest --cov=app --cov-report=html

# Frontend
cd frontend
pnpm test
```

**Ver guía de testing:** [`docs/DEVELOPMENT.md#testing`](docs/DEVELOPMENT.md)

---

## 📊 Performance

**Objetivo:** < 3 segundos  
**Actual:** ~1.4 segundos ✅

| Operación | Tiempo |
|-----------|--------|
| Extracción parámetros (IA) | 500ms |
| Cálculo geográfico | 50ms |
| Pre-filtrado SQL | 120ms |
| Búsqueda semántica | 130ms |
| Respuesta natural (IA) | 500ms |
| Otros | 100ms |
| **TOTAL** | **1400ms** |

**Throughput:** ~10 req/s (single instance)

---

## 🤝 Contribuir

1. Lee [`docs/DEVELOPMENT.md`](docs/DEVELOPMENT.md)
2. Crea una rama feature: `git checkout -b feature/nueva-funcionalidad`
3. Haz commit: `git commit -m "feat: descripción"`
4. Push: `git push origin feature/nueva-funcionalidad`
5. Abre un Pull Request

---

## 📄 Licencia

[Tu licencia aquí]

---

## 📞 Soporte

- **Documentación**: [`docs/`](docs/)
- **Issues**: [GitHub Issues](https://github.com/tu-repo/issues)

---

**Versión:** 1.0.0 (Fase 1 + PoC Frontend)  
**Última actualización:** 2026-02-07  
**Estado:** ✅ Funcional y en desarrollo activo
