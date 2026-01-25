# Roadmap de Implementación - Events Query API

**Versión:** 3.1 FINAL  
**Fecha:** Enero 2026  
**Basado en:** Observaciones técnicas del usuario

---

## 📊 Análisis de Observaciones

He analizado tus 6 observaciones técnicas y las he clasificado por **impacto**, **complejidad** y **urgencia** para decidir en qué fase implementar cada una.

---

## 🎯 Clasificación de Mejoras

### Observación 1: DB Async + Pooling Real
**Descripción:** Pasar de MySQL Connector/Python síncrono a async con pooling.

**Análisis:**
- **Impacto:** 🔴 ALTO (concurrencia real, evita bloquear event loop)
- **Complejidad:** 🟡 MEDIA (cambio de driver + refactor de queries)
- **Urgencia:** 🟡 MEDIA (crítico si hay múltiples usuarios simultáneos)

**Decisión:** ✅ **FASE 1 (MVP)** - Es fundamental para FastAPI

**Justificación:**
- FastAPI es async por diseño, mezclar con DB síncrona es anti-patrón
- Con 5-10 usuarios simultáneos ya se nota el cuello de botella
- El cambio es relativamente simple si se hace desde el principio

---

### Observación 2: ORJSONResponse
**Descripción:** Usar ORJSONResponse para serialización más rápida.

**Análisis:**
- **Impacto:** 🟢 MEDIO (mejora latencia de serialización)
- **Complejidad:** 🟢 BAJA (cambio trivial en FastAPI)
- **Urgencia:** 🟢 BAJA (mejora incremental)

**Decisión:** ✅ **FASE 1 (MVP)** - Es trivial de implementar

**Justificación:**
- Cambio de 2 líneas de código
- Mejora gratuita de performance (10-30% en serialización)
- No tiene desventajas

---

### Observación 3: Haversine en MySQL con GIS
**Descripción:** Mover cálculo de distancia a MySQL con ST_Distance_Sphere().

**Análisis:**
- **Impacto:** 🟡 MEDIO (solo si escalas a miles de eventos)
- **Complejidad:** 🟡 MEDIA (cambio de esquema + queries)
- **Urgencia:** 🔵 BAJA (con 125 eventos no es necesario)

**Decisión:** ⏭️ **FASE 3 (Escalado)** - Solo si creces a 1000+ eventos

**Justificación:**
- Con 125 eventos, Haversine en Python es suficiente (~50ms)
- Requiere cambio de esquema (POINT con SRID)
- Beneficio real solo con volumen alto

---

### Observación 4: Vector Search (Qdrant/MySQL 9)
**Descripción:** Usar vector DB o MySQL 9 con tipo VECTOR para búsqueda semántica.

**Análisis:**
- **Impacto:** 🔴 ALTO (solo si escalas a miles de eventos)
- **Complejidad:** 🔴 ALTA (nueva infraestructura o migración MySQL 9)
- **Urgencia:** 🔵 BAJA (con pre-filtrado a 15 eventos no es necesario)

**Decisión:** ⏭️ **FASE 4 (Producción a Escala)** - Solo si creces a 5000+ eventos

**Justificación:**
- Tu diseño de pre-filtrado SQL → 15 eventos → similitud en Python es óptimo para MVP
- Vector DB añade complejidad de infraestructura
- MySQL 9 aún no está ampliamente adoptado
- Beneficio real solo cuando pre-filtrado devuelva 100+ eventos

---

### Observación 5: OpenAI Robusto y Swap-Friendly
**Descripción:** Modelo configurable, retries, timeouts, cache de embeddings.

**Análisis:**
- **Impacto:** 🔴 ALTO (robustez, costes, latencia)
- **Complejidad:** 🟡 MEDIA (varias mejoras incrementales)
- **Urgencia:** 🟡 MEDIA (importante para producción)

