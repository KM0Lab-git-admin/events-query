# 📡 API (Legacy + v1) — Events Query

Esta guía está pensada para **consumidores de la API** (frontend, integraciones).  
La **referencia viva** de endpoints y esquemas es Swagger (`/docs`).

---

## 🧭 Base URL

- Local: `http://localhost:8000`
- UAT / Railway: `https://eventquery.uat.km0lab.com`

---

## 🔀 Versionado y compatibilidad (Dual Router)

El backend expone:

### API v1 (recomendada)
Todas las rutas bajo:
- `/api/v1/*`

### Legacy (compatibilidad / PoC)
Rutas antiguas mantenidas temporalmente:
- `/query`, `/health`, `/events/*`, etc.

> Nota: Legacy se mantendrá mientras haya clientes que dependan de ella; después se marcará como *deprecated*.

---

## 🚦 Rate limiting (v1)

Se usa rate limiting por endpoint (vía `slowapi`). Valores típicos documentados:

- `/api/v1/query`: **30 req/min**
- `/api/v1/events`, `/api/v1/events/{id}`, `/api/v1/categories`, `/api/v1/events/upcoming`: **100 req/min**
- `/api/v1/events/today`: **200 req/min**
- `/api/v1/health`: sin límite

Headers habituales:
- `X-RateLimit-Limit`
- `X-RateLimit-Remaining`
- `X-RateLimit-Reset`

Respuesta al exceder:
- HTTP `429` con un JSON de error.

---

## ❌ Formato de error

Los errores se devuelven como JSON (ejemplo):

```json
{
  "error": "validation_error",
  "message": "Código postal inválido",
  "detail": "El código postal debe tener exactamente 5 dígitos numéricos",
  "timestamp": "2026-02-06T10:30:00Z"
}
```

---

# ✅ API v1

## 1) POST `/api/v1/query` — búsqueda por lenguaje natural

**Uso:** experiencia “chat” (IA + ranking) a partir de una pregunta y CP.

### Body

```json
{
  "pregunta": "¿Qué hacer este fin de semana?",
  "cp_usuario": "08380",
  "limit": 20,
  "debug": false
}
```

Campos:
- `pregunta` (string, requerido): 3–500 caracteres.
- `cp_usuario` (string, requerido): CP 5 dígitos.
- `limit` (int, opcional): máximo de eventos a devolver (1–100). Default: 20.
- `debug` (bool, opcional): devuelve información adicional para análisis. Default: false.

### Response (200)

Devuelve:
- `respuesta_texto`
- `eventos[]` (lista rankeada, con `similitud_score` y opcionalmente `distancia_km`)
- `idioma_respuesta`
- `metadata`

---

## 2) GET `/api/v1/events` — lista de eventos con filtros y paginación

**Uso:** listar eventos para UI (grid/list) sin el coste de la IA.

### Query params (habituales)

- `page` (int, default 1)
- `page_size` (int, default 20, max 100)
- `poblacion` (string)
- `categoria` (string, slug)
- `fecha_desde` (YYYY-MM-DD) — default: hoy
- `fecha_hasta` (YYYY-MM-DD) — default: hoy + 30 días
- `es_gratuito` (bool)
- `search` (string) — texto libre (título + tags)
- `ordenar_por` (string) — `fecha`, `precio`, `distancia`, `similitud` (según implementación)

Ejemplos:

```bash
# Página 1, 20 por página
GET /api/v1/events?page=1&page_size=20

# Solo gratuitos (próximos 30 días por defecto)
GET /api/v1/events?es_gratuito=true

# En un rango de fechas
GET /api/v1/events?fecha_desde=2026-02-08&fecha_hasta=2026-02-09

# Por población + categoría
GET /api/v1/events?poblacion=Malgrat%20de%20Mar&categoria=gastronomia

# Búsqueda textual
GET /api/v1/events?search=infantil%20aire%20libre
```

> Nota de unificación: en documentos antiguos aparecen `limit/offset`. La paginación recomendada en esta doc es `page/page_size`.

---

## 3) GET `/api/v1/events/{id}` — detalle de evento

**Uso:** pantalla de detalle.

```bash
GET /api/v1/events/evt_123
```

---

## 4) GET `/api/v1/events/today` — eventos de hoy

**Uso:** atajo optimizado para “Hoy”.

```bash
GET /api/v1/events/today
```

---

## 5) GET `/api/v1/events/upcoming` — próximos eventos

**Uso:** atajo para “próximos X días”.

Query params:
- `days` (int, 1–30, default 7)

```bash
GET /api/v1/events/upcoming?days=7
```

---

## 6) GET `/api/v1/categories` — categorías con conteos

```bash
GET /api/v1/categories
```

---

## 7) GET `/api/v1/health` — health check

```bash
GET /api/v1/health
```

---

# 🧯 Legacy (compatibilidad)

Endpoints legacy expuestos (según dual router actual):

| Método | Endpoint | Uso |
|---|---|---|
| POST | `/query` | búsqueda NL (legacy) |
| GET | `/health` | health (legacy) |
| GET | `/api/info` | info API |
| GET | `/events/simple` | lista simple |
| GET | `/events/list` | lista con filtros (legacy) |
| GET | `/events/categorias` | categorías (legacy) |
| GET | `/events/poblaciones` | poblaciones (legacy) |

Recomendación: para nuevas integraciones usar **v1**.

---

# 🔁 Guía rápida de migración (legacy → v1)

- `/query` → `/api/v1/query`
- `/health` → `/api/v1/health`
- `/events/list` / `/events/simple` → `/api/v1/events`
- `/events/categorias` → `/api/v1/categories`
- (nuevo) detalle: `/api/v1/events/{id}`
- (nuevo) shortcuts: `/api/v1/events/today`, `/api/v1/events/upcoming`

---

## 📚 Swagger / OpenAPI

- Swagger UI: `/docs`
- ReDoc: `/redoc`
- OpenAPI JSON: `/openapi.json`

