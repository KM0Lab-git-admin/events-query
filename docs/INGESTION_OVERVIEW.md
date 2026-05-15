# 📥 Módulo de Ingesta — Visión general

**Versión:** 1.0
**Última actualización:** 2026-05-15

---

> 📌 **Docs relacionados (módulo de ingesta)**
> - [Visión general](./INGESTION_OVERVIEW.md) ← estás aquí
> - [Modelo de datos del módulo](./INGESTION_DATA_MODEL.md)
> - [Pipeline detallado](./INGESTION_PIPELINE.md)
> - [Optimización y escala](./INGESTION_OPTIMIZATION.md)
> - [Operaciones y observabilidad](./INGESTION_OPERATIONS.md)
>
> 📌 **Docs del proyecto base**
> - [API (Legacy + v1)](./API.md)
> - [Arquitectura](./ARCHITECTURE.md)
> - [Modelo de datos](./DATA_MODEL.md)
> - [Desarrollo](./DEVELOPMENT.md)

---

## 📋 Tabla de contenidos

1. [Propósito y posición en el sistema](#propósito-y-posición-en-el-sistema)
2. [Las tres rutas de captura](#las-tres-rutas-de-captura)
3. [Decisiones arquitectónicas clave](#decisiones-arquitectónicas-clave)
4. [Flujo end-to-end resumido](#flujo-end-to-end-resumido)
5. [Glosario](#glosario)
6. [Roadmap de implementación](#roadmap-de-implementación)

---

## Propósito y posición en el sistema

El módulo de ingesta es el **productor de eventos** del sistema. Su única responsabilidad es alimentar la tabla `EVENTOS_MASTER` (y sus tablas hijas) con eventos reales captados desde fuentes externas, de forma incremental, deduplicada y a coste controlado.

El módulo de consulta (API + búsqueda semántica + frontend) es el **consumidor**: lee de las mismas tablas que el módulo de ingesta escribe, pero no le importa cómo llegaron los eventos ahí. Esta separación es estricta: ningún componente de la API debe llamar al módulo de ingesta en tiempo de request.

```
┌─────────────────────────────────────────────────────────┐
│           Fuentes externas (web, agregadores, redes)    │
└────────────────────────┬────────────────────────────────┘
                         │
                         ▼
┌─────────────────────────────────────────────────────────┐
│           MÓDULO DE INGESTA (este módulo)               │
│                                                         │
│  Scheduler → Conectores → Extractores → Gate → Merge   │
│                              ↓                          │
└──────────────────────────────┼──────────────────────────┘
                               │ writes
                               ▼
┌─────────────────────────────────────────────────────────┐
│   EVENTOS_MASTER + tablas hijas (BD compartida)        │
└──────────────────────────────┬──────────────────────────┘
                               │ reads
                               ▼
┌─────────────────────────────────────────────────────────┐
│        MÓDULO DE CONSULTA (API + frontend)             │
└─────────────────────────────────────────────────────────┘
```

El módulo está pensado para correr como **proceso(s) batch** asíncronos, no como servicio request-response. La unidad de ejecución es el *scrape job*: el scheduler escoge qué fuentes están vencidas, dispara workers que ejecutan el pipeline completo para cada una, y los resultados se persisten transaccionalmente.

A nivel de despliegue (ver [`DEPLOYMENT.md`](./DEPLOYMENT.md)), esto se materializa típicamente como uno o más servicios separados en Railway que comparten la BD MySQL con el servicio de API.

---

## Las tres rutas de captura

El sistema reconoce tres tipos de fuente con perfiles muy distintos de coste, fiabilidad y cobertura. La distinción está reflejada en la enum `Tipo_Fuente` de la tabla `BIBLIOTECA_FUENTES`:

### Ruta A — Web oficial (`FUENTE_OFICIAL`)

Webs públicas de ayuntamientos, patronatos de turismo, casas de cultura. HTML servido sin autenticación.

- **Captura**: Python puro (`httpx` + `BeautifulSoup` o `Playwright` si hay JS pesado). Sin coste por petición.
- **Cascade pre-coste completa**: HEAD/sitemap para detectar cambios, listado para filtrar fechas, hash para evitar reprocesar.
- **Extracción**: parser estructural sobre JSON-LD (`schema.org/Event`), microdata o selectores CSS estables. **Sin LLM en el caso común**. El LLM solo aparece para enriquecer descripciones libres o normalizar tags.
- **Coste por evento**: prácticamente cero.
- **Cobertura**: granular (1 fuente = 1 municipio). Escala como `O(N municipios)`.
- **Calidad de datos**: alta (información de primera mano, descripciones completas, datos correctos).

### Ruta B — Agregador (`AGREGADOR`)

Plataformas que centralizan eventos de muchos municipios: Eventbrite, Meetup, Festacat, agendas de la Diputació, Generalitat Cultura.

- **Captura**: API HTTP o sitemap nacional. Sin coste, o coste por uso de API (la mayoría son gratuitas con rate limits razonables).
- **Cascade pre-coste**: filtro geográfico y temporal **en el propio request** (lat/lng + radio, comarca, ventana de fechas). Es el equivalente al HEAD/sitemap pero más potente porque devuelve solo lo relevante.
- **Extracción**: mapeo declarativo del JSON de respuesta a `EventCandidate`. **Sin LLM**.
- **Coste por evento**: cero.
- **Cobertura**: 1 fuente = N municipios. **Una sola integración con Diputació BCN puede alimentar los 311 municipios de la provincia.** Escala como `O(N agregadores)`, independiente del número de municipios.
- **Calidad de datos**: estandarizada media-alta. A veces faltan detalles que sí están en la web oficial.

### Ruta C — Red social (`RED_SOCIAL_PERFIL`, `RED_SOCIAL_QUERY`)

Cuentas de Instagram, Facebook, X, TikTok de ayuntamientos, organizadores y entidades colaboradoras. Dos sub-modos:

- `RED_SOCIAL_PERFIL`: scrape de los últimos N posts de una cuenta concreta (ej. `@ajmalgrat`).
- `RED_SOCIAL_QUERY`: scrape por hashtag o búsqueda (`#malgratdemar`, `#festamajormalgrat`).

- **Captura**: vía Apify (u otro proveedor de scraping gestionado) porque Meta y X tienen anti-bot agresivo. **Pagas en el momento del scrape**, antes de saber si el contenido es útil.
- **Cascade pre-coste**: muy limitada (Apify no permite filtrar por fecha antes de pedir). La frecuencia de scrape se reduce vía scheduling adaptativo, no vía filtros HTTP.
- **Extracción**: LLM siempre. Texto (caption del post) con un LLM rápido y barato. Imágenes (carteles con info de evento) con un modelo multimodal.
- **Gate pre-LLM**: punto clave. Antes de gastar tokens en un post, se comprueba si el evento que describe ya está en BD por una ruta gratis. Si lo está, se registra como fuente adicional sin re-extraer.
- **Coste por evento útil**: bajo a moderado (Apify ~$0.005/post + LLM ~$0.01–0.05/post según uso de visión).
- **Cobertura**: granular (1 cuenta = 1 entidad). Complementa, no sustituye.
- **Calidad de datos**: variable. Posts informales pueden tener fechas ambiguas, lugar implícito, datos incompletos.

---

## Decisiones arquitectónicas clave

### 1. Separación captura / extracción / persistencia

Cada paso es una capa independiente con un contrato claro. Esto permite:

- **Re-procesar sin re-scrapear**: si mejora el modelo de extracción o el prompt, se vuelve a correr sobre `CAPTURAS_RAW` sin tocar las fuentes externas.
- **Auditar fallos**: si un evento llega malformado, hay forma de rastrear si el error está en captura, extracción o merge.
- **Sustituir componentes**: cambiar de Apify a otro proveedor, o de OpenAI a otro LLM, afecta a una capa sin tocar el resto.

### 2. Cascade de filtros con coste creciente

El pipeline aplica filtros en orden de **coste creciente**: lo barato primero, lo caro al final. Filtros baratos (HEAD HTTP, sitemap, hash de contenido, parseo de listado) descartan típicamente el 70-90% del trabajo antes de gastar dinero. Ver [`INGESTION_OPTIMIZATION.md`](./INGESTION_OPTIMIZATION.md) para el detalle.

### 3. Gate pre-LLM para evitar duplicar gasto

Si un evento ya fue capturado por una ruta gratis (web o agregador), los posts de redes sociales que hablen del mismo evento **no pagan extracción LLM**. Se registran como fuentes adicionales que confirman el evento existente. Este es el mecanismo que hace viable la economía del sistema a escala provincial.

### 4. Multi-fuente por evento

Un evento real puede aparecer en varias fuentes (web del ajuntament + Festacat + IG del organizador). El modelo soporta esta multi-fuente nativamente: `EVENTOS_MASTER` mantiene la fuente *principal* en `Fuente_ID` y `Fuente_URL_Original`, pero existe la tabla `EVENTO_FUENTES` (ver [`INGESTION_DATA_MODEL.md`](./INGESTION_DATA_MODEL.md)) con la lista completa de fuentes que confirman cada evento. Esto es esencial para:

- Trazabilidad VAC 360
- Score de confianza (más fuentes = más confianza)
- Detección de cambios (si una fuente actualiza datos, las otras pueden invalidarlos)

### 5. Imágenes en storage propio

Las URLs de CDN de Instagram, Facebook y otras redes **caducan** en días o semanas. Para que la app pueda mostrar imágenes de eventos pasados o de hace meses, el módulo de ingesta **descarga cada imagen** y la guarda en storage propio (referenciado por `BINARIOS_STORAGE.URL_Almacenamiento_Nube`). El campo `EVENTOS_MASTER.Imagen_Principal_URL` apunta al CDN propio, no al de la red social.

### 6. Captura cruda persistente

Todo lo que se captura desde una fuente externa se almacena tal cual antes de procesarse (`CAPTURAS_RAW`). Esto permite:

- Re-procesar con modelos mejorados sin re-scrapear (ahorro a escala)
- Debug forense de fallos de extracción
- Cumplimiento de auditoría: hay constancia inmutable de qué se vio en cada fuente y cuándo

### 7. Solo eventos futuros (filtro temporal estricto)

El sistema descarta cualquier candidato con `fecha_fin < hoy` antes de persistir. Esto se aplica en dos puntos:

- **Pre-extracción** en rutas con metadata estructurada (listados HTML, JSON de agregadores).
- **Post-extracción** para redes sociales, donde la fecha solo se conoce tras procesar texto/imagen.

Eventos en curso (que empezaron ayer y siguen hoy) **sí entran**: el filtro es `fecha_fin >= hoy`, no `fecha_inicio >= hoy`.

---

## Flujo end-to-end resumido

```
┌──────────────────────────────────────────────────────────┐
│  1. SCHEDULER                                            │
│  Selecciona SCRAPING_TARGETS donde Next_Run_At <= now   │
│  ordenados por prioridad. Dispara workers.              │
└────────────────────────┬─────────────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────────────┐
│  2. CONNECTOR (uno por Tipo_Fuente)                     │
│  - HTML: cascade HEAD/sitemap → fetch → parse listado   │
│  - Agregador: API call con filtro geo+fecha             │
│  - Social: Apify pull últimos N posts                   │
│  Persiste en CAPTURAS_RAW.                              │
└────────────────────────┬─────────────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────────────┐
│  3. EXTRACTOR (uno por tipo de captura)                 │
│  - Structural: parser sobre HTML/JSON-LD/microdata     │
│  - Mapping: JSON de agregador → EventCandidate         │
│  - LLM Text: caption de post → EventCandidate          │
│  - LLM Vision: cartel de post → EventCandidate         │
│  Produce 0..N EventCandidate por captura.              │
└────────────────────────┬─────────────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────────────┐
│  4. GATE PRE-LLM (solo ruta social)                     │
│  Antes de invocar LLM, consulta EVENTOS_MASTER         │
│  para ese municipio en la ventana temporal del post.    │
│  Si match → registra fuente adicional, skip extracción. │
│  Si no match → procede con LLM.                         │
└────────────────────────┬─────────────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────────────┐
│  5. FILTRO TEMPORAL FINAL                               │
│  Descarta EventCandidate con fecha_fin < hoy.          │
└────────────────────────┬─────────────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────────────┐
│  6. MERGE CROSS-SOURCE                                  │
│  Agrupa candidatos por fingerprint(municipio, título,   │
│  fecha). Para cada grupo, aplica "mejor dato por campo"│
│  según prioridad de fuente. Produce MergedEvent.       │
└────────────────────────┬─────────────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────────────┐
│  7. PERSISTENCIA                                        │
│  INSERT/UPDATE EVENTOS_MASTER + EVENTO_HORARIOS +      │
│  EVENTO_CATEGORIAS + EVENTO_FUENTES.                   │
│  Descarga imágenes a BINARIOS_STORAGE.                 │
│  Encola job de embedding async.                        │
└────────────────────────┬─────────────────────────────────┘
                         │
                         ▼
┌──────────────────────────────────────────────────────────┐
│  8. EMBEDDING (job async, separado)                     │
│  Para cada evento nuevo o modificado, genera           │
│  Tags_Embedding_ES y Tags_Embedding_CAT.               │
│  Persiste en EVENTO_EMBEDDINGS.                        │
└──────────────────────────────────────────────────────────┘
```

El detalle de cada paso, incluyendo pseudocódigos y contratos exactos, está en [`INGESTION_PIPELINE.md`](./INGESTION_PIPELINE.md).

---

## Glosario

Términos usados a lo largo de toda la documentación del módulo. Si un MD usa una palabra técnica, debe estar definida aquí.

**Captura**: descarga cruda de contenido desde una fuente externa (HTML completo, JSON de API, lote de posts). Se almacena en `CAPTURAS_RAW` antes de cualquier procesamiento.

**Candidate / EventCandidate**: representación intermedia de un evento extraído de una captura, antes de pasar por merge. No tiene `ID_Unico_Evento` definitivo todavía.

**Cascade**: secuencia de filtros aplicados en orden de coste creciente para descartar contenido lo antes posible. Concepto central de la optimización del módulo.

**Conector / Connector**: componente responsable de capturar contenido de un tipo de fuente. Hay tres implementaciones: `HTMLConnector`, `AggregatorConnector`, `SocialConnector`.

**Extractor**: componente que transforma una captura cruda en uno o varios `EventCandidate`. Hay cuatro tipos: `StructuralExtractor`, `MappingExtractor`, `LLMTextExtractor`, `LLMVisionExtractor`.

**Fingerprint**: hash determinista de los campos identificativos de un evento (municipio + título normalizado + fecha) usado para detectar duplicados sin pasar por similitud semántica.

**Fuente**: una entrada en `BIBLIOTECA_FUENTES`. Representa una URL/cuenta/endpoint externo de donde captar contenido. No confundir con `Fuente_ID` de `EVENTOS_MASTER`, que es un enum descriptivo del método de captura.

**Gate / Gate pre-LLM**: comprobación en la ruta social que decide si un post justifica gastar LLM, consultando si su contenido coincide con eventos ya conocidos por rutas gratis.

**Merge**: paso que une candidatos de la misma "cosa" provenientes de fuentes distintas en un solo registro de `EVENTOS_MASTER`, eligiendo el mejor valor de cada campo según prioridad de fuente.

**Munipality / Municipio**: en este modelo se traduce a `ID_Ciudad` (FK a `CIUDADES`). El término "municipio" se usa por familiaridad de dominio pero el dato es `ID_Ciudad`.

**pHash**: hash perceptual de imagen, distinto de SHA-256. Permite detectar que dos imágenes son visualmente la misma aunque su byte-por-byte difiera (recompresión, recorte ligero, etc).

**Ruta**: cada una de las tres formas distintas de captura. Las rutas A, B, C son sinónimos de Web, Agregador y Social respectivamente. En `BIBLIOTECA_FUENTES.Tipo_Fuente` se materializan como `FUENTE_OFICIAL`, `AGREGADOR`, `RED_SOCIAL_PERFIL`, `RED_SOCIAL_QUERY`.

**Scraping target**: entrada en `SCRAPING_TARGETS`. Representa un trabajo programado contra una fuente. Una fuente puede tener varios targets (ej. una web con varios endpoints de agenda).

**VAC 360**: la spec de gobierno del dato y trazabilidad descrita en [`DATA_MODEL.md`](./DATA_MODEL.md). Este módulo la implementa.

---

## Roadmap de implementación

El módulo se construye en cuatro fases incrementales. Cada fase entrega valor por sí sola y la siguiente se apoya en la anterior.

### Fase 1 — Ruta web end-to-end (1 municipio)

Objetivo: validar el pipeline completo con coste cero antes de tocar Apify.

- Schema de las tablas nuevas aplicado (`SCHEMA_INGESTION_DELTA.sql`).
- `HTMLConnector` con cascade completa (HEAD/sitemap, hash dedup, listado filter).
- `StructuralExtractor` para JSON-LD y selectores CSS.
- Merge trivial (sin cross-source aún, una sola fuente).
- Persistencia en `EVENTOS_MASTER` + `EVENTO_HORARIOS` + `EVENTO_FUENTES`.
- Job de embedding async.
- Scheduler básico (sin scheduling adaptativo).
- Aplicado a una fuente real: la web del Ajuntament de Malgrat de Mar.

Criterio de salida: eventos reales de Malgrat aparecen en `EVENTOS_MASTER`, la API los devuelve, búsqueda semántica los encuentra. Todo gratuito.

### Fase 2 — Ruta agregador (cobertura masiva)

Objetivo: ganar cobertura provincial con una sola integración.

- `AggregatorConnector` con filtros geográficos y temporales en el request.
- `MappingExtractor` con configuración declarativa por agregador.
- Merge cross-source con política "mejor dato por campo".
- Integración con un agregador institucional (idealmente API de Diputació BCN o equivalente).
- Detección y reporte de duplicados detectados en merge.

Criterio de salida: una sola entrada en `BIBLIOTECA_FUENTES` alimenta candidatos para múltiples municipios. El merge dedupa correctamente eventos que vienen tanto de web como de agregador.

### Fase 3 — Ruta social con gate

Objetivo: añadir cobertura de cuentas activas en redes sin disparar el coste.

- `SocialConnector` integrado con Apify (un Actor por plataforma).
- `LLMTextExtractor` y `LLMVisionExtractor`.
- **Gate pre-LLM** implementado con fingerprint determinista + similitud semántica.
- Descarga de imágenes a storage propio.
- Registro de capturas/posts que no producen evento (gate skipped) en `AUDITORIA_SCRAPING`.

Criterio de salida: el gate bloquea al menos el 50% de las llamadas a LLM en redes sociales (medido en producción tras 30 días).

### Fase 4 — Optimizaciones a escala

Objetivo: preparar el sistema para crecer a 100+ municipios sin que se dispare el coste.

- Scheduling adaptativo por cobertura (`Coverage_Score` por `(ID_Ciudad, Tipo_Fuente)`).
- Backoff por fuente muerta.
- Caché de extracción por pHash de imagen (`PHASH_IMAGENES`).
- Re-procesamiento idempotente desde `CAPTURAS_RAW`.
- Métricas y dashboard de coste por fuente.

Criterio de salida: añadir un municipio nuevo al sistema no requiere tocar código, solo registrar fuentes en `BIBLIOTECA_FUENTES`.

---

## Próximos documentos a consultar

- Si vas a tocar BD o entender el modelo: [`INGESTION_DATA_MODEL.md`](./INGESTION_DATA_MODEL.md) → empezar por ahí.
- Si vas a programar un conector, extractor o el merge: [`INGESTION_PIPELINE.md`](./INGESTION_PIPELINE.md).
- Si vas a configurar scheduling, frecuencias o caches: [`INGESTION_OPTIMIZATION.md`](./INGESTION_OPTIMIZATION.md).
- Si vas a operar el módulo en producción (deploy, monitoreo, troubleshooting): [`INGESTION_OPERATIONS.md`](./INGESTION_OPERATIONS.md).