**Decisión:** 
- ✅ **FASE 1 (MVP):** Modelo configurable + timeouts + retries
- ⏭️ **FASE 2 (Producción):** Cache de embeddings con Redis

**Justificación:**
- Modelo configurable es trivial (env var)
- Timeouts y retries son críticos (OpenAI puede fallar)
- Cache de embeddings requiere Redis (añadir en Fase 2)

---

### Observación 6: Redis + Observabilidad + Testing
**Descripción:** Redis (cache + rate limiting), OpenTelemetry, pytest.

**Análisis:**
- **Impacto:** 🔴 ALTO (robustez, monitoreo, calidad)
- **Complejidad:** 🟡 MEDIA (varias piezas)
- **Urgencia:** 🟡 MEDIA (crítico para producción)

**Decisión:**
- ✅ **FASE 1 (MVP):** Testing (pytest + integración)
- ⏭️ **FASE 2 (Producción):** Redis + Observabilidad

**Justificación:**
- Testing es fundamental desde el principio (bilingüismo, filtrado)
- Redis y observabilidad son críticos para producción pero no para MVP
- Mejor iterar rápido en MVP y añadir infraestructura después

---

## 🗺️ Roadmap por Fases

### ✅ FASE 1: MVP (Implementación Inmediata)

**Objetivo:** Sistema funcional con buenas prácticas desde el principio.

**Stack Actualizado:**
```python
# Backend
fastapi==0.115.0
uvicorn[standard]==0.30.0
pydantic==2.8.0
orjson==3.9.0  # ← NUEVO: Serialización rápida

# Base de Datos
aiomysql==0.2.0  # ← NUEVO: MySQL async
mysql-connector-python  # Mantener para scripts de setup

# IA
openai==1.40.0
python-dotenv==1.0.1
tenacity==8.2.3  # ← NUEVO: Retries con backoff

# Testing
pytest==7.4.3  # ← NUEVO
pytest-asyncio==0.21.1  # ← NUEVO
```

**Cambios Implementados:**

1. **✅ DB Async + Pooling**
   - Usar `aiomysql` con connection pooling
   - Todas las queries async
   - Configuración de pool (min=5, max=20)

2. **✅ ORJSONResponse**
   - FastAPI configurado con ORJSONResponse por defecto
   - Mejora 10-30% en serialización

3. **✅ OpenAI Robusto**
   - Modelo configurable por env var (`OPENAI_MODEL`, `OPENAI_EMBEDDING_MODEL`)
   - Retries con backoff exponencial (tenacity)
   - Timeouts configurables (30s extracción, 10s embeddings)

4. **✅ Testing**
   - pytest con tests unitarios
   - Tests de integración con MySQL (testcontainers)
   - Tests de bilingüismo (español/catalán)
   - Tests de filtrado geográfico

**Performance Esperada:**
```
Extracción parámetros:    500ms
Pre-filtrado SQL:         120ms  ← Mejora (async)
Búsqueda semántica:       130ms
Respuesta natural:        500ms
Serialización JSON:        30ms  ← Mejora (orjson)
Otros:                    100ms
──────────────────────────────
TOTAL:                   1380ms ✅ < 3 segundos
```

**Entregables:**
- ✅ API funcional con Swagger
- ✅ BD MySQL con 125 eventos fake
- ✅ Tests unitarios e integración
- ✅ Documentación actualizada
- ✅ Docker Compose para desarrollo

---

### ⏭️ FASE 2: Producción (1-2 meses después)

**Objetivo:** Sistema robusto para usuarios reales con cache y monitoreo.

**Nuevas Dependencias:**
```python
redis==5.0.1  # Cache + rate limiting
opentelemetry-api==1.21.0  # Observabilidad
opentelemetry-instrumentation-fastapi==0.42b0
prometheus-client==0.19.0  # Métricas
```

**Cambios Implementados:**

1. **✅ Redis**
   - Cache de embeddings de consultas frecuentes
   - Rate limiting por IP/usuario
   - TTL: 1 hora para embeddings, 1 minuto para rate limit

