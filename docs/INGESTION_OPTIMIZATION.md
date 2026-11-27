# 📉 Módulo de Ingesta — Optimización y escala

**Versión:** 1.0
**Última actualización:** 2026-05-15

---

> 📌 **Docs relacionados (módulo de ingesta)**
> - [Visión general](./INGESTION_OVERVIEW.md)
> - [Modelo de datos del módulo](./INGESTION_DATA_MODEL.md)
> - [Pipeline detallado](./INGESTION_PIPELINE.md)
> - [Optimización y escala](./INGESTION_OPTIMIZATION.md) ← estás aquí
> - [Operaciones y observabilidad](./INGESTION_OPERATIONS.md)

---

## 📋 Tabla de contenidos

1. [Principio rector: cascade de coste creciente](#principio-rector-cascade-de-coste-creciente)
2. [Filtros pre-coste detallados](#filtros-pre-coste-detallados)
3. [Scheduling adaptativo](#scheduling-adaptativo)
4. [Backoff por fuente muerta](#backoff-por-fuente-muerta)
5. [Cache perceptual de carteles](#cache-perceptual-de-carteles)
6. [Cálculos de coste a escala](#cálculos-de-coste-a-escala)
7. [Métricas a monitorear](#métricas-a-monitorear)

---

## Principio rector: cascade de coste creciente

Toda la optimización del módulo se reduce a una regla: **gastar lo barato antes que lo caro**. Los filtros se aplican en orden de coste creciente, y cada filtro descarta lo más posible antes de pasar al siguiente.

| Capa | Coste | Cuánto descarta |
|---|---|---|
| HEAD HTTP / sitemap lastmod | ~0 ms, 0 € | 70-90% de páginas web sin cambios |
| Filtro temporal en listado | ~10-50 ms, 0 € | 30-60% de items pasados |
| Hash de contenido | ~1 ms, 0 € | 100% de capturas idénticas a previas |
| Scheduling adaptativo | 0 € (no se ejecuta el target) | Variable, hasta 75% de runs de Apify innecesarios |
| Apify scrape | $0.005-0.02 por lote | Inevitable para social, una vez decidido correr |
| Gate pre-LLM | ~50 ms + 1 embedding ($0.0001) | 50-80% de posts duplicados con rutas gratis |
| LLM-Text | $0.001-0.005 por post | (extracción real) |
| LLM-Vision con pHash cache | $0.01-0.05 / cache hit | 20-40% según viralidad del cartel |
| Embedding | $0.00001 por evento | (post-persistencia) |

A escala de 3.000 municipios, la diferencia entre aplicar esta cascade o no es de **~$5.000/mes vs $25.000/mes**. El multiplicador 5× es lo que hace o rompe el modelo de negocio.

---

## Filtros pre-coste detallados

### HEAD HTTP y `If-None-Match` / `If-Modified-Since`

Cualquier servidor HTTP medio decente responde a `HEAD` con headers `ETag` y `Last-Modified`. El cliente debe:

```python
async def head_check_or_skip(target, client):
    headers = {}
    if target.http_etag:
        headers['If-None-Match'] = target.http_etag
    if target.http_lastmodified:
        headers['If-Modified-Since'] = target.http_lastmodified

    response = await client.head(target.url_target, headers=headers, timeout=10)

    if response.status_code == 304:
        # No cambió: skip total
        return None

    # 200 OK: el servidor confirma cambio. Aún así guardamos los headers
    # nuevos para el próximo HEAD check.
    return {
        'etag': response.headers.get('ETag'),
        'last_modified': response.headers.get('Last-Modified'),
    }
```

**No todos los servidores cooperan.** Webs municipales pequeñas a veces devuelven siempre `200` ignorando los headers. En ese caso el filtro no ahorra nada, pero tampoco hace daño. Pasamos al siguiente filtro.

### Sitemap.xml con `<lastmod>`

Cuando una fuente publica sitemap, **es el mejor filtro disponible**. Una sola petición de ~10 KB te dice qué URLs cambiaron desde tu última pasada:

```python
async def sitemap_discover(target, last_known_runs):
    response = await client.get(target.url_target)
    root = ET.fromstring(response.content)
    ns = {'sm': 'http://www.sitemaps.org/schemas/sitemap/0.9'}

    new_urls = []
    for url_node in root.findall('sm:url', ns):
        loc = url_node.findtext('sm:loc', namespaces=ns)
        lastmod = url_node.findtext('sm:lastmod', namespaces=ns)

        if loc in last_known_runs and lastmod <= last_known_runs[loc]:
            continue  # no cambió
        new_urls.append(loc)

    return new_urls
```

Cada URL nueva o modificada se convierte en un target `WEB_DETALLE` que se programa para procesarse.

### Filtro temporal en página de listado

Las agendas municipales típicamente tienen un listado HTML con título + fecha + link a detalle. El connector debe **parsear el listado primero** y solo bajar las páginas de detalle de items con fecha futura:

```python
async def parse_listing_filter_future(html, css_selectors):
    soup = BeautifulSoup(html, 'lxml')
    items = []
    for item_el in soup.select(css_selectors['item']):
        date_text = item_el.select_one(css_selectors['date']).text
        try:
            event_date = parse_date_flexible(date_text)
        except ValueError:
            continue

        if event_date < date.today():
            continue  # pasado: skip

        items.append({
            'url_detalle': item_el.select_one(css_selectors['link']).get('href'),
            'fecha_estimada': event_date,
        })
    return items
```

Esto reduce el número de detalles a descargar en 30-60% típicamente (depende de cuánto contenido archivado mantenga la web).

**Importante**: la fecha del listado es una **estimación**. La fecha real se confirma en la extracción de detalle. El filtro temporal final ocurre antes de persistir, ver [`INGESTION_PIPELINE.md`](./INGESTION_PIPELINE.md).

### Hash de contenido SHA-256

Después de descargar y antes de extraer, el connector calcula el hash del payload:

```python
content_hash = sha256(response.content).hexdigest()

if content_hash == target.content_fingerprint:
    # Idéntico a la última captura: skip extracción
    # Pero aún registramos en AUDITORIA_SCRAPING que pasamos por aquí
    return None
```

Esto cubre el caso "la web no cambió ETag pero tampoco cambió el contenido" (cosa que pasa con servidores mal configurados). También cubre el caso "el contenido volvió a ser el mismo tras haber cambiado" (rollback).

---

## Scheduling adaptativo

**Objetivo**: dedicar más frecuencia a las fuentes que aportan eventos nuevos, menos a las que no, y especialmente bajar la frecuencia de Apify en municipios con buena cobertura gratis.

### Métrica base: `Coverage_Score`

Por cada par `(ID_Ciudad, Tipo_Fuente)`, se calcula:

```
Score_Eficiencia = Aportados_30d / max(Aportados_30d + Capturas_Sin_Evento_30d, 1)
```

- `Aportados_30d`: eventos únicos en los últimos 30 días cuya fuente principal es esta fuente.
- `Capturas_Sin_Evento_30d`: capturas que pasaron por el pipeline pero no produjeron evento.

Score 1.0 = perfecto, cada captura produce un evento útil. Score 0.0 = la fuente no aporta nada.

### Frecuencia sugerida

```python
def compute_suggested_frequency(coverage_score, eventos_aportados_30d, tipo_fuente):
    """
    Devuelve frecuencia en horas. Multiplicador sobre Frecuencia_Base_Horas.
    """
    if tipo_fuente in ('FUENTE_OFICIAL', 'AGREGADOR'):
        # Rutas gratis: más permisivas. Mantener frecuencia base salvo si está totalmente muerta.
        if eventos_aportados_30d == 0 and coverage_score == 0:
            return 168  # semanal
        return 24  # diario (default)

    elif tipo_fuente in ('RED_SOCIAL_PERFIL', 'RED_SOCIAL_QUERY'):
        # Social: el coste es relevante. Adaptarse a cobertura del municipio en las rutas gratis.
        coverage_municipal = get_total_coverage(municipio)  # score combinado de FUENTE_OFICIAL + AGREGADOR

        if coverage_municipal > 0.8:
            # Buena cobertura por rutas gratis: social solo como complemento ligero
            return 168  # semanal
        elif coverage_municipal > 0.4:
            return 48  # cada 2 días
        elif eventos_aportados_30d >= 5:
            # La social SÍ aporta eventos que las gratis no tienen
            return 12  # cada 12 horas
        else:
            return 24  # diario, default conservador
```

### Aplicación al scheduler

El job de cálculo de `COVERAGE_METRICS` corre cada noche (~3:00). Al terminar, actualiza el campo `Frecuencia_Sugerida_Horas` de cada par. El scheduler, al calcular `Next_Run_At` de un target, consulta `COVERAGE_METRICS` y multiplica por `Frecuencia_Sugerida_Horas / Frecuencia_Base_Horas`.

```sql
-- Job nocturno (pseudocódigo)
INSERT INTO COVERAGE_METRICS (
    ID_Ciudad, Tipo_Fuente,
    Eventos_Aportados_30d, Eventos_Confirmados_30d, Capturas_Sin_Evento_30d,
    Score_Eficiencia, Frecuencia_Sugerida_Horas
)
SELECT
    em.ID_Ciudad,
    bf.Tipo_Fuente,
    COUNT(DISTINCT CASE WHEN ef.Es_Fuente_Principal = 1
                        AND em.Fecha_Creacion >= NOW() - INTERVAL 30 DAY
                        THEN em.ID_Unico_Evento END) AS aportados,
    COUNT(DISTINCT CASE WHEN ef.Es_Fuente_Principal = 0
                        AND em.Fecha_Creacion >= NOW() - INTERVAL 30 DAY
                        THEN em.ID_Unico_Evento END) AS confirmados,
    (SELECT COUNT(*) FROM AUDITORIA_SCRAPING aud
       WHERE aud.ID_Unico_Evento IS NULL
         AND aud.Fecha_Ejecucion >= NOW() - INTERVAL 30 DAY
         AND aud.Motivo_Skip <> 'NA') AS sin_evento,
    ...
FROM EVENTOS_MASTER em
JOIN EVENTO_FUENTES ef ON ef.ID_Unico_Evento = em.ID_Unico_Evento
JOIN BIBLIOTECA_FUENTES bf ON bf.ID_Fuente = ef.ID_Fuente
GROUP BY em.ID_Ciudad, bf.Tipo_Fuente
ON DUPLICATE KEY UPDATE ...;
```

---

## Backoff por fuente muerta

Independiente del scheduling adaptativo (que es a nivel de municipio), el **backoff exponencial** opera a nivel de target individual cuando captura tras captura no produce nada útil.

### Reglas

| `Capturas_Vacias_Consecutivas` | Multiplicador de frecuencia |
|---|---|
| 0-4 | 1× (frecuencia normal) |
| 5 | 2× |
| 6 | 4× |
| 7 | 8× |
| 8+ | 16× (máximo, evita freezing total) |

```python
def apply_backoff(target):
    n = target.capturas_vacias_consecutivas
    if n < 5:
        return 1.0
    multiplier = min(2 ** (n - 4), 16)
    return float(multiplier)
```

### Recuperación

Al primer hit útil tras una racha de vacíos, `Capturas_Vacias_Consecutivas` se resetea a 0 y `Capturas_Utiles_Consecutivas` empieza a contar. La frecuencia vuelve a la sugerida por scheduling adaptativo.

### Detección de fuente realmente muerta

Si `Capturas_Vacias_Consecutivas >= 20` (con multiplicador 16× ya aplicado, equivale a meses sin aportar nada), se pone el target en `Estado = 'PAUSADO'` y se notifica al operador para revisión manual (la fuente cambió, la cuenta se borró, etc.).

---

## Cache perceptual de carteles

**Problema**: un cartel de la Generalitat de Cataluña anunciando "La Marató 2026" puede aparecer en posts de Instagram de cientos de cuentas (ajuntaments, asociaciones, voluntarios) durante semanas. Sin caché, cada aparición cuesta una llamada LLM-Vision (~$0.02). A escala provincial puede ser **cientos de dólares por evento viral**.

### Algoritmo

1. **Al descargar una imagen** de un post social, calcular pHash con `imagehash.phash(PIL.Image.open(...))`. Resultado: hex 32-char.

2. **Lookup determinista** en `PHASH_IMAGENES`:
   ```sql
   SELECT * FROM PHASH_IMAGENES WHERE Phash_Hex = %s
   ```

3. **Lookup con tolerancia** (si el lookup directo falla):
   ```sql
   -- pseudo: distancia Hamming <= 5 sobre BIT_COUNT(Phash_Hex XOR ?)
   SELECT *, BIT_COUNT(CONV(Phash_Hex, 16, 10) ^ CONV(?, 16, 10)) AS distancia
   FROM PHASH_IMAGENES
   WHERE distancia <= 5
   ORDER BY distancia ASC LIMIT 1
   ```
   (En MySQL puro este query es lento sin extensiones. Para producción a escala, mantener un índice secundario con buckets de pHash o usar una extensión como pgvector si se migra a Postgres.)

4. **Si hay match**:
   - Incrementar `Veces_Reutilizado`, actualizar `Fecha_Ultimo_Hit`.
   - Reutilizar `Extraccion_JSON` previamente cacheada.
   - Crear `EventCandidate` a partir de ese JSON, con la ciudad/idioma del nuevo contexto.

5. **Si no hay match**:
   - Llamar LLM-Vision.
   - Insertar fila nueva en `PHASH_IMAGENES` con `Extraccion_JSON = resultado`.

### Cuándo NO usar cache

- **Posts del organizador del evento**: si la imagen viene de la cuenta del propio organizador y trae detalles específicos (entradas, modalidad), conviene llamar LLM-Vision aunque haya cache hit. Heurística: si la cuenta tiene `Tipo_Organizador = 'PRIVADO'` y el caption menciona variables (precio diferente al cacheado, capacidad cambiada), invalidar caché.

- **pHash con muchos hits pero baja confianza de extracción**: si `PHASH_IMAGENES.Extraccion_JSON` tiene un score de confianza bajo (algunos campos vacíos), preferir re-extraer cuando aparece en un nuevo contexto que pueda completar la info.

### Métricas

- `phash_cache_hits_total` — contador
- `phash_cache_misses_total` — contador
- `phash_cache_hit_ratio` — gauge (calculado)
- `phash_savings_usd_total` — contador acumulado del coste de Vision evitado

---

## Cálculos de coste a escala

Estimaciones para tres escenarios de tamaño del sistema. Asume condiciones medias (Catalunya, 2026, modelos OpenAI gpt-4.1-mini y text-embedding-3-small, Apify Starter).

### Escenario A: piloto (10 municipios)

- Fuentes: ~3 web + 1 agregador (cubre todos) + ~5 social = 9 entradas en `BIBLIOTECA_FUENTES`.
- Targets activos: ~50.
- Eventos nuevos/mes: ~200 total.

**Coste mensual estimado**:

| Concepto | Cantidad | Coste unitario | Total |
|---|---|---|---|
| Apify Starter | 1 suscripción | $29 | $29 |
| Apify usage (~30 runs/día × $0.005 cada) | ~900 runs | $0.005 | $4.50 |
| LLM-Text (200 posts/mes con texto) | 200 | $0.002 | $0.40 |
| LLM-Vision (sin cache, 100 carteles) | 100 | $0.02 | $2.00 |
| LLM-Vision (con cache, ~30% hit) | 70 efectivos | — | $1.40 |
| Embeddings (200 eventos × 2 idiomas) | 400 | $0.00001 | $0.004 |
| Object storage (R2, ~5 GB imágenes) | 5 GB | $0.015/GB | $0.08 |
| **Total** | | | **~$34/mes** |

A esta escala, el cuello dominante es la suscripción base de Apify, no el uso.

### Escenario B: comarca (100 municipios)

- Fuentes: ~60 web + 3 agregadores + ~150 social = ~213 entradas.
- Targets activos: ~500.
- Eventos nuevos/mes: ~2.000.

**Coste mensual estimado**:

| Concepto | Cantidad | Coste unitario | Total |
|---|---|---|---|
| Apify Scale | 1 suscripción | $199 | $199 |
| Apify usage | ~9.000 runs | $0.005 | $45 |
| LLM-Text | 2.000 posts | $0.002 | $4 |
| LLM-Vision sin cache | ~1.000 carteles | $0.02 | $20 |
| LLM-Vision con cache 30% | 700 efectivos | — | $14 |
| Embeddings | 4.000 | $0.00001 | $0.04 |
| Object storage (~50 GB) | 50 GB | $0.015 | $0.75 |
| BD MySQL (Railway) | — | — | $20 |
| **Total** | | | **~$280/mes** |

El plan Scale de Apify se justifica por los $0.25/CU vs $0.30/CU en Starter; a este volumen el descuento compensa la diferencia de plan.

### Escenario C: nacional (3.000 municipios)

- Fuentes: ~1.500 web + 5 agregadores + ~2.000 social = ~3.500 entradas.
- Targets activos: ~10.000.
- Eventos nuevos/mes: ~30.000.

**Coste mensual estimado (con cascade aplicada y caché funcionando)**:

| Concepto | Cantidad | Coste unitario | Total |
|---|---|---|---|
| Apify Business | 1 suscripción | $999 | $999 |
| Apify usage | ~120.000 runs | $0.0045 | $540 |
| LLM-Text (filtrados por Gate ~50% reducción) | ~15.000 posts | $0.002 | $30 |
| LLM-Vision (Gate ~50% + cache ~40%) | ~5.400 carteles efectivos | $0.02 | $108 |
| Embeddings | 60.000 | $0.00001 | $0.60 |
| Object storage (~500 GB) | 500 GB | $0.015 | $7.50 |
| BD MySQL (cluster) | — | — | $200 |
| Compute (workers Railway) | 4 servicios | — | $80 |
| **Total** | | | **~$2.000/mes** |

**Importante**: sin el Gate y sin la caché perceptual, la cifra anterior se multiplicaría por 3-4× (entorno a $7.000-8.000/mes). La cascade no es opcional a esta escala.

### Para un coste por evento

A 30.000 eventos/mes y $2.000/mes, el **coste marginal por evento captado es ~$0.067**. Esto incluye captura, extracción, embeddings, storage de imagen e infraestructura. Suficientemente bajo para que un modelo de monetización publicitaria o B2B tenga margen.

---

## Métricas a monitorear

Métricas que el módulo debe exponer (vía Prometheus, OpenTelemetry o equivalente). Las métricas críticas se marcan con ⭐.

### Métricas de eficiencia

- ⭐ `gate_decisions_total{decision}` — contador por tipo de decisión del Gate.
- ⭐ `gate_savings_usd_total` — coste evitado acumulado por el Gate.
- ⭐ `phash_cache_hit_ratio` — gauge en `[0, 1]`.
- ⭐ `phash_savings_usd_total` — coste evitado acumulado por la caché.
- `cascade_filter_descartados_total{filtro}` — cuántos items descarta cada filtro (HEAD, sitemap, listado, hash).
- `coverage_score{ciudad,tipo_fuente}` — gauge actual del score.

### Métricas operacionales

- ⭐ `targets_pendientes` — gauge del backlog del scheduler.
- ⭐ `target_errores_total{tipo_fuente,tipo_error}` — contador de errores.
- `target_latencia_seconds{tipo_fuente}` — histograma del tiempo de procesamiento por target.
- `apify_runs_total{plataforma}` — contador de runs disparados.
- `llm_requests_total{tipo_extractor}` — contador de llamadas a LLM.
- `llm_tokens_total{tipo_extractor,token_type}` — tokens consumidos.

### Métricas de calidad

- `eventos_nuevos_total` — eventos persistidos como nuevos por unidad de tiempo.
- `eventos_actualizados_total` — eventos actualizados (merge con existente).
- `eventos_con_multi_fuente` — gauge de eventos con N>=2 fuentes (indicador de cross-source funcionando).
- `embeddings_pendientes` — gauge de eventos sin embedding al día.

### Alertas sugeridas

- `targets_pendientes > 1000` durante > 1 hora → workers saturados o scheduler caído.
- `target_errores_total{tipo_error='auth_failure'}` aumentando → credenciales expiradas (Apify, OpenAI).
- `coverage_score{tipo_fuente='RED_SOCIAL_*'} < 0.05` para un municipio activo → ruta social rota para ese municipio.
- `phash_cache_hit_ratio < 0.1` durante varios días → caché no está funcionando como esperado.
- `apify_cost_diario_usd > umbral` → posible loop o fuente fugada disparando demasiados runs.
