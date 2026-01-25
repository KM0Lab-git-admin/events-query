# Comparativa de Stack por Fases - Events Query API

**Versión:** 3.1 FINAL  
**Fecha:** Enero 2026

---

## 📊 Tabla Comparativa Completa

| Componente | Fase 1 (MVP) | Fase 2 (Producción) | Fase 3 (Escalado) | Fase 4 (Escala) |
|------------|--------------|---------------------|-------------------|-----------------|
| **Framework Web** | FastAPI 0.115 | FastAPI 0.115 | FastAPI 0.115 | FastAPI 0.115 |
| **Serialización** | ✅ ORJSONResponse | ORJSONResponse | ORJSONResponse | ORJSONResponse |
| **Base de Datos** | ✅ aiomysql (async) | aiomysql | aiomysql | aiomysql |
| **Pooling DB** | ✅ aiomysql pool | aiomysql pool | aiomysql pool | aiomysql pool |
| **Coordenadas** | DECIMAL (Haversine Python) | DECIMAL (Haversine Python) | ✅ POINT + ST_Distance_Sphere | POINT + ST_Distance_Sphere |
| **IA - LLM** | ✅ OpenAI (configurable) | OpenAI (configurable) | OpenAI (configurable) | OpenAI (configurable) |
| **IA - Embeddings** | ✅ text-embedding-3-small | text-embedding-3-small | text-embedding-3-small | text-embedding-3-small |
| **Búsqueda Semántica** | Python (cosine similarity) | Python (cosine similarity) | Python (cosine similarity) | ✅ Vector DB (HNSW) |
| **Retries** | ✅ tenacity | tenacity | tenacity | tenacity |
| **Cache** | - | ✅ Redis | Redis | Redis |
| **Rate Limiting** | - | ✅ Redis | Redis | Redis |
| **Observabilidad** | - | ✅ OpenTelemetry + Prometheus | OpenTelemetry + Prometheus | OpenTelemetry + Prometheus |
| **Testing** | ✅ pytest + pytest-asyncio | pytest + pytest-asyncio | pytest + pytest-asyncio | pytest + pytest-asyncio |
| **CDN** | - | - | ✅ CloudFlare/CloudFront | CloudFlare/CloudFront |
| **Vector DB** | - | - | - | ✅ Qdrant / MySQL 9 VECTOR |
| **Load Balancer** | - | - | - | ✅ Nginx / HAProxy |
| **Escalado** | Single instance | Single instance | Single instance | ✅ Horizontal (múltiples instancias) |

---

## 🔄 Cambios Clave por Fase

### ✅ FASE 1 → FASE 2

**Añadido:**
- Redis (cache + rate limiting)
- OpenTelemetry (observabilidad)
- Prometheus (métricas)
- Logs estructurados

**Impacto:**
- ✅ Reducción 30% latencia (cache hits)
- ✅ Protección contra abuso (rate limiting)
- ✅ Visibilidad completa del sistema

---

### ⏭️ FASE 2 → FASE 3

**Añadido:**
- MySQL GIS (POINT + ST_Distance_Sphere)
- CDN para imágenes
- Índices optimizados

**Impacto:**
- ✅ Reducción 40% tiempo cálculo geográfico
- ✅ Reducción 80% latencia de imágenes
- ✅ Soporta 1000+ eventos sin degradación

---

### ⏭️ FASE 3 → FASE 4

**Añadido:**
- Vector DB (Qdrant o MySQL 9)
- Load balancer
- Escalado horizontal
- Read replicas

**Impacto:**
- ✅ Búsqueda semántica 60% más rápida
- ✅ Soporta 10,000+ eventos
- ✅ Alta disponibilidad
- ✅ Soporta 1000+ req/s

---

## 📈 Performance por Fase

### FASE 1 (MVP) - 125 eventos

```
Extracción parámetros:    500ms
Pre-filtrado SQL:         120ms  ← Async
Búsqueda semántica:       130ms
Respuesta natural:        500ms
Serialización:             30ms  ← ORJSONResponse
Otros:                    100ms
──────────────────────────────
TOTAL:                   1380ms ✅
```

**Throughput:** ~10 req/s (single instance)

---

### FASE 2 (Producción) - 125 eventos

```
Con cache hit (30%):
Extracción parámetros:    500ms
Embedding (cache):          5ms  ← Redis
Pre-filtrado SQL:         120ms
Búsqueda semántica:       130ms
Respuesta natural:        500ms
Serialización:             30ms
──────────────────────────────
TOTAL:                   1285ms ✅

Sin cache hit (70%):
TOTAL:                   1380ms
```

**Throughput:** ~15 req/s (con cache)

---

### FASE 3 (Escalado) - 1000 eventos

```
Extracción parámetros:    500ms
Pre-filtrado SQL:          80ms  ← GIS + índices
Búsqueda semántica:       130ms
Respuesta natural:        500ms
Serialización:             30ms
Otros:                     60ms
──────────────────────────────
TOTAL:                   1300ms ✅
```

