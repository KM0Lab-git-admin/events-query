# 🛠️ Módulo de Ingesta — Operaciones y observabilidad

**Versión:** 1.0
**Última actualización:** 2026-05-15

---

> 📌 **Docs relacionados (módulo de ingesta)**
> - [Visión general](./INGESTION_OVERVIEW.md)
> - [Modelo de datos del módulo](./INGESTION_DATA_MODEL.md)
> - [Pipeline detallado](./INGESTION_PIPELINE.md)
> - [Optimización y escala](./INGESTION_OPTIMIZATION.md)
> - [Operaciones y observabilidad](./INGESTION_OPERATIONS.md) ← estás aquí

---

## 📋 Tabla de contenidos

1. [Gestión de imágenes y storage propio](#gestión-de-imágenes-y-storage-propio)
2. [Auditoría y trazabilidad VAC 360](#auditoría-y-trazabilidad-vac-360)
3. [Manejo de fallos](#manejo-de-fallos)
4. [Observabilidad](#observabilidad)
5. [Despliegue en Railway](#despliegue-en-railway)
6. [Backup y recuperación](#backup-y-recuperación)
7. [Runbooks operacionales](#runbooks-operacionales)

---

## Gestión de imágenes y storage propio

Las imágenes de eventos son una pieza crítica del producto: la app las muestra en listados, en detalles y en notificaciones. Tres razones obligan a tener storage propio en lugar de enlazar a la fuente original:

**1. URLs externas caducan.** Los CDN de Meta (Instagram, Facebook) firman las URLs de imágenes con tokens que expiran en días o semanas. Una app que muestra un evento de hace dos meses encontrará la imagen rota si solo guarda la URL.

**2. Performance.** El CDN propio sirve más rápido a usuarios de Catalunya (Cloudflare R2 con edge en Madrid/París) que ir a buscar la imagen al CDN del servicio externo, que puede tener cold start.

**3. Control de transformaciones.** El módulo genera tres tamaños (thumbnail 400px, medium 1080px, original) optimizados para los distintos usos en la app. No hay forma de hacer esto a URLs externas.

### Stack recomendado

- **Object storage**: Cloudflare R2 ($0.015/GB/mes, sin egress fees) o AWS S3 ($0.023/GB/mes + egress).
- **CDN**: Cloudflare CDN delante de R2 (incluido en el plan, sin coste adicional).
- **Procesamiento de imagen**: PIL/Pillow para resize y conversión, `imagehash` para pHash.

### Estructura de keys en object storage

```
events/
  {id_unico_evento}/
    {uuid}.original.jpg     ← bytes originales descargados
    {uuid}.medium.jpg       ← 1080px de ancho, calidad 85
    {uuid}.thumb.jpg        ← 400px de ancho, calidad 80
```

El `uuid` evita colisiones si una misma imagen se versiona (caso raro pero posible).

### Procedimiento de descarga

```python
async def download_and_store_image(url_original: str, id_unico_evento: str) -> dict:
    """
    Descarga una imagen desde una URL externa, la procesa y la sube al storage propio.
    Devuelve dict con URLs públicas y metadatos.
    """
    # 1. Descargar con timeout y validación de tamaño
    response = await http_client.get(
        url_original,
        timeout=httpx.Timeout(30.0, connect=10.0),
        follow_redirects=True,
    )
    response.raise_for_status()

    if len(response.content) > 20 * 1024 * 1024:  # 20 MB máx
        raise ImageTooLargeError(url_original)

    img_bytes = response.content

    # 2. Validar que es imagen real, no HTML/error
    try:
        pil_img = PIL.Image.open(io.BytesIO(img_bytes))
        pil_img.verify()
        pil_img = PIL.Image.open(io.BytesIO(img_bytes))  # reabrir tras verify
    except (PIL.UnidentifiedImageError, OSError):
        raise InvalidImageError(url_original)

    # 3. Calcular hash perceptual
    phash = str(imagehash.phash(pil_img))

    # 4. Generar variantes
    medium = _resize_image(pil_img, max_width=1080, quality=85)
    thumb = _resize_image(pil_img, max_width=400, quality=80)

    # 5. Subir las tres variantes
    base_uuid = uuid4().hex[:12]
    keys = {
        'original': f"events/{id_unico_evento}/{base_uuid}.original.jpg",
        'medium':   f"events/{id_unico_evento}/{base_uuid}.medium.jpg",
        'thumb':    f"events/{id_unico_evento}/{base_uuid}.thumb.jpg",
    }

    await storage.put(keys['original'], img_bytes, content_type='image/jpeg')
    await storage.put(keys['medium'], medium, content_type='image/jpeg')
    await storage.put(keys['thumb'], thumb, content_type='image/jpeg')

    return {
        'url_original_externa': url_original,
        'url_cdn_original': storage.public_url(keys['original']),
        'url_cdn_medium': storage.public_url(keys['medium']),
        'url_cdn_thumb': storage.public_url(keys['thumb']),
        'phash': phash,
        'checksum_sha256': sha256(img_bytes).hexdigest(),
        'size_bytes': len(img_bytes),
    }
```

### Registros en BD

Tras la descarga exitosa:

```python
# 1. Insertar en BINARIOS_STORAGE
binario_id = await db.execute("""
    INSERT INTO BINARIOS_STORAGE
        (ID_Unico_Evento, Nombre_Archivo, Tipo_Archivo,
         URL_Almacenamiento_Nube, Checksum_SHA256)
    VALUES (%s, %s, %s, %s, %s)
""", [id_unico_evento, f"{base_uuid}.medium.jpg", 'JPG',
      result['url_cdn_medium'], result['checksum_sha256']])

# 2. Si tiene pHash, registrar/actualizar PHASH_IMAGENES
if result['phash']:
    await db.execute("""
        INSERT INTO PHASH_IMAGENES (Phash_Hex, ID_Binario)
        VALUES (%s, %s)
        ON DUPLICATE KEY UPDATE
            Veces_Reutilizado = Veces_Reutilizado + 1,
            Fecha_Ultimo_Hit = NOW()
    """, [result['phash'], binario_id])

# 3. Si es la imagen principal, actualizar EVENTOS_MASTER
if es_principal:
    await db.execute("""
        UPDATE EVENTOS_MASTER
        SET Imagen_Principal_URL = %s
        WHERE ID_Unico_Evento = %s
    """, [result['url_cdn_medium'], id_unico_evento])
```

`EVENTOS_MASTER.Imagen_Principal_URL` siempre apunta a la versión **medium** (1080px). Si la app necesita thumbnail o original, puede derivar la URL reemplazando el sufijo, o consultar `BINARIOS_STORAGE`.

### Rotación y limpieza

Eventos cancelados o eliminados conservan sus binarios durante **90 días** en un bucket "archive". Pasados los 90 días, un job de limpieza borra los objetos físicamente. Las filas en `BINARIOS_STORAGE` se mantienen pero con `URL_Almacenamiento_Nube` marcada como vacía para auditoría histórica.

---

## Auditoría y trazabilidad VAC 360

Toda actividad del módulo debe ser reconstruible a posteriori. Esto se materializa en cuatro tablas que, juntas, dan trazabilidad completa.

### Las cuatro fuentes de verdad

| Tabla | Qué cuenta | Granularidad |
|---|---|---|
| `CAPTURAS_RAW` | Qué se descargó de cada fuente | Por captura individual (cada GET, cada llamada Apify) |
| `AUDITORIA_SCRAPING` | Qué hizo el extractor con cada captura | Por intento de extracción |
| `EVENTO_FUENTES` | Qué fuentes confirmaron cada evento | Por enlace evento-fuente |
| `EVENTOS_MASTER.Fecha_Creacion` y `Fuente_URL_Original` | Marca temporal y origen del registro persistido | Por evento |

### Casos de uso de la auditoría

**"¿Por qué este evento tiene la fecha mal?"**

```sql
-- Reconstruir el merge de un evento
SELECT
    ef.URL_Origen, ef.Es_Fuente_Principal, ef.Aporto_Extraccion,
    ef.Score_Calidad, ef.Fecha_Primera_Vez,
    bf.Tipo_Fuente,
    cr.Fecha_Captura, cr.Extractor_Usado
FROM EVENTO_FUENTES ef
JOIN BIBLIOTECA_FUENTES bf ON bf.ID_Fuente = ef.ID_Fuente
LEFT JOIN CAPTURAS_RAW cr ON cr.ID_Captura = ef.ID_Captura
WHERE ef.ID_Unico_Evento = ?
ORDER BY ef.Fecha_Primera_Vez ASC;
```

A partir de aquí se puede inspeccionar `CAPTURAS_RAW.Payload_Bytes` para ver el HTML/JSON original que se procesó.

**"¿Cuántos posts de Instagram pasaron sin producir evento?"**

```sql
SELECT
    DATE(aud.Fecha_Ejecucion) AS dia,
    aud.Motivo_Skip,
    COUNT(*) AS cnt
FROM AUDITORIA_SCRAPING aud
JOIN CAPTURAS_RAW cr ON cr.ID_Captura = aud.ID_Captura
JOIN BIBLIOTECA_FUENTES bf ON bf.ID_Fuente = cr.ID_Fuente
WHERE bf.Tipo_Fuente IN ('RED_SOCIAL_PERFIL', 'RED_SOCIAL_QUERY')
  AND aud.Fecha_Ejecucion >= NOW() - INTERVAL 7 DAY
  AND aud.ID_Unico_Evento IS NULL
GROUP BY dia, aud.Motivo_Skip
ORDER BY dia DESC, cnt DESC;
```

**"¿Qué fuentes producen más errores?"**

```sql
SELECT
    bf.ID_Fuente, bf.URL_Base, bf.Tipo_Fuente,
    COUNT(*) AS errores_30d,
    MAX(aud.Fecha_Ejecucion) AS ultimo_error,
    SUBSTRING(MAX(aud.Detalle), 1, 200) AS ejemplo_error
FROM AUDITORIA_SCRAPING aud
JOIN CAPTURAS_RAW cr ON cr.ID_Captura = aud.ID_Captura
JOIN BIBLIOTECA_FUENTES bf ON bf.ID_Fuente = cr.ID_Fuente
WHERE aud.Resultado = 'ERROR'
  AND aud.Fecha_Ejecucion >= NOW() - INTERVAL 30 DAY
GROUP BY bf.ID_Fuente
HAVING errores_30d > 5
ORDER BY errores_30d DESC;
```

### Retención de capturas

`CAPTURAS_RAW.Payload_Bytes` puede crecer muy rápido (HTMLs de 100-500 KB cada uno, payloads de Apify de varios MB). Política de retención:

- **Capturas exitosas con eventos producidos**: payload se conserva durante 180 días, después se mueve a object storage (`Payload_Storage_URL`) y se vacía `Payload_Bytes`.
- **Capturas con error o sin evento**: payload se conserva durante 30 días (suficiente para debugging), después se vacía.
- **Filas en CAPTURAS_RAW**: se conservan indefinidamente. La metadata (hash, fecha, status) ocupa poco.

Job nocturno que aplica la política:

```sql
-- Mover payloads viejos a archive
UPDATE CAPTURAS_RAW
SET Payload_Storage_URL = NULL,
    Payload_Bytes = NULL
WHERE Fecha_Captura < NOW() - INTERVAL 180 DAY
  AND Payload_Bytes IS NOT NULL
  AND Status = 'EXTRAIDA'
  AND ID_Captura IN (SELECT ID_Captura FROM EVENTO_FUENTES);  -- produjo evento
```

---

## Manejo de fallos

El módulo trata con sistemas externos inestables. La política es **fallar de forma observable**, no silenciosamente.

### Categorías de fallo

| Categoría | Ejemplos | Acción |
|---|---|---|
| Transitorios | Timeout HTTP, 5xx temporal, rate limit con Retry-After | Retry con backoff exponencial, mismo `ID_Target` |
| Persistentes | 404, página renombrada, JSON estructura cambió, parser ya no aplica | Reintentar 3 veces, después `Estado='PAUSADO'`, alertar |
| Catastróficos | Credenciales expiradas, BD caída, object storage caído | Detener workers, alertar inmediatamente |
| Lógicos | Captura OK pero extractor no produce candidatos válidos | Auditar con `Motivo_Skip`, no es error per se |

### Retry con backoff exponencial

```python
@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=60),
    retry=retry_if_exception_type((httpx.TimeoutException, httpx.NetworkError, ServerError5xx)),
    reraise=True,
)
async def fetch_with_retry(url: str) -> httpx.Response:
    response = await http_client.get(url, timeout=30)
    if 500 <= response.status_code < 600:
        raise ServerError5xx(f"{url} returned {response.status_code}")
    return response
```

### Dead letter queue conceptual

Los targets que fallan 3 veces consecutivas pasan a `Estado='PAUSADO'`. Esto los excluye del scheduler. Un dashboard (o un job semanal) lista los targets pausados para revisión manual:

```sql
SELECT
    st.ID_Target, st.URL_Target, st.Intentos, st.Last_Error,
    st.Last_Run_At, bf.Tipo_Fuente, bf.URL_Base
FROM SCRAPING_TARGETS st
JOIN BIBLIOTECA_FUENTES bf ON bf.ID_Fuente = st.ID_Fuente
WHERE st.Estado = 'PAUSADO'
ORDER BY st.Last_Run_At DESC;
```

Tras revisar y corregir (cambiar URL, actualizar selectores en `Config_JSON`, etc.), se reactiva manualmente con `UPDATE SCRAPING_TARGETS SET Estado='PENDIENTE', Intentos=0 WHERE ID_Target=?`.

### Idempotencia

Las operaciones deben ser idempotentes para que un retry no cause inconsistencia:

- **Captura**: si una captura ya existe con el mismo `Content_Hash_SHA256`, se crea con `Status='SKIPPED_SIN_CAMBIOS'` y se referencia la previa.
- **Persistencia de evento**: usa `INSERT ... ON DUPLICATE KEY UPDATE` (o `INSERT IGNORE` + `UPDATE` por separado en transacción).
- **Descarga de imagen**: el `Checksum_SHA256` previene duplicados en `BINARIOS_STORAGE`.

### Aislamiento de fallos

Un fallo procesando un target no debe afectar a otros. Cada worker corre su pipeline en un try/except que captura todo, registra en `AUDITORIA_SCRAPING` y pasa al siguiente:

```python
async def process_target_safe(id_target: int):
    try:
        await process_target(id_target)
    except Exception as e:
        await log_target_error(id_target, e)
        capture_exception_to_apm(e)  # Sentry / etc.
        # No re-raise: otro target sigue.
```

---

## Observabilidad

Tres pilares: logs estructurados, métricas, alertas.

### Logs estructurados

JSON por línea, con campos consistentes para que sean filtrables en Loki/CloudWatch/Datadog:

```python
import structlog

logger = structlog.get_logger()

logger.info(
    "captura_completed",
    id_target=target.id_target,
    id_fuente=fuente.id_fuente,
    tipo_fuente=fuente.tipo_fuente,
    duration_ms=duration_ms,
    payload_size_bytes=len(payload),
    extractors_run=[ext.name for ext in extractors],
    candidates_produced=len(candidates),
    coste_estimado_usd=coste,
)
```

Eventos que **siempre** deben loggearse:

- Inicio y fin de cada `process_target` (con duration y resultado).
- Cada decisión del Gate (con score y método).
- Cada llamada a LLM (con modelo, tokens, latencia).
- Cada error de extractor con stack trace.
- Cada cambio de estado en `SCRAPING_TARGETS` (a `OK`, `ERROR`, `PAUSADO`).

### Métricas

Lista completa en [`INGESTION_OPTIMIZATION.md`](./INGESTION_OPTIMIZATION.md#métricas-a-monitorear). Las críticas (⭐) son las que deben tener panel y alerta.

### Alertas

Configurar en Grafana/Datadog/equivalente:

| Condición | Severidad | Acción |
|---|---|---|
| `targets_pendientes > 1000` durante > 1h | warning | Revisar workers, considerar escalado |
| `targets_pendientes > 5000` o > 6h | critical | Workers caídos, intervención inmediata |
| `apify_cost_diario_usd > $50` (escenario A) o $300 (B) o $1500 (C) | warning | Posible loop, investigar |
| `target_errores_total{tipo_error='auth'}` > 0 | critical | Credenciales expiradas |
| `coverage_score{tipo_fuente='FUENTE_OFICIAL'} < 0.1` durante 7 días | warning | Fuente probablemente rota |
| `phash_cache_hit_ratio < 0.05` durante 3 días | info | Cache no está funcionando, revisar |
| DB connection pool exhausted | critical | DB sobrecargada o pool mal dimensionado |

---

## Despliegue en Railway

Ver [`DEPLOYMENT.md`](./DEPLOYMENT.md) para el setup general del proyecto. Esta sección cubre solo lo específico del módulo de ingesta.

### Servicios en Railway

El módulo de ingesta se materializa típicamente como **2-3 servicios separados** del servicio de API:

1. **`ingestion-scheduler`**: un solo proceso. Lee `SCRAPING_TARGETS` cada minuto, dispara workers (vía cola interna o RPC al servicio de workers).
2. **`ingestion-workers`**: 1-N réplicas según carga. Cada worker procesa un target a la vez (la concurrencia viene de tener N réplicas, no de threads dentro de cada una).
3. **`ingestion-jobs`** (opcional): cron jobs para tareas batch — recálculo de `COVERAGE_METRICS` nocturno, embedder de pendientes, limpieza de capturas viejas.

Cada servicio tiene su propio `Procfile` o `start command`:

```toml
# railway.toml para ingestion-workers
[deploy]
startCommand = "python -m app.ingestion.worker_main"
healthcheckPath = "/health"
healthcheckTimeout = 30
restartPolicyType = "ON_FAILURE"
restartPolicyMaxRetries = 5
```

### Variables de entorno

Variables específicas del módulo (vienen además de las generales del proyecto):

```bash
# Apify
APIFY_TOKEN=apify_api_...
APIFY_PLAN=starter  # starter | scale | business

# OpenAI / LLM
OPENAI_API_KEY=sk-...
LLM_TEXT_MODEL=gpt-4.1-mini
LLM_VISION_MODEL=gpt-4.1-mini
EMBEDDING_MODEL=text-embedding-3-small

# Object storage
R2_ACCOUNT_ID=...
R2_ACCESS_KEY=...
R2_SECRET_KEY=...
R2_BUCKET_NAME=km0events-binaries
CDN_PUBLIC_BASE_URL=https://cdn.km0lab.com

# Concurrencia
INGESTION_WORKER_BATCH_SIZE=10
INGESTION_WORKER_INTERVAL_SECONDS=60
INGESTION_MAX_CONCURRENT_TARGETS=5

# Coste y safety
COST_DAILY_HARD_LIMIT_USD=100   # mata workers si excede
GATE_SEMANTIC_THRESHOLD=0.82
PHASH_HAMMING_TOLERANCE=5
```

### Connection pool

El módulo tiene mucho I/O concurrente (HTTP + DB + storage). El pool de BD debe dimensionarse con holgura:

```python
# Mínimo recomendado
DB_POOL_MIN_SIZE = INGESTION_MAX_CONCURRENT_TARGETS * 2
DB_POOL_MAX_SIZE = INGESTION_MAX_CONCURRENT_TARGETS * 4
DB_POOL_TIMEOUT = 30  # segundos
```

Si los workers comparten BD con la API, vigilar el total: `(N_workers × DB_POOL_MAX) + (N_api_replicas × DB_POOL_MAX)` no debe superar el límite del plan de Railway MySQL.

---

## Ejecución del pipeline multi-fuente (fase 1 implementada)

> Sección añadida en junio 2026 con la implementación real de `scripts/ingest_all.py`
> en modo BD (eventos + noticias, targets en BD, detección de cambios).

### Comandos

```bash
# 1. Aplicar deltas de schema (una vez)
mysql -u USER -p events_db < SQL/fuentes_delta.sql
mysql -u USER -p events_db < SQL/noticias_delta.sql

# 2. Cargar las semillas de fuentes (idempotente, re-ejecutable)
python scripts/import_fuentes.py --input scripts/fuentes/Malgrat.json --target local
python scripts/import_fuentes.py --input scripts/fuentes/Blanes.json  --target local

# 3. Ejecutar el pipeline (modo BD, el del cron)
python scripts/ingest_all.py --target local
python scripts/ingest_all.py --target railway          # contra producción
python scripts/ingest_all.py --solo-poblacion "Malgrat de Mar"
python scripts/ingest_all.py --dry-run                 # no escribe (SÍ gasta LLM)
python scripts/ingest_all.py --refresh                 # ignora incremental y fingerprints
```

### Orden interno del run (modo BD)

1. Purga de eventos pasados + horarios sueltos caducados + noticias caducadas
   (TTL `NEWS_TTL_DIAS`, default 45 días; archivado y borrado definitivo a 90 días).
2. Carga de eventos/noticias existentes (omisión incremental).
3. Por población y target (orden de prioridad): detección de cambios
   (ETag/Last-Modified → 304; fingerprint sha256 del HTML limpio) → skip si no
   cambió; si cambió: extracción según tipo (EVENTOS directo; MIXTO/NOTICIAS con
   clasificador; WEB_DETALLE extracción directa; Telegram batch).
4. Eventos: fusión → filtro temporal → enriquecimiento → persistencia.
5. Noticias: dedupe cross-fuente → traducción/tags → NOTICIAS_MASTER.
6. Purga de carpetas de imágenes huérfanas + sync de binarios remotos.
7. Resumen de targets (OK/SKIP/ERROR) + informe de gasto real de OpenAI.

Un lock-file (`scripts/.ingest.lock`) impide ejecuciones simultáneas; un lock
de más de 6 horas se considera huérfano y se ignora.

### Programación del cron (documentado, NO activado)

El comando es idempotente y barato en runs sin cambios. Cuando se decida
activarlo, opciones:

**Windows (Task Scheduler), en la máquina de ejecución:**
```powershell
schtasks /create /tn "KM0_Ingesta" /sc daily /st 06:00 `
  /tr "C:\ruta\venv\Scripts\python.exe C:\ruta\events-query\scripts\ingest_all.py --target railway"
```

**Linux (crontab):**
```cron
0 6 * * * cd /ruta/events-query && ./venv/bin/python scripts/ingest_all.py --target railway >> logs/ingesta.log 2>&1
```

**Railway (cron job sobre el servicio):** añadir un servicio cron con schedule
`0 6 * * *` que ejecute `python scripts/ingest_all.py --target railway`
(requiere empaquetar scripts/ en el deploy y las env vars RAILWAY_DB_* +
OPENAI_API_KEY en el servicio).

### Redes sociales (fase 2)

Instagram/Facebook/X/YouTube están registradas en `BIBLIOTECA_FUENTES` con
`Activa=0` (las carga `import_fuentes.py` desde las semillas). El conector vía
Apify se implementará en fase 2; al activarlo bastará poner `Activa=1` y crear
su target. Telegram público (t.me/s/handle) SÍ está implementado en fase 1.

### Deduplicación semántica (scripts/dedupe_events.py)

La ingesta deduplica por título/lugar/fechas, pero fuentes distintas titulan el
mismo evento de formas muy diferentes, y los festivales generan actividades
relacionadas que no son duplicados. `dedupe_events.py` lo resuelve sobre la BD:

```bash
mysql -u USER -p events_db < SQL/familia_delta.sql      # una vez (ID_Familia)
python scripts/dedupe_events.py --target local --dry-run  # informe sin tocar BD
python scripts/dedupe_events.py --target local            # aplica
```

- Blocking: pares de la misma ciudad con fechas solapadas (±2 días).
- Embeddings (`text-embedding-3-small`) + boosts (lugar/organizador/fecha).
- `score >= 0.90` → fusión automática (gana el de descripción más rica; se
  traspasan horarios, fuentes, categorías e imágenes; el otro se borra).
- `0.78 <= score < 0.90` → juez LLM: `MISMO` (fusión) / `MISMA_FAMILIA`
  (agrupa vía `EVENTOS_MASTER.ID_Familia`, cabeza = el que engloba en fechas) /
  `DISTINTO`.
- Umbrales ajustables: `--umbral-dup`, `--umbral-gris` (o env `DEDUPE_UMBRAL_*`).
- Idempotente; pensado para el cron justo después de `ingest_all.py`.
- Railway: tras fusiones, ejecutar `ingest_all.py --sync-images-only --target
  railway` para resubir las imágenes traspasadas a su nueva ruta.

---

## Backup y recuperación

Las tablas del módulo se incluyen en el backup general de la BD (ver [`DEPLOYMENT.md`](./DEPLOYMENT.md)). Algunas consideraciones específicas:

### Prioridades de restauración

En caso de pérdida total:

1. **Crítico** (debe recuperarse al 100%): `EVENTOS_MASTER`, `EVENTO_HORARIOS`, `EVENTO_FUENTES`, `EVENTO_CATEGORIAS`, `BINARIOS_STORAGE` (metadatos). Estas son las tablas que sirve la API.
2. **Importante** (recuperar para no perder configuración): `BIBLIOTECA_FUENTES`, `SCRAPING_TARGETS`, `CATEGORIAS`, `CIUDADES`, `CODIGOS_POSTALES`.
3. **Recuperable** (puede reconstruirse): `EVENTO_EMBEDDINGS` (se regenera con un job batch a coste bajo), `COVERAGE_METRICS` (se recalcula en una noche), `PHASH_IMAGENES` (se reconstruye según aparecen imágenes nuevas).
4. **Histórico** (deseable pero no crítico): `CAPTURAS_RAW` con payloads viejos, `AUDITORIA_SCRAPING` con > 90 días.

### Object storage

El object storage de imágenes **no se respalda automáticamente con la BD**. Cloudflare R2 ofrece versioning de objetos como feature aparte. Activarlo añade ~$0.005/GB/mes.

Alternativa más barata: snapshot mensual del bucket completo a otro bucket de archive en una región distinta. Para el escenario C (~500 GB) son ~$7.50/mes.

### Recuperación de capturas

Si un evento aparece corrupto en BD y la captura cruda existe en `CAPTURAS_RAW`, **se puede re-procesar sin volver a scrapear**:

```python
async def reprocess_capture(id_captura: int):
    captura = await load_capture(id_captura)
    fuente = await load_fuente(captura.id_fuente)
    extractor = get_extractor_for(fuente, captura)

    candidates = await extractor.extract(captura, fuente)
    merged = await merger.merge(candidates)

    for m in merged:
        await persister.upsert(m)
```

Esto es lo que justifica el principio de "captura inmutable" del modelo de datos.

---

## Runbooks operacionales

Procedimientos para situaciones típicas de operación. Cada uno está pensado para que alguien que no es el autor original del módulo pueda ejecutarlo.

### Runbook 1: añadir un nuevo municipio

1. **Insertar la ciudad** si no existe:
   ```sql
   INSERT INTO CIUDADES (Nombre, Provincia, Latitud, Longitud)
   VALUES ('Pineda de Mar', 'Barcelona', 41.6275, 2.6856);
   ```
2. **Insertar códigos postales** del municipio en `CODIGOS_POSTALES`.
3. **Descubrir fuentes oficiales**: web del ayuntamiento, agenda de turismo, redes sociales.
4. **Registrar fuentes** en `BIBLIOTECA_FUENTES` con `Config_JSON` apropiado.
5. **Crear targets** iniciales en `SCRAPING_TARGETS` (al menos uno por fuente).
6. **Esperar primer ciclo** (típicamente < 1 hora). Validar en `AUDITORIA_SCRAPING` que las primeras capturas se ejecutan sin error.
7. **Revisar primeros eventos** en `EVENTOS_MASTER` y ajustar `Config_JSON` si los selectores fallan.

### Runbook 2: una fuente empezó a fallar

1. Detectar la alerta (típicamente "target_errores aumentando").
2. Consultar últimos errores:
   ```sql
   SELECT * FROM AUDITORIA_SCRAPING
   WHERE Resultado = 'ERROR'
     AND ID_Captura IN (SELECT ID_Captura FROM CAPTURAS_RAW WHERE ID_Fuente = ?)
   ORDER BY Fecha_Ejecucion DESC LIMIT 10;
   ```
3. Reproducir manualmente la URL/llamada que falla.
4. Diagnóstico típico:
   - **HTTP 404** → la web cambió la URL. Actualizar `URL_Target` en `SCRAPING_TARGETS`.
   - **HTTP 200 pero parser falla** → la web cambió la estructura. Actualizar `Config_JSON` de la fuente con nuevos selectores.
   - **HTTP 429** → rate limit, posiblemente bajar frecuencia base.
   - **Apify error** → ver dashboard de Apify, suele ser temporal o problema con el actor.
5. Reactivar los targets pausados.

### Runbook 3: el coste de Apify se disparó

1. Identificar runs caros:
   ```sql
   SELECT ID_Fuente, COUNT(*) AS runs, SUM(Coste_Estimado_USD) AS coste_total
   FROM CAPTURAS_RAW
   WHERE Fecha_Captura >= NOW() - INTERVAL 7 DAY
     AND Content_Type = 'application/json'
   GROUP BY ID_Fuente
   ORDER BY coste_total DESC LIMIT 10;
   ```
2. Si una fuente está corriendo más veces de las esperadas:
   - Verificar `SCRAPING_TARGETS.Frecuencia_Horas` y `Next_Run_At` para ver si hay loop.
   - Verificar `COVERAGE_METRICS` para ver si el scheduling adaptativo no está aplicándose.
3. Aplicar mitigación inmediata: `UPDATE SCRAPING_TARGETS SET Frecuencia_Horas=168, Next_Run_At=NOW()+INTERVAL 7 DAY WHERE ID_Fuente=?`.
4. Investigar root cause en logs.

### Runbook 4: un evento aparece con datos incorrectos

1. Identificar el evento: `SELECT * FROM EVENTOS_MASTER WHERE ID_Unico_Evento = ?`.
2. Reconstruir las fuentes que contribuyeron:
   ```sql
   SELECT ef.*, bf.URL_Base, cr.Fecha_Captura, cr.Status
   FROM EVENTO_FUENTES ef
   JOIN BIBLIOTECA_FUENTES bf ON bf.ID_Fuente = ef.ID_Fuente
   LEFT JOIN CAPTURAS_RAW cr ON cr.ID_Captura = ef.ID_Captura
   WHERE ef.ID_Unico_Evento = ?;
   ```
3. Inspeccionar la captura cruda que aportó el campo erróneo (`CAPTURAS_RAW.Payload_Bytes` o `Payload_Storage_URL`).
4. Decidir:
   - Si el error está en el origen (la web del ayuntamiento puso fecha mal) → corrección manual en `EVENTOS_MASTER`, no se puede hacer mucho más.
   - Si el error está en el extractor (parseó mal una fecha relativa) → corregir extractor, reprocesar la captura, reactivar embeddings.

### Runbook 5: regenerar embeddings tras cambio de modelo

1. Configurar nuevo `EMBEDDING_MODEL` en variables de entorno.
2. Marcar embeddings antiguos para regeneración (opción A: borrarlos):
   ```sql
   DELETE FROM EVENTO_EMBEDDINGS WHERE Modelo = 'text-embedding-3-small';
   ```
   O (opción B: mantener viejos, generar nuevos):
   ```sql
   -- no se borra nada, el job de embedder verá que no hay embedding con Modelo='nuevo' y los generará
   ```
3. Reiniciar `ingestion-jobs` para que el job de embedder coja los pendientes.
4. Monitorizar `embeddings_pendientes` hasta llegar a 0.
5. Cuando estén todos los nuevos generados, actualizar la API para que consulte el nuevo modelo.
6. Eventualmente, borrar embeddings del modelo viejo.
