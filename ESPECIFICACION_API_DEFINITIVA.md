# 🚀 Especificación Definitiva API REST - Events Query

**Versión:** 1.0  
**Fecha:** 2026-02-06  
**Backend:** `eventquery.km0lab.com` (Railway)  
**Frontend:** `app.km0lab.com` (Vercel)  
**Autenticación:** Pública (sin auth)

---

## 📋 Índice

1. [Arquitectura](#arquitectura)
2. [Endpoints Definitivos](#endpoints-definitivos)
3. [Optimizaciones de Rendimiento](#optimizaciones-de-rendimiento)
4. [Configuración CORS](#configuración-cors)
5. [Rate Limiting](#rate-limiting)
6. [Manejo de Errores](#manejo-de-errores)
7. [Documentación Swagger](#documentación-swagger)
8. [Ejemplos de Integración](#ejemplos-de-integración)

---

## 🏗️ Arquitectura

```
┌─────────────────────────────────────────────────────────────┐
│                    app.km0lab.com (Vercel)                  │
│                     Frontend React/Next.js                   │
└────────────────────────┬────────────────────────────────────┘
                         │
                         │ HTTPS
                         │ CORS: app.km0lab.com
                         │
┌────────────────────────▼────────────────────────────────────┐
│              eventquery.km0lab.com (Railway)                │
│                    FastAPI + MySQL + OpenAI                  │
│                                                              │
│  /api/v1/query          - Búsqueda inteligente             │
│  /api/v1/events         - Listar con filtros + paginación  │
│  /api/v1/events/{id}    - Detalle de evento                │
│  /api/v1/health         - Health check                      │
│  /docs                  - Swagger UI                         │
└──────────────────────────────────────────────────────────────┘
```

---

## 🎯 Endpoints Definitivos

### Base URL
```
https://eventquery.km0lab.com/api/v1
```

---

### 1. POST `/api/v1/query` - Búsqueda Inteligente

**Descripción:** Búsqueda de eventos usando lenguaje natural con IA.

#### Request

```http
POST /api/v1/query HTTP/1.1
Host: eventquery.km0lab.com
Content-Type: application/json

{
  "pregunta": "¿Qué hacer este fin de semana?",
  "cp_usuario": "08380",
  "limit": 20,
  "debug": false
}
```

**Parámetros:**

| Campo | Tipo | Requerido | Default | Descripción |
|-------|------|-----------|---------|-------------|
| `pregunta` | string | ✅ Sí | - | Pregunta en lenguaje natural (3-500 caracteres) |
| `cp_usuario` | string | ✅ Sí | - | Código postal del usuario (5 dígitos) |
| `limit` | integer | ❌ No | 20 | Número máximo de eventos a devolver (1-100) |
| `debug` | boolean | ❌ No | false | Activar modo debug |

#### Response 200 OK

```json
{
  "respuesta_texto": "He encontrado 5 eventos para ti este fin de semana en Malgrat de Mar...",
  "eventos": [
    {
      "id_unico_evento": "c65f6d2e7e8064a276021c20306592bb98c723726fec4451e4f0b48e7e8600e",
      "titulo": "Cuentacuentos en la biblioteca",
      "descripcion_corta": "Sesión de cuentacuentos para niños de 3 a 8 años",
      "descripcion_larga": "Actividad familiar donde se narran cuentos tradicionales y modernos...",
      "cp_evento": "08380",
      "poblacion_nombre": "Malgrat de Mar",
      "lugar_nombre": "Biblioteca Municipal",
      "direccion_completa": "Carrer de la Biblioteca, 1",
      "fecha_inicio": "2026-02-08",
      "fecha_fin": "2026-02-08",
      "hora_inicio": "17:30:00",
      "hora_fin": "18:30:00",
      "es_gratuito": false,
      "precio_euros": 5.00,
      "categorias": ["Infantil", "Cultura"],
      "tags": ["infantil", "familia", "educativo", "cuentacuentos", "biblioteca"],
      "url_evento": "https://example.com/evento/123",
      "url_imagen": "https://example.com/imagen.jpg",
      "distancia_km": 0.5,
      "similitud_score": 0.92
    }
  ],
  "total": 5,
  "idioma_respuesta": "es",
  "metadata": {
    "limit": 20,
    "returned": 5,
    "tiempo_respuesta_ms": 245
  }
}
```

#### Response 400 Bad Request

```json
{
  "error": "validation_error",
  "message": "Código postal inválido",
  "detail": "El código postal debe tener exactamente 5 dígitos numéricos",
  "timestamp": "2026-02-06T10:30:00Z"
}
```

---

### 2. GET `/api/v1/events` - Listar Eventos con Filtros

**Descripción:** Lista eventos con filtros avanzados y paginación optimizada.

#### Request

```http
GET /api/v1/events?fecha_desde=2026-02-06&fecha_hasta=2026-02-08&poblacion=Malgrat%20de%20Mar&es_gratuito=true&limit=20&offset=0 HTTP/1.1
Host: eventquery.km0lab.com
```

**Parámetros Query:**

| Parámetro | Tipo | Requerido | Default | Descripción |
|-----------|------|-----------|---------|-------------|
| `fecha_desde` | date | ❌ No | hoy | Fecha mínima (YYYY-MM-DD) |
| `fecha_hasta` | date | ❌ No | +30 días | Fecha máxima (YYYY-MM-DD) |
| `poblacion` | string | ❌ No | todas | Filtrar por población ("Malgrat de Mar", "Blanes") |
| `categoria` | string | ❌ No | todas | Slug de categoría (cultura, deportes, gastronomia, etc.) |
| `es_gratuito` | boolean | ❌ No | - | Filtrar solo eventos gratuitos |
| `tags` | string | ❌ No | - | Buscar en tags (texto libre) |
| `limit` | integer | ❌ No | 20 | Número de resultados por página (1-100) |
| `offset` | integer | ❌ No | 0 | Saltar N resultados (paginación) |
| `ordenar_por` | string | ❌ No | fecha | Ordenar por: `fecha`, `precio`, `similitud`, `distancia` |

**Ejemplos de Uso:**

```bash
# Eventos de hoy
GET /api/v1/events?fecha_desde=2026-02-06&fecha_hasta=2026-02-06

# Eventos gratuitos este fin de semana
GET /api/v1/events?fecha_desde=2026-02-08&fecha_hasta=2026-02-09&es_gratuito=true

# Eventos de gastronomía en Malgrat
GET /api/v1/events?categoria=gastronomia&poblacion=Malgrat%20de%20Mar

# Paginación (página 2, 20 por página)
GET /api/v1/events?limit=20&offset=20
```

#### Response 200 OK

```json
{
  "eventos": [
    {
      "id_unico_evento": "abc123...",
      "titulo": "Cata de vinos y quesos",
      "descripcion_corta": "Degustación de vinos locales...",
      "cp_evento": "08380",
      "poblacion_nombre": "Malgrat de Mar",
      "lugar_nombre": "Centro Cultural",
      "fecha_inicio": "2026-02-08",
      "hora_inicio": "19:00:00",
      "es_gratuito": false,
      "precio_euros": 15.50,
      "categorias": ["Gastronomía"],
      "url_imagen": "https://..."
    }
  ],
  "pagination": {
    "total": 45,
    "limit": 20,
    "offset": 0,
    "returned": 20,
    "has_more": true,
    "next_offset": 20
  },
  "filters_applied": {
    "fecha_desde": "2026-02-06",
    "fecha_hasta": "2026-02-08",
    "es_gratuito": true
  },
  "metadata": {
    "tiempo_respuesta_ms": 35
  }
}
```

**Optimización:** Solo devuelve campos esenciales (no descripción_larga) para reducir payload.

---

### 3. GET `/api/v1/events/{id}` - Detalle de Evento

**Descripción:** Obtiene información completa de un evento específico.

#### Request

```http
GET /api/v1/events/c65f6d2e7e8064a276021c20306592bb98c723726fec4451e4f0b48e7e8600e HTTP/1.1
Host: eventquery.km0lab.com
```

#### Response 200 OK

```json
{
  "id_unico_evento": "c65f6d2e7e8064a276021c20306592bb98c723726fec4451e4f0b48e7e8600e",
  "titulo": "Cuentacuentos en la biblioteca",
  "descripcion_corta": "Sesión de cuentacuentos para niños...",
  "descripcion_larga": "Actividad familiar donde se narran cuentos tradicionales y modernos. Los niños podrán participar activamente y al final habrá un taller de manualidades relacionado con los cuentos narrados...",
  "cp_evento": "08380",
  "poblacion_nombre": "Malgrat de Mar",
  "lugar_nombre": "Biblioteca Municipal",
  "direccion_completa": "Carrer de la Biblioteca, 1, 08380 Malgrat de Mar",
  "coordenadas": {
    "latitud": 41.6456,
    "longitud": 2.7432
  },
  "fecha_inicio": "2026-02-08",
  "fecha_fin": "2026-02-08",
  "hora_inicio": "17:30:00",
  "hora_fin": "18:30:00",
  "es_gratuito": false,
  "precio_euros": 5.00,
  "moneda": "EUR",
  "categorias": ["Infantil", "Cultura"],
  "tags": ["infantil", "familia", "educativo", "cuentacuentos", "biblioteca"],
  "organizador": {
    "nombre": "Biblioteca Municipal de Malgrat de Mar",
    "tipo": "PUBLICO",
    "web": "https://biblioteca.malgratdemar.cat",
    "email": "biblioteca@malgratdemar.cat",
    "telefono": "+34 937 651 234"
  },
  "inscripcion": {
    "url_evento": "https://example.com/evento/123",
    "url_entradas": "https://example.com/entradas/123",
    "plazas_disponibles": 25,
    "plazas_totales": 30
  },
  "multimedia": {
    "url_imagen": "https://example.com/imagen.jpg",
    "imagenes_adicionales": [
      "https://example.com/imagen2.jpg",
      "https://example.com/imagen3.jpg"
    ]
  },
  "accesibilidad": {
    "accesible_movilidad_reducida": true,
    "parking_disponible": true,
    "transporte_publico": "Autobús L1, L2 - Parada Biblioteca"
  },
  "recurrencia": {
    "es_recurrente": true,
    "patron": "Todos los sábados",
    "proximas_fechas": [
      "2026-02-15",
      "2026-02-22",
      "2026-03-01"
    ]
  },
  "metadata": {
    "fecha_creacion": "2026-01-15T10:00:00Z",
    "fecha_actualizacion": "2026-02-01T15:30:00Z",
    "estado": "ACTIVO",
    "visitas": 245
  }
}
```

#### Response 404 Not Found

```json
{
  "error": "not_found",
  "message": "Evento no encontrado",
  "detail": "No existe ningún evento con el ID especificado",
  "timestamp": "2026-02-06T10:30:00Z"
}
```

---

### 4. GET `/api/v1/events/today` - Eventos de Hoy (Shortcut)

**Descripción:** Atajo optimizado para obtener eventos de hoy.

#### Request

```http
GET /api/v1/events/today?poblacion=Malgrat%20de%20Mar&limit=10 HTTP/1.1
Host: eventquery.km0lab.com
```

**Parámetros:**

| Parámetro | Tipo | Default | Descripción |
|-----------|------|---------|-------------|
| `poblacion` | string | todas | Filtrar por población |
| `limit` | integer | 10 | Número de eventos (1-50) |

#### Response 200 OK

```json
{
  "fecha": "2026-02-06",
  "eventos": [...],
  "total": 8,
  "metadata": {
    "cache_hit": true,
    "tiempo_respuesta_ms": 12
  }
}
```

**Optimización:** Respuesta cacheada durante 5 minutos para máximo rendimiento.

---

### 5. GET `/api/v1/events/upcoming` - Próximos Eventos

**Descripción:** Obtiene los próximos N eventos ordenados por fecha.

#### Request

```http
GET /api/v1/events/upcoming?days=7&limit=20 HTTP/1.1
Host: eventquery.km0lab.com
```

**Parámetros:**

| Parámetro | Tipo | Default | Descripción |
|-----------|------|---------|-------------|
| `days` | integer | 7 | Próximos N días (1-30) |
| `poblacion` | string | todas | Filtrar por población |
| `limit` | integer | 20 | Número de eventos (1-100) |

#### Response 200 OK

```json
{
  "fecha_desde": "2026-02-06",
  "fecha_hasta": "2026-02-13",
  "eventos": [...],
  "total": 32,
  "por_dia": {
    "2026-02-06": 5,
    "2026-02-07": 8,
    "2026-02-08": 12,
    "2026-02-09": 7
  }
}
```

---

### 6. GET `/api/v1/categories` - Listar Categorías

**Descripción:** Obtiene todas las categorías disponibles con conteo de eventos.

#### Request

```http
GET /api/v1/categories HTTP/1.1
Host: eventquery.km0lab.com
```

#### Response 200 OK

```json
{
  "categorias": [
    {
      "id": 1,
      "slug": "cultura",
      "nombre_es": "Cultura",
      "nombre_cat": "Cultura",
      "descripcion_es": "Eventos culturales, exposiciones, teatro...",
      "icono": "🎭",
      "color": "#FF6B6B",
      "eventos_activos": 45
    },
    {
      "id": 2,
      "slug": "gastronomia",
      "nombre_es": "Gastronomía",
      "nombre_cat": "Gastronomia",
      "descripcion_es": "Catas, degustaciones, festivales gastronómicos...",
      "icono": "🍷",
      "color": "#4ECDC4",
      "eventos_activos": 23
    }
  ],
  "total": 8
}
```

---

### 7. GET `/api/v1/health` - Health Check

**Descripción:** Verifica el estado de salud de la API y sus dependencias.

#### Request

```http
GET /api/v1/health HTTP/1.1
Host: eventquery.km0lab.com
```

#### Response 200 OK

```json
{
  "status": "healthy",
  "version": "1.0.0",
  "environment": "production",
  "timestamp": "2026-02-06T10:30:00Z",
  "checks": {
    "database": {
      "status": "healthy",
      "latency_ms": 5,
      "eventos_count": 125
    },
    "openai": {
      "status": "configured",
      "model": "gpt-4.1-mini"
    },
    "cache": {
      "status": "healthy",
      "hit_rate": 0.85
    }
  },
  "uptime_seconds": 86400
}
```

---

## ⚡ Optimizaciones de Rendimiento

### 1. Paginación Inteligente

**Problema:** Devolver 125 eventos en una sola petición es ineficiente.

**Solución:**
- Default: 20 eventos por página
- Máximo: 100 eventos por página
- Offset-based pagination
- Metadata con `has_more` y `next_offset`

**Ejemplo:**
```javascript
// Página 1
GET /api/v1/events?limit=20&offset=0

// Página 2
GET /api/v1/events?limit=20&offset=20

// Página 3
GET /api/v1/events?limit=20&offset=40
```

---

### 2. Filtros de Fecha por Default

**Problema:** Sin filtros, devuelve eventos pasados y muy futuros.

**Solución:**
- Default `fecha_desde`: hoy
- Default `fecha_hasta`: +30 días
- Usuario puede sobrescribir con parámetros

**Beneficio:** Reduce eventos devueltos de 125 → ~30-40 en promedio.

---

### 3. Campos Opcionales

**Problema:** `descripcion_larga` puede ser muy grande (1000+ caracteres).

**Solución:**
- `/api/v1/events` (lista): Solo campos esenciales
- `/api/v1/events/{id}` (detalle): Todos los campos

**Beneficio:** Reduce payload de lista en ~60%.

---

### 4. Caché Estratégico

**Endpoints cacheados:**
- `GET /api/v1/events/today` → 5 minutos
- `GET /api/v1/categories` → 1 hora
- `GET /api/v1/health` → 1 minuto

**Beneficio:** Respuestas en <15ms para endpoints cacheados.

---

### 5. Índices de Base de Datos

**Índices recomendados:**
```sql
CREATE INDEX idx_fecha_inicio ON EVENTO_HORARIOS(Fecha_Inicio);
CREATE INDEX idx_cp_estado ON EVENTOS_MASTER(CP_Evento, Estado);
CREATE INDEX idx_categoria ON EVENTO_CATEGORIAS(ID_Categoria);
```

**Beneficio:** Queries 10x más rápidas.

---

### 6. Compresión de Respuestas

**Configuración:**
```python
# FastAPI automáticamente comprime con gzip si el cliente lo soporta
# Ahorro típico: 70-80% del tamaño
```

---

### 7. Rate Limiting Inteligente

**Límites:**
- `POST /api/v1/query`: 30 req/min (más costoso, usa OpenAI)
- `GET /api/v1/events`: 100 req/min (más ligero)
- `GET /api/v1/events/today`: 200 req/min (cacheado)

**Implementación:** Por IP, con headers informativos:
```http
X-RateLimit-Limit: 30
X-RateLimit-Remaining: 25
X-RateLimit-Reset: 1675680000
```

---

## 🔒 Configuración CORS

### Producción

```python
from fastapi.middleware.cors import CORSMiddleware

app.add_middleware(
    CORSMiddleware,
    allow_origins=[
        "https://app.km0lab.com",
        "https://www.app.km0lab.com"
    ],
    allow_credentials=True,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=[
        "Content-Type",
        "Accept",
        "Origin",
        "User-Agent"
    ],
    expose_headers=[
        "X-RateLimit-Limit",
        "X-RateLimit-Remaining",
        "X-RateLimit-Reset"
    ],
    max_age=3600  # Cache preflight por 1 hora
)
```

### Desarrollo

```python
allow_origins=[
    "https://app.km0lab.com",
    "https://www.app.km0lab.com",
    "http://localhost:3000",      # React dev
    "http://localhost:5173",      # Vite dev
    "http://127.0.0.1:3000",
    "http://127.0.0.1:5173"
]
```

---

## 🚦 Rate Limiting

### Implementación con slowapi

```python
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.util import get_remote_address
from slowapi.errors import RateLimitExceeded

limiter = Limiter(key_func=get_remote_address)
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)

@app.post("/api/v1/query")
@limiter.limit("30/minute")
async def query_events(request: Request, query: QueryRequest):
    ...

@app.get("/api/v1/events")
@limiter.limit("100/minute")
async def list_events(request: Request):
    ...
```

### Response cuando se excede el límite

```http
HTTP/1.1 429 Too Many Requests
X-RateLimit-Limit: 30
X-RateLimit-Remaining: 0
X-RateLimit-Reset: 1675680060
Retry-After: 60

{
  "error": "rate_limit_exceeded",
  "message": "Demasiadas peticiones",
  "detail": "Has excedido el límite de 30 peticiones por minuto. Inténtalo de nuevo en 60 segundos.",
  "timestamp": "2026-02-06T10:30:00Z",
  "retry_after": 60
}
```

---

## ❌ Manejo de Errores

### Códigos de Estado

| Código | Significado | Cuándo |
|--------|-------------|--------|
| 200 | OK | Petición exitosa |
| 400 | Bad Request | Parámetros inválidos |
| 404 | Not Found | Recurso no encontrado |
| 429 | Too Many Requests | Rate limit excedido |
| 500 | Internal Server Error | Error del servidor |
| 503 | Service Unavailable | Servicio temporalmente no disponible |

### Formato de Error Estándar

```json
{
  "error": "error_code",
  "message": "Mensaje legible para humanos",
  "detail": "Información adicional del error",
  "timestamp": "2026-02-06T10:30:00Z",
  "path": "/api/v1/query",
  "request_id": "req_abc123xyz"
}
```

### Ejemplos de Errores

#### 400 - Validación

```json
{
  "error": "validation_error",
  "message": "Parámetros inválidos",
  "detail": {
    "pregunta": "La pregunta debe tener entre 3 y 500 caracteres",
    "cp_usuario": "El código postal debe tener 5 dígitos"
  },
  "timestamp": "2026-02-06T10:30:00Z"
}
```

#### 404 - No Encontrado

```json
{
  "error": "not_found",
  "message": "Evento no encontrado",
  "detail": "No existe ningún evento con el ID 'abc123'",
  "timestamp": "2026-02-06T10:30:00Z"
}
```

#### 500 - Error Interno

```json
{
  "error": "internal_server_error",
  "message": "Error interno del servidor",
  "detail": "Ha ocurrido un error inesperado. Por favor, inténtalo de nuevo más tarde.",
  "timestamp": "2026-02-06T10:30:00Z",
  "request_id": "req_abc123xyz"
}
```

---

## 📚 Documentación Swagger

### Metadata

```python
app = FastAPI(
    title="Events Query API",
    version="1.0.0",
    description="""
    🎉 **API REST para búsqueda inteligente de eventos locales**
    
    Esta API permite buscar eventos usando lenguaje natural gracias a IA (OpenAI GPT-4).
    
    ## 🌟 Características
    
    * **Búsqueda en lenguaje natural** - Pregunta como hablarías normalmente
    * **Detección automática de idioma** - Español y catalán
    * **Búsqueda semántica** - Encuentra eventos relevantes aunque no contengan las palabras exactas
    * **Optimizada para rendimiento** - Paginación, caché, filtros inteligentes
    * **Sin autenticación** - API pública y gratuita
    
    ## 📍 Poblaciones Soportadas
    
    * **Malgrat de Mar** (08380)
    * **Blanes** (17300)
    
    ## 💡 Ejemplos de Preguntas
    
    * "¿Qué hacer este fin de semana?"
    * "Actividades para niños"
    * "Eventos gastronómicos"
    * "Què puc fer aquest cap de setmana?" (catalán)
    
    ## 🚀 Rate Limits
    
    * `POST /query`: 30 req/min
    * `GET /events`: 100 req/min
    * `GET /events/today`: 200 req/min
    
    ## 🔗 Enlaces
    
    * [Documentación completa](https://docs.km0lab.com)
    * [Frontend](https://app.km0lab.com)
    * [Soporte](mailto:support@km0lab.com)
    """,
    contact={
        "name": "KM0Lab",
        "url": "https://km0lab.com",
        "email": "support@km0lab.com"
    },
    license_info={
        "name": "Propietario",
        "url": "https://km0lab.com/license"
    },
    servers=[
        {
            "url": "https://eventquery.km0lab.com",
            "description": "Producción (Railway)"
        },
        {
            "url": "http://localhost:8000",
            "description": "Desarrollo local"
        }
    ],
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)
```

### Tags para Agrupar Endpoints

```python
tags_metadata = [
    {
        "name": "Search",
        "description": "Búsqueda inteligente de eventos con IA"
    },
    {
        "name": "Events",
        "description": "Listar y filtrar eventos"
    },
    {
        "name": "Categories",
        "description": "Categorías de eventos"
    },
    {
        "name": "Health",
        "description": "Estado de salud de la API"
    }
]

app = FastAPI(..., openapi_tags=tags_metadata)

@router.post("/query", tags=["Search"])
async def query_events(...):
    ...

@router.get("/events", tags=["Events"])
async def list_events(...):
    ...
```

---

## 💻 Ejemplos de Integración

### React/Next.js (app.km0lab.com)

#### 1. Configuración Base

```javascript
// lib/api.js
const API_BASE_URL = 'https://eventquery.km0lab.com/api/v1';

class EventsAPI {
  constructor() {
    this.baseURL = API_BASE_URL;
  }

  async request(endpoint, options = {}) {
    const url = `${this.baseURL}${endpoint}`;
    
    const response = await fetch(url, {
      ...options,
      headers: {
        'Content-Type': 'application/json',
        ...options.headers
      }
    });

    if (!response.ok) {
      const error = await response.json();
      throw new Error(error.message || 'Error en la petición');
    }

    return await response.json();
  }

  // Búsqueda inteligente
  async buscar(pregunta, codigoPostal, limit = 20) {
    return this.request('/query', {
      method: 'POST',
      body: JSON.stringify({
        pregunta,
        cp_usuario: codigoPostal,
        limit,
        debug: false
      })
    });
  }

  // Listar eventos con filtros
  async listarEventos(filtros = {}) {
    const params = new URLSearchParams();
    
    if (filtros.fecha_desde) params.append('fecha_desde', filtros.fecha_desde);
    if (filtros.fecha_hasta) params.append('fecha_hasta', filtros.fecha_hasta);
    if (filtros.poblacion) params.append('poblacion', filtros.poblacion);
    if (filtros.categoria) params.append('categoria', filtros.categoria);
    if (filtros.es_gratuito !== undefined) params.append('es_gratuito', filtros.es_gratuito);
    if (filtros.limit) params.append('limit', filtros.limit);
    if (filtros.offset) params.append('offset', filtros.offset);

    return this.request(`/events?${params.toString()}`);
  }

  // Eventos de hoy
  async eventosHoy(poblacion = null, limit = 10) {
    const params = new URLSearchParams({ limit });
    if (poblacion) params.append('poblacion', poblacion);

    return this.request(`/events/today?${params.toString()}`);
  }

  // Detalle de evento
  async obtenerEvento(id) {
    return this.request(`/events/${id}`);
  }

  // Próximos eventos
  async proximosEventos(days = 7, limit = 20) {
    const params = new URLSearchParams({ days, limit });
    return this.request(`/events/upcoming?${params.toString()}`);
  }

  // Categorías
  async obtenerCategorias() {
    return this.request('/categories');
  }
}

export const eventsAPI = new EventsAPI();
```

#### 2. Hook de React

```javascript
// hooks/useEventos.js
import { useState, useEffect } from 'react';
import { eventsAPI } from '../lib/api';

export function useEventos(filtros = {}) {
  const [eventos, setEventos] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);
  const [pagination, setPagination] = useState(null);

  useEffect(() => {
    const fetchEventos = async () => {
      setLoading(true);
      setError(null);

      try {
        const data = await eventsAPI.listarEventos(filtros);
        setEventos(data.eventos);
        setPagination(data.pagination);
      } catch (err) {
        setError(err.message);
      } finally {
        setLoading(false);
      }
    };

    fetchEventos();
  }, [JSON.stringify(filtros)]);

  return { eventos, loading, error, pagination };
}
```

#### 3. Componente de Búsqueda

```javascript
// components/BuscadorEventos.jsx
import { useState } from 'react';
import { eventsAPI } from '../lib/api';

export function BuscadorEventos() {
  const [pregunta, setPregunta] = useState('');
  const [eventos, setEventos] = useState([]);
  const [loading, setLoading] = useState(false);
  const [error, setError] = useState(null);

  const handleBuscar = async (e) => {
    e.preventDefault();
    
    if (!pregunta.trim()) return;

    setLoading(true);
    setError(null);

    try {
      const resultado = await eventsAPI.buscar(pregunta, '08380', 20);
      setEventos(resultado.eventos);
      
      // Mostrar respuesta en lenguaje natural
      console.log(resultado.respuesta_texto);
    } catch (err) {
      setError(err.message);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="buscador">
      <form onSubmit={handleBuscar}>
        <input
          type="text"
          value={pregunta}
          onChange={(e) => setPregunta(e.target.value)}
          placeholder="¿Qué quieres hacer?"
          disabled={loading}
        />
        <button type="submit" disabled={loading || !pregunta.trim()}>
          {loading ? 'Buscando...' : 'Buscar'}
        </button>
      </form>

      {error && (
        <div className="error">
          ❌ {error}
        </div>
      )}

      <div className="resultados">
        {eventos.map(evento => (
          <EventoCard key={evento.id_unico_evento} evento={evento} />
        ))}
      </div>
    </div>
  );
}
```

#### 4. Componente de Lista con Paginación

```javascript
// components/ListaEventos.jsx
import { useState } from 'react';
import { useEventos } from '../hooks/useEventos';

export function ListaEventos() {
  const [filtros, setFiltros] = useState({
    fecha_desde: new Date().toISOString().split('T')[0],
    limit: 20,
    offset: 0
  });

  const { eventos, loading, error, pagination } = useEventos(filtros);

  const cargarMas = () => {
    setFiltros(prev => ({
      ...prev,
      offset: prev.offset + prev.limit
    }));
  };

  if (loading && eventos.length === 0) {
    return <div>Cargando eventos...</div>;
  }

  if (error) {
    return <div>Error: {error}</div>;
  }

  return (
    <div>
      <div className="eventos-grid">
        {eventos.map(evento => (
          <EventoCard key={evento.id_unico_evento} evento={evento} />
        ))}
      </div>

      {pagination?.has_more && (
        <button onClick={cargarMas} disabled={loading}>
          {loading ? 'Cargando...' : 'Cargar más'}
        </button>
      )}

      <div className="pagination-info">
        Mostrando {eventos.length} de {pagination?.total} eventos
      </div>
    </div>
  );
}
```

#### 5. Componente de Eventos de Hoy

```javascript
// components/EventosHoy.jsx
import { useState, useEffect } from 'react';
import { eventsAPI } from '../lib/api';

export function EventosHoy() {
  const [eventos, setEventos] = useState([]);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    eventsAPI.eventosHoy('Malgrat de Mar', 10)
      .then(data => setEventos(data.eventos))
      .catch(err => console.error(err))
      .finally(() => setLoading(false));
  }, []);

  if (loading) return <div>Cargando...</div>;

  return (
    <div>
      <h2>🎉 Eventos de hoy en Malgrat de Mar</h2>
      {eventos.length === 0 ? (
        <p>No hay eventos programados para hoy</p>
      ) : (
        eventos.map(evento => (
          <EventoCard key={evento.id_unico_evento} evento={evento} />
        ))
      )}
    </div>
  );
}
```

---

## 🎯 Resumen de Implementación

### Cambios a Realizar

#### 1. Versionado (`/api/v1/`)
- Modificar `app/api/routes.py` para incluir prefijo `/api/v1`
- Actualizar `app/main.py` para registrar router con prefijo

#### 2. Nuevos Endpoints
- ✅ `GET /api/v1/events` - Ya existe, mejorar con paginación
- ✅ `GET /api/v1/events/{id}` - Crear nuevo
- ✅ `GET /api/v1/events/today` - Crear nuevo (shortcut)
- ✅ `GET /api/v1/events/upcoming` - Crear nuevo
- ✅ `GET /api/v1/categories` - Crear nuevo

#### 3. Optimizaciones
- Añadir parámetro `limit` a `/query` (default: 20, max: 100)
- Añadir filtros de fecha por default a `/events`
- Implementar paginación con `limit` y `offset`
- Añadir metadata de rendimiento en responses

#### 4. CORS
- Actualizar `allow_origins` para `app.km0lab.com`
- Añadir `expose_headers` para rate limiting

#### 5. Rate Limiting
- Instalar `slowapi`
- Configurar límites por endpoint
- Añadir headers de rate limit

#### 6. Swagger
- Mejorar metadata (descripción, contacto, servers)
- Añadir tags para agrupar endpoints
- Añadir ejemplos completos en cada endpoint

#### 7. Manejo de Errores
- Estandarizar formato de error
- Añadir `request_id` para tracking
- Mejorar mensajes de error

---

## ⏱️ Estimación de Tiempo

| Tarea | Tiempo |
|-------|--------|
| Versionado | 15 min |
| Nuevos endpoints | 45 min |
| Optimizaciones | 30 min |
| CORS | 5 min |
| Rate limiting | 20 min |
| Swagger | 15 min |
| Manejo de errores | 10 min |
| Testing | 20 min |
| **Total** | **~2 horas** |

---

## ✅ Checklist de Implementación

- [ ] Añadir versionado `/api/v1/`
- [ ] Crear endpoint `GET /api/v1/events/{id}`
- [ ] Crear endpoint `GET /api/v1/events/today`
- [ ] Crear endpoint `GET /api/v1/events/upcoming`
- [ ] Crear endpoint `GET /api/v1/categories`
- [ ] Añadir paginación a `/api/v1/events`
- [ ] Añadir parámetro `limit` a `/api/v1/query`
- [ ] Configurar CORS para `app.km0lab.com`
- [ ] Instalar y configurar `slowapi`
- [ ] Añadir rate limiting a endpoints
- [ ] Mejorar metadata de Swagger
- [ ] Añadir tags a endpoints
- [ ] Estandarizar formato de errores
- [ ] Añadir tests para nuevos endpoints
- [ ] Actualizar documentación
- [ ] Deploy a Railway

---

**¿Apruebas esta especificación? ¿Algún ajuste antes de implementar?**