2. **✅ Observabilidad**
   - OpenTelemetry con traces distribuidos
   - Logs estructurados (JSON)
   - Métricas Prometheus:
     - Latencia por endpoint
     - Tasa de aciertos de cache
     - Errores de OpenAI
     - Queries SQL lentas

3. **✅ Mejoras de Robustez**
   - Health checks completos (DB, OpenAI, Redis)
   - Graceful shutdown
   - Circuit breaker para OpenAI
   - Fallback si OpenAI falla (búsqueda solo por categorías)

**Performance Esperada con Cache:**
```
Con cache hit (30% de queries):
- Extracción parámetros:    500ms
- Embedding desde cache:      5ms  ← Mejora 95%
- Pre-filtrado SQL:         120ms
- Búsqueda semántica:       130ms
- Respuesta natural:        500ms
- Serialización:             30ms
──────────────────────────────────
TOTAL:                     1285ms ✅
```

**Entregables:**
- ✅ Redis integrado
- ✅ Dashboards de monitoreo (Grafana)
- ✅ Alertas configuradas
- ✅ Documentación de operación

---

### ⏭️ FASE 3: Escalado (6 meses después, si creces a 1000+ eventos)

**Objetivo:** Optimizar para alto volumen de eventos.

**Cambios Implementados:**

1. **✅ Haversine en MySQL**
   - Migrar coordenadas a tipo `POINT` con SRID 4326
   - Usar `ST_Distance_Sphere()` en queries
   - Índice espacial en coordenadas
   - Beneficio: Filtrado geográfico en BD (más eficiente)

2. **✅ Optimizaciones de BD**
   - Índices compuestos optimizados
   - Particionado de tabla EVENTOS_MASTER por fecha
   - Materialized views para queries frecuentes

3. **✅ CDN para Imágenes**
   - Servir imágenes desde CDN (CloudFlare/AWS CloudFront)
   - Reducir carga en servidor

**Performance Esperada:**
```
Con 1000 eventos:
- Pre-filtrado SQL:          80ms  ← Mejora (GIS + índices)
- Búsqueda semántica:       130ms  (aún 15 eventos)
- TOTAL:                   1200ms ✅
```

**Entregables:**
- ✅ Esquema BD actualizado con GIS
- ✅ Script de migración
- ✅ CDN configurado

---

### ⏭️ FASE 4: Producción a Escala (1 año después, si creces a 5000+ eventos)

**Objetivo:** Búsqueda semántica a escala con vector DB.

**Cambios Implementados:**

1. **✅ Vector Database**
   - Opción A: Qdrant (open source, self-hosted)
   - Opción B: MySQL 9 con tipo VECTOR + HeatWave
   - Índice HNSW para búsqueda vectorial rápida

2. **✅ Arquitectura Híbrida**
   - MySQL: Datos relacionales (eventos, categorías, horarios)
   - Vector DB: Embeddings + búsqueda semántica
   - Sincronización automática

3. **✅ Escalado Horizontal**
   - Múltiples instancias de API (load balancer)
   - Read replicas de MySQL
   - Sharding si es necesario

**Performance Esperada:**
```
Con 10,000 eventos y pre-filtrado a 500:
- Pre-filtrado SQL:          80ms
- Búsqueda vectorial (HNSW): 50ms  ← Mejora 60%
- TOTAL:                   1100ms ✅
```

**Entregables:**
- ✅ Vector DB desplegado
- ✅ Pipeline de sincronización
- ✅ Load balancer configurado

---

## 📊 Resumen de Decisiones