**Throughput:** ~20 req/s

---

### FASE 4 (Escala) - 10,000 eventos

```
Extracción parámetros:    500ms
Pre-filtrado SQL:          80ms
Búsqueda vectorial:        50ms  ← Vector DB (HNSW)
Respuesta natural:        500ms
Serialización:             30ms
Otros:                     40ms
──────────────────────────────
TOTAL:                   1200ms ✅
```

**Throughput:** ~100 req/s (con load balancer + 5 instancias)

---

## 💰 Coste Estimado por Fase

### FASE 1 (MVP)
```
Infraestructura:
- 1 servidor (4 vCPU, 8GB RAM): $40/mes
- MySQL 8.0 (managed): $25/mes

OpenAI:
- 1000 queries/día × 30 días = 30,000 queries/mes
- Extracción (gpt-4.1-mini): ~500 tokens × $0.15/1M = $2.25
- Embeddings: ~100 tokens × $0.02/1M = $0.60
- Respuestas (gpt-4.1-mini): ~200 tokens × $0.60/1M = $3.60

TOTAL: ~$72/mes
```

---

### FASE 2 (Producción)
```
Infraestructura:
- 1 servidor (4 vCPU, 8GB RAM): $40/mes
- MySQL 8.0 (managed): $25/mes
- Redis (managed): $15/mes

OpenAI (con 30% cache hit):
- Extracción: $2.25
- Embeddings: $0.42 (30% ahorrado)
- Respuestas: $3.60

Observabilidad:
- Grafana Cloud (free tier): $0

TOTAL: ~$87/mes
```

---

### FASE 3 (Escalado)
```
Infraestructura:
- 1 servidor (8 vCPU, 16GB RAM): $80/mes
- MySQL 8.0 (managed, más potente): $50/mes
- Redis: $15/mes
- CDN (CloudFlare): $20/mes

OpenAI: $6.27 (mismo volumen)

TOTAL: ~$171/mes
```

---

### FASE 4 (Escala)
```
Infraestructura:
- 5 servidores (load balanced): $200/mes
- MySQL 8.0 (read replicas): $150/mes
- Redis: $30/mes
- Vector DB (Qdrant Cloud): $100/mes
- CDN: $50/mes

OpenAI (10x volumen): $62.70

TOTAL: ~$593/mes
```

---

## 🎯 Recomendaciones por Escenario

### Si tienes < 100 usuarios/día:
👉 **FASE 1** es suficiente

### Si tienes 100-1000 usuarios/día:
👉 **FASE 2** (añadir Redis + observabilidad)

### Si tienes 1000-5000 usuarios/día:
👉 **FASE 3** (optimizar BD + CDN)

### Si tienes > 5000 usuarios/día:
👉 **FASE 4** (vector DB + escalado horizontal)

---

## 📋 Checklist de Migración entre Fases

### FASE 1 → FASE 2

- [ ] Desplegar Redis (Docker o managed)
- [ ] Implementar cache de embeddings
- [ ] Implementar rate limiting
- [ ] Configurar OpenTelemetry
- [ ] Configurar Prometheus + Grafana
- [ ] Añadir logs estructurados
- [ ] Configurar alertas
- [ ] Testing de carga

**Tiempo estimado:** 1-2 semanas

---

### FASE 2 → FASE 3

- [ ] Backup completo de BD
- [ ] Migrar coordenadas a POINT
- [ ] Actualizar queries con ST_Distance_Sphere
- [ ] Crear índices espaciales
- [ ] Configurar CDN
- [ ] Migrar imágenes a CDN
- [ ] Testing de performance
- [ ] Rollback plan

**Tiempo estimado:** 2-3 semanas

---

### FASE 3 → FASE 4

- [ ] Evaluar Vector DB (Qdrant vs MySQL 9)
- [ ] Desplegar Vector DB
- [ ] Implementar sincronización BD → Vector DB
- [ ] Migrar embeddings existentes
- [ ] Actualizar lógica de búsqueda
- [ ] Configurar load balancer
- [ ] Desplegar múltiples instancias
- [ ] Configurar read replicas
- [ ] Testing de alta carga
- [ ] Plan de rollback

**Tiempo estimado:** 1-2 meses

---

## ✅ Conclusión

**Decisión Final:**

- **Empezar con FASE 1** (MVP con async + ORJSONResponse + testing)
- **Migrar a FASE 2** cuando tengas usuarios reales (Redis + observabilidad)
- **Migrar a FASE 3** solo si creces a 1000+ eventos
- **Migrar a FASE 4** solo si creces a 5000+ eventos

**Justificación:**
- Cada fase añade complejidad solo cuando es necesaria
- Evita sobre-ingeniería prematura
- Permite iterar rápido en MVP
- Escalado gradual según tracción real

---

*Comparativa creada: Enero 2026*  
*Versión: 3.1 FINAL*
