# 🏗️ Arquitectura - Events Query API

**Versión:** 1.0  
**Última actualización:** Enero 2026

---

> 🔀 **Dual router (estado actual)**  
> - Legacy: `/query`, `/events/list`, `/events/simple`, etc.  
> - v1: `/api/v1/query`, `/api/v1/events`, etc.  
> Ver detalles en [API.md](./API.md).


> 📌 **Docs relacionados (documentación unificada)**  
> - [API (Legacy + v1)](./API.md)  
> - [Deploy en Railway](./DEPLOYMENT.md)  
> - [Arquitectura](./ARCHITECTURE.md)  
> - [Modelo de datos + Ingesta IA](./DATA_MODEL.md)  
> - [Desarrollo](./DEVELOPMENT.md)  
> - [Troubleshooting](./TROUBLESHOOTING.md)


## 📋 Tabla de Contenidos

1. [Visión General](#visión-general)
2. [Arquitectura del Sistema](#arquitectura-del-sistema)
3. [Backend](#backend)
4. [Frontend](#frontend)
5. [Base de Datos](#base-de-datos)
6. [Flujo de Búsqueda](#flujo-de-búsqueda)
7. [Sistema de Análisis](#sistema-de-análisis)
8. [Decisiones Arquitectónicas](#decisiones-arquitectónicas)

---

## Visión General

Events Query API es un sistema de búsqueda inteligente que combina:

- **Búsqueda en lenguaje natural** con OpenAI GPT-4.1-mini
- **Búsqueda semántica** con embeddings (text-embedding-3-small)
- **Búsqueda geográfica** por código postal y radio
- **Respuestas naturales** generadas por IA
- **Análisis detallado** para diagnóstico y mejora

### Arquitectura de Alto Nivel

```
┌──────────────────────────────────────────────────────────┐
│                        USUARIO                           │
│  "¿Qué hacer este fin de semana con niños?"              │
│  CP: 08380                                               │
└────────────────────────┬─────────────────────────────────┘
                         │ HTTP
                         ▼
┌──────────────────────────────────────────────────────────┐
│                   FRONTEND (React)                       │
│  • EventsList: Lista de eventos disponibles              │
│  • QueryChat: Chat de consultas                          │
│  • AnalysisView: Análisis detallado                      │
└────────────────────────┬─────────────────────────────────┘
                         │ REST API
                         ▼
┌──────────────────────────────────────────────────────────┐
│                  BACKEND (FastAPI)                       │
│                                                          │
│  ┌────────────────────────────────────────────────────┐ │
│  │  API Layer (routes.py)                             │ │
│  │  • POST /query - Búsqueda principal                │ │
│  │  • GET /events/simple - Lista eventos              │ │
│  │  • GET /health - Health check                      │ │
│  └────────────────────────────────────────────────────┘ │
│                         │                                │
│  ┌────────────────────────────────────────────────────┐ │
│  │  Services Layer                                    │ │
│  │  • events_service.py - Orquestador principal       │ │
│  │  • ai_service.py - OpenAI integration              │ │
│  │  • database.py - MySQL connection pool             │ │
│  │  • query_builder.py - SQL query builder            │ │
│  │  • analysis_service.py - Análisis detallado        │ │
│  └────────────────────────────────────────────────────┘ │
│                         │                                │
│  ┌────────────────────────────────────────────────────┐ │
│  │  Models Layer (schemas.py)                         │ │
│  │  • QueryRequest, QueryResponse                     │ │
│  │  • Evento, ExtractedParameters                     │ │
│  └────────────────────────────────────────────────────┘ │
└────────────────────────┬─────────────────────────────────┘
                         │
         ┌───────────────┼───────────────┐
         │               │               │
         ▼               ▼               ▼
┌─────────────┐  ┌─────────────┐  ┌─────────────┐
│   MySQL     │  │   OpenAI    │  │  Analysis   │
│   8.0       │  │   API       │  │  Service    │
│             │  │             │  │             │
│ • 8 tablas  │  │ • GPT-4.1   │  │ • Similitud │
│ • Eventos   │  │ • Embeddings│  │ • Diagnóstico│
│ • CPs       │  │             │  │ • Propuestas│
└─────────────┘  └─────────────┘  └─────────────┘
```

---

## Backend

### Stack Tecnológico

| Componente | Tecnología | Versión | Propósito |
|------------|------------|---------|-----------|
| **Framework** | FastAPI | 0.115 | API REST moderna y rápida |
| **Servidor** | Uvicorn | Latest | Servidor ASGI |
| **Validación** | Pydantic | 2.x | Validación de datos |
| **BD Driver** | aiomysql | Latest | MySQL async con pooling |
| **IA** | OpenAI | Latest | GPT-4.1-mini + embeddings |
| **JSON** | ORJSONResponse | Latest | Serialización ultra-rápida |
| **Retries** | tenacity | Latest | Retries con backoff |

### Estructura de Directorios

```
app/
├── __init__.py
├── main.py                 # Aplicación FastAPI principal
├── config.py               # Configuración (env vars)
├── api/
│   ├── __init__.py
│   └── routes.py           # Endpoints REST
├── models/
│   ├── __init__.py
│   └── schemas.py          # Modelos Pydantic
└── services/
    ├── __init__.py
    ├── events_service.py   # Orquestador principal
    ├── ai_service.py       # OpenAI integration
    ├── database.py         # MySQL connection pool
    ├── query_builder.py    # SQL query builder
    └── analysis_service.py # Análisis detallado
```

### Servicios Principales

#### 1. **events_service.py** - Orquestador Principal

Coordina todo el flujo de búsqueda:

```python
async def search_events(request: QueryRequest) -> QueryResponse:
    # 1. Extraer parámetros con IA
    params = await ai_service.extract_parameters(...)
    
    # 2. Calcular CPs en radio
    codigos_postales = await db_service.get_codigos_postales_in_radius(...)
    
    # 3. Pre-filtrado SQL
    eventos_raw = await db_service.execute_query(...)
    
    # 4. Búsqueda semántica
    eventos_filtrados = await self._semantic_search(...)
    
    # 5. Generar respuesta natural
    respuesta_texto = await ai_service.generate_response(...)
    
    # 6. Análisis detallado (si debug=true)
    analisis = await analysis_service.analyze_batch(...)
    
    return QueryResponse(...)
```

#### 2. **ai_service.py** - OpenAI Integration

Interactúa con OpenAI para:

- **Extracción de parámetros**: Convierte lenguaje natural a parámetros estructurados
- **Generación de embeddings**: Crea vectores de 1536 dimensiones
- **Respuestas naturales**: Genera texto explicativo
- **Retries automáticos**: Maneja errores de API con backoff exponencial

```python
async def extract_parameters(pregunta: str, cp_usuario: str) -> ExtractedParameters:
    # Usa GPT-4.1-mini con function calling
    # Retorna: idioma, conceptos, fechas, categorías, radio_km, etc.
    
async def generate_embedding(text: str) -> List[float]:
    # Usa text-embedding-3-small
    # Retorna: vector de 1536 dimensiones
    
async def generate_response(eventos: List[Dict], pregunta: str, idioma: str) -> str:
    # Usa GPT-4.1-mini para generar respuesta natural
```

#### 3. **database.py** - MySQL Connection Pool

Gestiona conexiones a MySQL con pooling:

```python
class DatabaseService:
    def __init__(self):
        self.pool = None  # aiomysql.Pool
        
    async def initialize(self):
        # Crea connection pool
        self.pool = await aiomysql.create_pool(
            minsize=5,
            maxsize=20,
            ...
        )
    
    async def execute_query(self, query: str, params: tuple):
        # Ejecuta query con parámetros
        async with self.pool.acquire() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cursor:
                await cursor.execute(query, params)
                return await cursor.fetchall()
```

#### 4. **query_builder.py** - SQL Query Builder

Construye queries SQL dinámicas:

```python
def build_events_query(codigos_postales: List[str], params: ExtractedParameters):
    # Construye query con filtros:
    # • CP_Evento IN (...)
    # • Fecha BETWEEN ... AND ...
    # • Categorías (si se especifican)
    # • Estado = 'ACTIVO'
    # NO filtra por tags (se hace después con búsqueda semántica)
```

#### 5. **analysis_service.py** - Análisis Detallado

Sistema de diagnóstico para entender decisiones de la IA:

```python
async def analyze_event_similarity(evento, pregunta_embedding, conceptos, umbral):
    # Analiza similitud por:
    # • Tag individual
    # • Categoría
    # • Descripción
    
    # Genera diagnóstico:
    # • Problemas detectados
    # • Soluciones propuestas
    # • Score estimado con mejoras
```

---

## Frontend

### Stack Tecnológico

| Componente | Tecnología | Versión |
|------------|------------|---------|
| **Framework** | React | 18+ |
| **Build Tool** | Vite | 5+ |
| **Package Manager** | pnpm | Latest |
| **Styling** | CSS-in-JS | - |

### Estructura

```
frontend/
├── src/
│   ├── main.jsx           # Entry point
│   ├── App.jsx            # Componente principal
│   ├── EventsList.jsx     # Lista de eventos
│   ├── QueryChat.jsx      # Chat de consultas
│   ├── AnalysisView.jsx   # Análisis detallado
│   └── index.css          # Estilos globales
├── index.html
├── vite.config.js
└── package.json
```

### Componentes Principales

#### 1. **App.jsx** - Componente Principal

Gestiona estado global y renderiza componentes:

```jsx
function App() {
  const [analysisData, setAnalysisData] = useState(null)
  
  return (
    <div>
      <EventsList />
      <QueryChat onAnalysisUpdate={setAnalysisData} />
      {analysisData && <AnalysisView analisis={analysisData} />}
    </div>
  )
}
```

#### 2. **EventsList.jsx** - Lista de Eventos

Muestra eventos disponibles en la BD:

- Fetch a `/events/simple`
- Estadísticas (total, gratuitos)
- Lista scrollable

#### 3. **QueryChat.jsx** - Chat de Consultas

Interfaz para hacer preguntas:

- Input de pregunta
- Input de código postal
- Botón de búsqueda
- Visualización de respuesta
- JSON expandible

#### 4. **AnalysisView.jsx** - Análisis Detallado

Visualiza análisis paso a paso:

- Vista expandible de eventos
- Barras de similitud por tag
- Similitud por categoría
- Problemas detectados
- Soluciones propuestas
- Score estimado

---

## Base de Datos

### Esquema MySQL

**8 tablas relacionales:**

```sql
EVENTOS_MASTER          -- Tabla principal de eventos
├── ID_Unico_Evento (PK)
├── Titulo_ES, Titulo_CAT
├── Desc_Corta_ES, Desc_Corta_CAT
├── Desc_Larga_ES, Desc_Larga_CAT
├── CP_Evento (FK)
├── Poblacion_Nombre
├── Lugar_Nombre
├── Direccion_Fisica
├── Es_Gratuito
├── Precio_Euros
├── Tags_ES (JSON)
├── Tags_CAT (JSON)
├── Tags_Embedding_ES (JSON - 1536 dims)
├── Tags_Embedding_CAT (JSON - 1536 dims)
├── Link_Entradas_Inscripcion
├── Imagen_Principal_URL
├── Estado
└── Fecha_Creacion

EVENTO_HORARIOS         -- Horarios de eventos
├── ID_Horario (PK)
├── ID_Unico_Evento (FK)
├── Fecha_Inicio
├── Fecha_Fin
├── Hora_Inicio
└── Hora_Fin

CATEGORIAS              -- Categorías de eventos
├── ID_Categoria (PK)
└── Nombre_Categoria

EVENTO_CATEGORIAS       -- Relación N:M eventos-categorías
├── ID_Unico_Evento (FK)
└── ID_Categoria (FK)

CODIGOS_POSTALES        -- Códigos postales con coordenadas
├── CP (PK)
├── Poblacion_Nombre
├── Latitud
└── Longitud

POBLACIONES             -- Poblaciones
├── ID_Poblacion (PK)
├── Nombre_Poblacion
└── Provincia

ORGANIZADORES           -- Organizadores de eventos
├── ID_Organizador (PK)
├── Nombre_Organizador
└── Contacto_Email

EVENTO_ORGANIZADORES    -- Relación N:M eventos-organizadores
├── ID_Unico_Evento (FK)
└── ID_Organizador (FK)
```

### Índices

```sql
-- Índices para performance
CREATE INDEX idx_cp_evento ON EVENTOS_MASTER(CP_Evento);
CREATE INDEX idx_estado ON EVENTOS_MASTER(Estado);
CREATE INDEX idx_fecha_inicio ON EVENTO_HORARIOS(Fecha_Inicio);
CREATE INDEX idx_cp ON CODIGOS_POSTALES(CP);
```

---

## Flujo de Búsqueda

### Diagrama Completo

```
┌─────────────────────────────────────────┐
│            USUARIO                      │
│  "Actividades para niños al aire libre  │
│   este fin de semana"                   │
│  CP: "08380"                            │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│    PASO 1: EXTRACCIÓN DE PARÁMETROS     │
│    (OpenAI GPT-4.1-mini)                │
│                                         │
│  Input: "Actividades para niños..."     │
│  Output:                                │
│  {                                      │
│    "idioma": "es",                      │
│    "conceptos": ["niños", "aire libre"],│
│    "fechas": ["2026-01-25", "2026-01-26"],│
│    "categorias": ["infantil"],          │
│    "radio_km": null                     │
│  }                                      │
│                                         │
│  Tiempo: ~500ms                         │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│    PASO 2: CÁLCULO GEOGRÁFICO           │
│                                         │
│  Input: CP="08380", radio=null          │
│  Output: CPs = ["08380"]                │
│                                         │
│  Si radio=20km:                         │
│  • Busca CPs en radio de 20km          │
│  • Calcula distancias con Haversine    │
│                                         │
│  Tiempo: ~50ms                          │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│    PASO 3: PRE-FILTRADO SQL             │
│                                         │
│  Construye query con filtros:           │
│  • CP_Evento IN ('08380')               │
│  • Fecha BETWEEN '2026-01-25' AND ...   │
│  • Categorías (si se especifican)       │
│  • Estado = 'ACTIVO'                    │
│                                         │
│  Resultado: 50 eventos                  │
│  Tiempo: ~120ms                         │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│    PASO 4: BÚSQUEDA SEMÁNTICA           │
│                                         │
│  Para cada evento:                      │
│  1. Extrae Tags_Embedding_ES (1536 dims)│
│  2. Genera embedding de conceptos       │
│  3. Calcula similitud (coseno)          │
│  4. Filtra por umbral (>= 0.4)          │
│                                         │
│  Resultado: 10 eventos relevantes       │
│  Tiempo: ~130ms                         │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│    PASO 5: RESPUESTA NATURAL            │
│    (OpenAI GPT-4.1-mini)                │
│                                         │
│  Input: 10 eventos + pregunta original  │
│  Output: Texto natural explicativo      │
│                                         │
│  "He encontrado 10 eventos perfectos    │
│   para niños este fin de semana..."     │
│                                         │
│  Tiempo: ~500ms                         │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│    PASO 6: ANÁLISIS DETALLADO           │
│    (si debug=true)                      │
│                                         │
│  Para cada evento (primeros 20):        │
│  • Similitud por tag individual         │
│  • Similitud por categoría              │
│  • Similitud por descripción            │
│  • Diagnóstico de problemas             │
│  • Propuestas de mejora                 │
│                                         │
│  Tiempo: ~2000ms                        │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│           RESPUESTA FINAL               │
│                                         │
│  {                                      │
│    "respuesta_texto": "...",            │
│    "eventos": [...],                    │
│    "total": 10,                         │
│    "idioma_respuesta": "es",            │
│    "debug_info": {                      │
│      "parametros_extraidos": {...},     │
│      "analisis_detallado": [...]        │
│    }                                    │
│  }                                      │
│                                         │
│  Tiempo total: ~1400ms (sin debug)      │
│  Tiempo total: ~3400ms (con debug)      │
└─────────────────────────────────────────┘
```

---

## Sistema de Análisis

### Propósito

Entender **por qué** la IA toma cada decisión y **cómo mejorar** la precisión del sistema.

### Componentes

#### 1. **Análisis de Similitud**

Para cada evento, calcula:

- **Similitud por tag individual**: Qué tags aportan más
- **Similitud por categoría**: Si la categoría es relevante
- **Similitud por descripción**: Relevancia de la descripción

#### 2. **Diagnóstico Automático**

Detecta 5 tipos de problemas:

1. **SCORE_BAJO**: No pasa el umbral
2. **CATEGORIA_IRRELEVANTE**: Categoría con similitud < 0.3
3. **TAGS_INSUFICIENTES**: Pocos tags relevantes
4. **DESCRIPCION_POCO_RELEVANTE**: Descripción no aporta
5. **SIN_EMBEDDING**: Falta generar embedding

#### 3. **Propuestas de Mejora**

Sugiere 4 tipos de soluciones:

1. **cambiar_categoria**: Con categoría sugerida
2. **añadir_tags**: Con lista de tags sugeridos
3. **mejorar_descripcion**: Con palabras clave
4. **generar_embedding**: Si falta

Cada propuesta incluye:
- **Prioridad**: CRÍTICA, ALTA, MEDIA, BAJA
- **Impacto estimado**: +0.20, +0.15, etc.
- **Score estimado**: Score después de aplicar mejoras

---

## Decisiones Arquitectónicas

### 1. **Tags y Embeddings Separados por Idioma** ⭐

**Decisión:** Almacenar tags y embeddings por separado para español y catalán.

**Justificación:**
- ✅ 50% más rápido (solo consulta un embedding)
- ✅ Mayor precisión (no mezcla idiomas)
- ✅ API detecta idioma automáticamente

**Implementación:**
```sql
Tags_ES JSON NULL
Tags_CAT JSON NULL
Tags_Embedding_ES JSON NULL    -- Vector 1536 dims
Tags_Embedding_CAT JSON NULL   -- Vector 1536 dims
```

### 2. **Búsqueda en Dos Fases**

**Decisión:** Pre-filtrado SQL + búsqueda semántica.

**Justificación:**
- ✅ Reduce eventos a analizar (50 en lugar de 1000)
- ✅ Búsqueda semántica solo en eventos relevantes
- ✅ Performance < 1.5 segundos

**Flujo:**
1. SQL filtra por CP, fecha, categoría → 50 eventos
2. Búsqueda semántica filtra por similitud → 10 eventos

### 3. **Connection Pooling**

**Decisión:** aiomysql con pool de 5-20 conexiones.

**Justificación:**
- ✅ Reutiliza conexiones (no crea/destruye en cada request)
- ✅ Previene agotamiento de conexiones
- ✅ Mejor performance bajo carga

### 4. **Async/Await en Todo el Stack**

**Decisión:** FastAPI + aiomysql + httpx (async).

**Justificación:**
- ✅ No bloquea threads en I/O
- ✅ Mayor throughput (~10 req/s vs ~3 req/s)
- ✅ Mejor uso de recursos

### 5. **ORJSONResponse**

**Decisión:** Usar orjson en lugar de json estándar.

**Justificación:**
- ✅ 2-3x más rápido que json estándar
- ✅ Serializa Decimal, datetime automáticamente
- ✅ Ahorra ~30ms por request

### 6. **Umbral de Similitud 0.4**

**Decisión:** Filtrar eventos con similitud >= 0.4.

**Justificación:**
- ✅ Balance entre precisión y recall
- ✅ 0.3 = demasiados falsos positivos
- ✅ 0.5 = demasiados falsos negativos

**Configurable en:** `app/services/events_service.py` línea 152

### 7. **Sistema de Análisis Opcional**

**Decisión:** Análisis detallado solo si `debug=true`.

**Justificación:**
- ✅ No impacta performance en producción
- ✅ Útil para desarrollo y mejora
- ✅ Añade ~2 segundos al tiempo de respuesta

---

## Performance

### Objetivo

- **< 3 segundos** de respuesta
- **~10 req/s** de throughput (single instance)

### Performance Actual

| Operación | Tiempo |
|-----------|--------|
| Extracción parámetros (IA) | 500ms |
| Cálculo geográfico | 50ms |
| Pre-filtrado SQL | 120ms |
| Búsqueda semántica | 130ms |
| Respuesta natural (IA) | 500ms |
| Serialización | 30ms |
| Otros | 70ms |
| **TOTAL (sin debug)** | **1400ms** ✅ |
| **TOTAL (con debug)** | **3400ms** |

### Optimizaciones Aplicadas

1. ✅ Connection pooling (aiomysql)
2. ✅ ORJSONResponse (2-3x más rápido)
3. ✅ Async/Await (no bloquea threads)
4. ✅ Índices en BD (CP, Estado, Fecha)
5. ✅ Pre-filtrado SQL (reduce eventos a analizar)
6. ✅ Embeddings pre-calculados (no se generan en runtime)

### Optimizaciones Futuras (Fase 2)

- [ ] Redis para cache de embeddings
- [ ] CDN para imágenes
- [ ] Compresión gzip/brotli
- [ ] HTTP/2

---

## Seguridad

### Medidas Implementadas

1. ✅ **SQL parametrizado**: Previene SQL injection
2. ✅ **Validación Pydantic**: Valida todos los inputs
3. ✅ **Connection pooling**: Previene agotamiento de conexiones
4. ✅ **Timeouts**: OpenAI con timeout de 30s
5. ✅ **Retries con backoff**: Maneja errores de API
6. ✅ **CORS configurado**: Solo orígenes permitidos

### Medidas Futuras (Fase 2)

- [ ] Rate limiting (por IP)
- [ ] Autenticación JWT
- [ ] HTTPS obligatorio
- [ ] Logs de auditoría

---

## Escalabilidad

### Actual (Single Instance)

- **Throughput**: ~10 req/s
- **Latencia**: ~1.4s
- **Conexiones BD**: 5-20 (pool)

### Escalabilidad Horizontal (Fase 2)

```
┌────────────┐
│ Load       │
│ Balancer   │
└──────┬─────┘
       │
   ┌───┴───┬───────┬───────┐
   │       │       │       │
   ▼       ▼       ▼       ▼
┌─────┐ ┌─────┐ ┌─────┐ ┌─────┐
│ API │ │ API │ │ API │ │ API │
│  1  │ │  2  │ │  3  │ │  4  │
└──┬──┘ └──┬──┘ └──┬──┘ └──┬──┘
   │       │       │       │
   └───────┴───┬───┴───────┘
               │
         ┌─────┴─────┐
         │           │
         ▼           ▼
    ┌────────┐  ┌────────┐
    │ MySQL  │  │ Redis  │
    │ Master │  │ Cache  │
    └────────┘  └────────┘
```

**Capacidad estimada:** ~40 req/s (4 instancias)

---

## Monitoreo (Fase 2)

### Métricas Clave

- **Latencia**: p50, p95, p99
- **Throughput**: req/s
- **Errores**: tasa de error (%)
- **OpenAI**: llamadas, latencia, errores
- **BD**: queries, latencia, conexiones

### Stack Propuesto

- **Prometheus**: Métricas
- **Grafana**: Dashboards
- **OpenTelemetry**: Tracing distribuido
- **Loki**: Logs centralizados

---

## Conclusión

Events Query API es un sistema moderno, escalable y bien arquitecturado que combina lo mejor de:

- **FastAPI** para APIs rápidas y modernas
- **OpenAI** para IA generativa y búsqueda semántica
- **MySQL** para datos relacionales
- **React** para UI interactiva
- **Sistema de análisis** para mejora continua

La arquitectura está diseñada para:
- ✅ Performance (< 1.5s)
- ✅ Escalabilidad (horizontal)
- ✅ Mantenibilidad (código limpio)
- ✅ Observabilidad (logs, métricas)

---

**Próximos pasos:** Ver [`DEVELOPMENT.md`](DEVELOPMENT.md) para guía de desarrollo.