| Mejora | Fase | Justificación |
|--------|------|---------------|
| **DB Async + Pooling** | ✅ Fase 1 | Fundamental para FastAPI, evita anti-patrón |
| **ORJSONResponse** | ✅ Fase 1 | Trivial de implementar, mejora gratuita |
| **OpenAI Configurable** | ✅ Fase 1 | Flexibilidad sin coste |
| **Retries + Timeouts** | ✅ Fase 1 | Robustez básica necesaria |
| **Testing** | ✅ Fase 1 | Calidad desde el principio |
| **Redis Cache** | ⏭️ Fase 2 | Requiere infraestructura, no crítico para MVP |
| **Observabilidad** | ⏭️ Fase 2 | Importante para producción, no para MVP |
| **Rate Limiting** | ⏭️ Fase 2 | Necesario con usuarios reales |
| **Haversine MySQL** | ⏭️ Fase 3 | Solo si escalas a 1000+ eventos |
| **Vector DB** | ⏭️ Fase 4 | Solo si escalas a 5000+ eventos |

---

## 🎯 Top 3 Cambios Prioritarios (Tu Recomendación)

Estoy de acuerdo con tu top 3:

### 1. ✅ DB Async + Pooling → **FASE 1**
**Razón:** Es la base de una API FastAPI bien hecha.

### 2. ✅ ORJSONResponse → **FASE 1**
**Razón:** Mejora gratuita, trivial de implementar.

### 3. ⏭️ Plan de Vector Search → **FASE 4**
**Razón:** Solo si escalas. Tu diseño actual es óptimo para MVP.

---

## 🔄 Stack Actualizado para FASE 1 (MVP)

### Backend
```python
fastapi==0.115.0
uvicorn[standard]==0.30.0
pydantic==2.8.0
orjson==3.9.0  # Serialización rápida
```

### Base de Datos
```python
aiomysql==0.2.0  # MySQL async con pooling
```

### IA
```python
openai==1.40.0
python-dotenv==1.0.1
tenacity==8.2.3  # Retries con backoff
```

### Testing
```python
pytest==7.4.3
pytest-asyncio==0.21.1
httpx==0.25.2  # Para tests de API
```

---

## 📝 Cambios en la Arquitectura (Fase 1)

### Antes (Documentación Original):
```python
# Síncrono
import mysql.connector

conn = mysql.connector.connect(...)
cursor = conn.cursor()
cursor.execute(query, params)
results = cursor.fetchall()
```

### Después (Fase 1 - Async):
```python
# Asíncrono con pooling
import aiomysql

pool = await aiomysql.create_pool(
    host='localhost',
    port=3306,
    user='user',
    password='pass',
    db='events_db',
    minsize=5,
    maxsize=20
)

async with pool.acquire() as conn:
    async with conn.cursor() as cursor:
        await cursor.execute(query, params)
        results = await cursor.fetchall()
```

### Endpoints FastAPI:
```python
from fastapi import FastAPI
from fastapi.responses import ORJSONResponse

app = FastAPI(default_response_class=ORJSONResponse)

@app.post("/query")
async def query_events(request: QueryRequest):
    # Todo async
    params = await ai_service.extract_parameters(request.pregunta)
    cps = await geo_service.get_cps_in_radius(request.cp_usuario, params.radio_km)
    eventos = await db_service.query_events(cps, params)
    response = await ai_service.generate_response(request.pregunta, eventos)
    return response
```

---

## ✅ Conclusión

**Decisión Final:**

- **FASE 1 (MVP):** DB Async + ORJSONResponse + OpenAI Robusto + Testing
- **FASE 2 (Producción):** Redis + Observabilidad
- **FASE 3 (Escalado):** Haversine MySQL + Optimizaciones
- **FASE 4 (Escala):** Vector DB

**Justificación:**
- Fase 1 incluye mejoras fundamentales sin añadir complejidad excesiva
- Redis y observabilidad son críticos para producción pero no para validar MVP
- Optimizaciones de escalado solo si el producto tiene tracción

**Estado:** ✅ **Roadmap definido y listo para implementación**

---

*Roadmap creado: Enero 2026*  
*Versión: 3.1 FINAL*
