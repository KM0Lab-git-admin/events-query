# 🔧 Módulo de Ingesta — Pipeline detallado

**Versión:** 1.0
**Última actualización:** 2026-05-15

---

> 📌 **Docs relacionados (módulo de ingesta)**
> - [Visión general](./INGESTION_OVERVIEW.md)
> - [Modelo de datos del módulo](./INGESTION_DATA_MODEL.md)
> - [Pipeline detallado](./INGESTION_PIPELINE.md) ← estás aquí
> - [Optimización y escala](./INGESTION_OPTIMIZATION.md)
> - [Operaciones y observabilidad](./INGESTION_OPERATIONS.md)

---

## 📋 Tabla de contenidos

1. [Arquitectura de capas](#arquitectura-de-capas)
2. [Capa Scheduler](#capa-scheduler)
3. [Capa Connector](#capa-connector)
4. [Capa Extractor](#capa-extractor)
5. [Capa Gate pre-LLM](#capa-gate-pre-llm)
6. [Capa Merger](#capa-merger)
7. [Capa Persister](#capa-persister)
8. [Capa Embedder (async)](#capa-embedder-async)
9. [Ejemplo end-to-end](#ejemplo-end-to-end)

---

## Arquitectura de capas

El pipeline está dividido en siete capas, cada una con un contrato estricto. Cada capa se puede testear en aislamiento mockeando las anteriores. El orden es:

```
Scheduler → Connector → Extractor → Gate → Merger → Persister → Embedder
```

Las capas se comunican exclusivamente mediante los modelos Pydantic definidos en [`INGESTION_DATA_MODEL.md`](./INGESTION_DATA_MODEL.md). **No se permite saltarse capas** ni acceder a tablas internas de otra capa. Esta restricción mantiene el módulo refactorable.

Cada capa tiene un módulo Python correspondiente, sugerido bajo `app/ingestion/`:

```
app/ingestion/
├── __init__.py
├── scheduler.py
├── connectors/
│   ├── __init__.py
│   ├── base.py             # interfaz BaseConnector
│   ├── html_connector.py
│   ├── aggregator_connector.py
│   └── social_connector.py
├── extractors/
│   ├── __init__.py
│   ├── base.py
│   ├── structural_extractor.py
│   ├── mapping_extractor.py
│   ├── llm_text_extractor.py
│   └── llm_vision_extractor.py
├── gate.py
├── merger.py
├── persister.py
├── embedder.py
└── models.py               # los Pydantic intermedios
```

---

## Capa Scheduler

**Responsabilidad**: decidir qué se procesa, cuándo y con qué worker.

### Algoritmo

Bucle infinito (o ejecución periódica vía cron) que:

```python
def scheduler_tick():
    targets = db.execute("""
        SELECT * FROM SCRAPING_TARGETS
        WHERE Estado IN ('PENDIENTE', 'OK')
          AND Next_Run_At <= NOW()
        ORDER BY
            (SELECT Prioridad FROM BIBLIOTECA_FUENTES bf
             WHERE bf.ID_Fuente = SCRAPING_TARGETS.ID_Fuente) ASC,
            Next_Run_At ASC
        LIMIT %s
    """, [batch_size])

    for target in targets:
        # Reservar el target para evitar doble procesamiento
        result = db.execute("""
            UPDATE SCRAPING_TARGETS
            SET Estado = 'PROCESANDO', Last_Run_At = NOW()
            WHERE ID_Target = %s AND Estado IN ('PENDIENTE', 'OK')
        """, [target.id_target])

        if result.rowcount == 0:
            continue  # otro worker lo cogió

        enqueue_worker(process_target, target.id_target)
```

### Worker

```python
def process_target(id_target: int):
    target = load_target(id_target)
    fuente = load_fuente(target.id_fuente)

    try:
        # 1. Connector
        captura = run_connector(target, fuente)
        if captura is None:
            # cascade descartó: no hay cambios desde último run
            mark_target_ok(id_target, capturas_utiles=False)
            return

        # 2. Extractor
        candidates = run_extractor(captura, fuente)

        # 3-5. Gate (solo si fuente es social) + filtro temporal + merge
        processed = []
        for candidate in candidates:
            if is_social(fuente):
                decision = gate.evaluate(candidate)
                if decision.decision == 'REGISTRAR_FUENTE':
                    register_additional_source(decision.id_unico_evento_match, candidate)
                    log_audit(captura, motivo_skip='GATE_DUPLICADO')
                    continue
                elif decision.decision == 'DESCARTAR':
                    log_audit(captura, motivo_skip=decision.razon)
                    continue
                # else: EXTRAER → flujo normal
            if candidate.fecha_fin and candidate.fecha_fin < today():
                log_audit(captura, motivo_skip='FILTRO_TEMPORAL')
                continue
            processed.append(candidate)

        # 6. Merge
        merged_events = merger.merge(processed)

        # 7. Persist
        for merged in merged_events:
            persister.upsert(merged)

        # 8. Encolar embedding
        for merged in merged_events:
            if merged.es_evento_nuevo or merged.tags_changed:
                embedder.enqueue(merged.id_unico_evento)

        # Update target metadata
        mark_target_ok(id_target, capturas_utiles=len(merged_events) > 0)

    except Exception as e:
        mark_target_error(id_target, error=str(e))
        raise
```

### Cálculo del próximo `Next_Run_At`

Al terminar un target con éxito (o con resultado "sin cambios"), se actualiza `Next_Run_At`:

```python
def compute_next_run(target, capturas_utiles: bool):
    base_hours = target.frecuencia_base_horas
    coverage = get_coverage_score(target.id_fuente, target.tipo_target)

    # Adaptive multiplier según coverage
    if coverage and coverage > 0.8:
        # Buena cobertura → bajar frecuencia (intervalo mayor)
        adaptive_multiplier = 2.0
    elif coverage and coverage < 0.2:
        # Mala cobertura → considerar pausar
        adaptive_multiplier = 4.0
    else:
        adaptive_multiplier = 1.0

    # Backoff por capturas vacías consecutivas
    if target.capturas_vacias_consecutivas >= 5:
        backoff_multiplier = min(2 ** (target.capturas_vacias_consecutivas - 4), 16)
    else:
        backoff_multiplier = 1.0

    effective_hours = base_hours * adaptive_multiplier * backoff_multiplier
    return now() + timedelta(hours=effective_hours)
```

La fórmula concreta y los umbrales están en [`INGESTION_OPTIMIZATION.md`](./INGESTION_OPTIMIZATION.md).

---

## Capa Connector

**Responsabilidad**: capturar contenido externo y persistirlo como `CAPTURAS_RAW`.

### Interfaz común

```python
from abc import ABC, abstractmethod

class BaseConnector(ABC):
    """Captura contenido de una fuente externa.

    Cada implementación maneja un tipo de fuente. La interfaz es uniforme:
    recibe target+fuente, devuelve una RawCapture (o None si no hay cambios).

    Es responsable de:
    - Aplicar la cascade de filtros pre-coste antes de bajarse el payload
    - Calcular content_hash_sha256 para detección de cambios
    - Persistir la captura en CAPTURAS_RAW si hay payload nuevo
    - Actualizar Http_ETag, Http_LastModified, Content_Fingerprint en SCRAPING_TARGETS
    """

    @abstractmethod
    async def fetch(self, target: ScrapingTarget, fuente: BibliotecaFuente) -> Optional[RawCapture]:
        ...
```

### `HTMLConnector` — ruta web

Aplica la cascade completa de filtros pre-coste.

```python
class HTMLConnector(BaseConnector):

    async def fetch(self, target, fuente):
        if target.tipo_target == 'WEB_SITEMAP':
            return await self._fetch_sitemap(target, fuente)
        elif target.tipo_target == 'WEB_LISTADO':
            return await self._fetch_listado(target, fuente)
        elif target.tipo_target == 'WEB_DETALLE':
            return await self._fetch_detalle(target, fuente)

    async def _fetch_detalle(self, target, fuente):
        # 1. HEAD check
        head_response = await self.client.head(target.url_target, headers={
            'If-None-Match': target.http_etag or '',
            'If-Modified-Since': target.http_lastmodified or '',
        })
        if head_response.status_code == 304:
            return None  # sin cambios, skip

        # 2. GET completo
        response = await self.client.get(target.url_target)
        content_hash = sha256(response.content).hexdigest()

        # 3. Comparar fingerprint
        if content_hash == target.content_fingerprint:
            return None  # contenido idéntico al último, skip

        # 4. Persistir captura
        return RawCapture(
            id_target=target.id_target,
            id_fuente=fuente.id_fuente,
            fecha_captura=now(),
            content_type=response.headers.get('content-type', 'text/html'),
            content_hash_sha256=content_hash,
            payload_bytes=response.content,
            payload_size_bytes=len(response.content),
        )

    async def _fetch_listado(self, target, fuente):
        # Similar pero, antes de bajar el payload completo, parsea solo los
        # items del listado y filtra por fecha. Solo descarga páginas de
        # detalle de los items con fecha futura. Cada detalle se persiste
        # como un nuevo target con tipo_target='WEB_DETALLE'.
        ...

    async def _fetch_sitemap(self, target, fuente):
        # Parsea sitemap.xml. Para cada URL con lastmod posterior a la última
        # captura, crea/actualiza targets WEB_DETALLE.
        ...
```

### `AggregatorConnector` — ruta agregador

Pide a la API solo lo relevante. La cascade aquí es "el propio request ya filtra".

```python
class AggregatorConnector(BaseConnector):

    async def fetch(self, target, fuente):
        config = fuente.config_json
        municipios_activos = get_active_municipios()  # de COVERAGE_METRICS y BIBLIOTECA_FUENTES

        all_items = []
        for municipio in municipios_activos:
            params = self._build_query_params(config, municipio)
            response = await self.client.get(target.url_target, params=params)

            if response.status_code == 429:
                # Rate limit: backoff exponencial
                raise RateLimitError(retry_after=int(response.headers.get('Retry-After', 60)))

            items = response.json().get(config['items_field'], [])
            all_items.extend(items)

        # Calcular hash sobre el conjunto agregado
        canonical = json.dumps(all_items, sort_keys=True).encode()
        content_hash = sha256(canonical).hexdigest()

        if content_hash == target.content_fingerprint:
            return None

        return RawCapture(
            id_target=target.id_target,
            id_fuente=fuente.id_fuente,
            fecha_captura=now(),
            content_type='application/json',
            content_hash_sha256=content_hash,
            payload_bytes=canonical,
            payload_size_bytes=len(canonical),
        )

    def _build_query_params(self, config, municipio):
        # Mapeo de campos del config a query params
        # Ejemplo para Eventbrite:
        return {
            'location.latitude':  municipio.latitud,
            'location.longitude': municipio.longitud,
            'location.within':    config.get('radio_km', 10) + 'km',
            'start_date.range_start': today().isoformat() + 'T00:00:00',
            'sort_by': 'date',
        }
```

### `SocialConnector` — ruta social

Encapsula la llamada a Apify u otro provider.

```python
class SocialConnector(BaseConnector):

    APIFY_ACTORS = {
        'INSTAGRAM_PROFILE': 'apify/instagram-scraper',
        'FACEBOOK_PAGE': 'apify/facebook-pages-scraper',
        'X_PROFILE': 'apidojo/tweet-scraper',
        'TIKTOK_PROFILE': 'clockworks/free-tiktok-scraper',
    }

    async def fetch(self, target, fuente):
        # Para social NO hay HEAD/sitemap. La cascade ocurre en el scheduling
        # adaptativo (decidir si correr este target hoy o no).

        actor_id = self._select_actor(fuente)
        input_params = self._build_actor_input(target, fuente)

        # Lanza run de Apify y espera resultado
        run_result = await self.apify.run_actor(actor_id, input_params, timeout_s=600)

        posts = run_result.get_items()
        coste_run = run_result.get_cost_usd()

        canonical = json.dumps(posts, sort_keys=True).encode()
        content_hash = sha256(canonical).hexdigest()

        if content_hash == target.content_fingerprint:
            # Sin cambios: aún así contabilizamos el coste pagado a Apify
            log_audit_cost(target.id_target, coste_run)
            return None

        capture = RawCapture(
            id_target=target.id_target,
            id_fuente=fuente.id_fuente,
            fecha_captura=now(),
            content_type='application/json',
            content_hash_sha256=content_hash,
            payload_bytes=canonical,
            payload_size_bytes=len(canonical),
        )
        capture.coste_estimado_usd = coste_run
        return capture

    def _build_actor_input(self, target, fuente):
        # Ejemplo Instagram profile
        return {
            'usernames': [fuente.handle],
            'resultsLimit': 25,
            'addParentData': False,
        }
```

---

## Capa Extractor

**Responsabilidad**: transformar `RawCapture` en lista de `EventCandidate`.

### Interfaz común

```python
class BaseExtractor(ABC):
    """Extrae EventCandidates de una captura.

    Una captura puede generar 0..N candidatos.
    El extractor elige la implementación según content_type y fuente.
    """

    @abstractmethod
    async def extract(self, captura: RawCapture, fuente: BibliotecaFuente) -> list[EventCandidate]:
        ...
```

### `StructuralExtractor` — para web HTML

Extrae sin LLM cuando hay estructura semántica reconocible.

```python
class StructuralExtractor(BaseExtractor):

    async def extract(self, captura, fuente):
        html = captura.payload_bytes.decode('utf-8', errors='replace')
        soup = BeautifulSoup(html, 'lxml')

        # Estrategia 1: JSON-LD
        candidates = self._try_jsonld(soup, captura, fuente)
        if candidates:
            return candidates

        # Estrategia 2: microdata
        candidates = self._try_microdata(soup, captura, fuente)
        if candidates:
            return candidates

        # Estrategia 3: selectores CSS configurados en fuente.config_json
        candidates = self._try_css_selectors(soup, captura, fuente)
        if candidates:
            return candidates

        # Estrategia 4: fallback a LLM (solo si está habilitado en config)
        if fuente.config_json.get('llm_fallback', False):
            return await LLMTextExtractor().extract(captura, fuente)

        return []

    def _try_jsonld(self, soup, captura, fuente):
        candidates = []
        for tag in soup.find_all('script', type='application/ld+json'):
            try:
                data = json.loads(tag.string)
            except json.JSONDecodeError:
                continue
            for item in self._iter_event_items(data):
                candidate = self._jsonld_to_candidate(item, captura, fuente)
                if candidate:
                    candidates.append(candidate)
        return candidates

    def _jsonld_to_candidate(self, item, captura, fuente):
        # Mapea schema.org/Event a EventCandidate
        if item.get('@type') != 'Event':
            return None

        return EventCandidate(
            id_captura=captura.id_captura,
            id_fuente=fuente.id_fuente,
            extractor_usado='structural_jsonld',
            url_origen=item.get('url') or captura.payload_storage_url,
            score_calidad=0.90,
            id_ciudad=fuente.id_ciudad,
            cp_evento=self._extract_cp(item),
            lugar_nombre=item.get('location', {}).get('name'),
            direccion_fisica=item.get('location', {}).get('address', {}).get('streetAddress'),
            coordenadas=self._extract_geo(item),
            titulo_es=item.get('name'),
            titulo_cat=None,  # se llenará por traducción async si falta
            idioma_origen=fuente.config_json.get('idioma_origen', 'ca'),
            desc_larga_es=item.get('description'),
            fecha_inicio=parse_date(item.get('startDate')),
            fecha_fin=parse_date(item.get('endDate')),
            hora_inicio=parse_time(item.get('startDate')),
            hora_fin=parse_time(item.get('endDate')),
            es_gratuito=self._infer_gratis(item),
            precio_euros=self._extract_price(item),
            link_entradas_inscripcion=item.get('offers', {}).get('url'),
            organizador_nombre=item.get('organizer', {}).get('name'),
            imagen_url_original=item.get('image'),
            tags_ia=[],  # se generan en LLM async si no vienen estructurados
        )
```

### `MappingExtractor` — para agregadores

Mapeo declarativo configurado en `BIBLIOTECA_FUENTES.Config_JSON`.

```python
class MappingExtractor(BaseExtractor):

    async def extract(self, captura, fuente):
        data = json.loads(captura.payload_bytes)
        mapping = fuente.config_json['mapping']
        items_field = mapping['items_field']

        candidates = []
        for item in data.get(items_field, []):
            candidate = self._apply_mapping(item, mapping, captura, fuente)
            if candidate:
                candidates.append(candidate)
        return candidates

    def _apply_mapping(self, item, mapping, captura, fuente):
        # mapping ejemplo:
        # {
        #   "items_field": "events",
        #   "fields": {
        #     "titulo_es": "name.text",
        #     "fecha_inicio": "start.local",
        #     "lugar_nombre": "venue.name",
        #     "url_origen": "url",
        #     "imagen_url_original": "logo.original.url"
        #   },
        #   "score_base": 0.80
        # }
        try:
            return EventCandidate(
                id_captura=captura.id_captura,
                id_fuente=fuente.id_fuente,
                extractor_usado=f'mapping_{fuente.url_base}',
                url_origen=self._jpath(item, mapping['fields']['url_origen']),
                score_calidad=mapping.get('score_base', 0.80),
                id_ciudad=fuente.id_ciudad,
                titulo_es=self._jpath(item, mapping['fields']['titulo_es']),
                fecha_inicio=parse_date(self._jpath(item, mapping['fields']['fecha_inicio'])),
                lugar_nombre=self._jpath(item, mapping['fields'].get('lugar_nombre')),
                imagen_url_original=self._jpath(item, mapping['fields'].get('imagen_url_original')),
                # ... resto de campos según mapping
            )
        except (KeyError, ValueError):
            return None

    def _jpath(self, obj, path):
        """Resuelve un path tipo 'a.b.c' sobre un dict anidado."""
        if not path:
            return None
        for part in path.split('.'):
            if obj is None:
                return None
            obj = obj.get(part) if isinstance(obj, dict) else None
        return obj
```

### `LLMTextExtractor` — para captions de posts

Usa un LLM con function calling/structured output para extraer eventos de texto libre.

```python
class LLMTextExtractor(BaseExtractor):

    PROMPT_SYSTEM = """Eres un extractor de eventos locales.
Analiza el texto de un post de redes sociales y, si describe un evento
futuro, extrae sus datos estructurados.

REGLAS:
- Si el texto NO describe un evento (es promo genérica, opinión, etc), devuelve evento=null.
- Si describe varios eventos, devuelve una lista.
- Si la fecha es relativa ("este viernes"), conviértela a fecha absoluta usando la fecha del post.
- Si falta la fecha, devuelve evento=null. NO inventes fechas.
- Si el idioma del texto es catalán, llena titulo_cat y desc_larga_cat. Si es castellano, titulo_es y desc_larga_es. NO traduzcas.
- Tags: extrae 5-10 tags semánticos (no hashtags, sino conceptos: "infantil", "música en vivo", "comida", "deporte").
"""

    async def extract(self, captura, fuente):
        post_data = json.loads(captura.payload_bytes)
        candidates = []

        for post in post_data:
            response = await self.openai.responses.create(
                model='gpt-4.1-mini',
                input=[
                    {'role': 'system', 'content': self.PROMPT_SYSTEM},
                    {'role': 'user', 'content': self._build_user_prompt(post)},
                ],
                response_format={'type': 'json_schema', 'json_schema': EVENT_EXTRACTION_SCHEMA},
            )
            extracted = json.loads(response.output_text)

            for ev in extracted.get('eventos', []):
                candidate = self._extracted_to_candidate(ev, post, captura, fuente)
                if candidate:
                    candidates.append(candidate)

        return candidates

    def _build_user_prompt(self, post):
        return f"""
FECHA_POST: {post['timestamp']}
AUTOR: {post['username']}
TEXTO:
{post['caption']}

URL_POST: {post['url']}
"""
```

### `LLMVisionExtractor` — para carteles en imágenes

```python
class LLMVisionExtractor(BaseExtractor):

    PROMPT_SYSTEM = """Analiza la imagen. Si es un cartel de evento, extrae:
- Título del evento
- Fecha y hora (si están visibles)
- Lugar (si está visible)
- Organizador (si está visible)
- Tipo de evento (concierto, taller, exposición, etc.)

Si la imagen NO es un cartel de evento (foto personal, comida, etc), devuelve evento=null.
NO inventes datos que no estén visibles en la imagen.
"""

    async def extract(self, captura, fuente):
        post_data = json.loads(captura.payload_bytes)
        candidates = []

        for post in post_data:
            for img_url in post.get('images', []):
                # Bajar la imagen
                img_bytes = await self._download_image(img_url)
                phash = self._compute_phash(img_bytes)

                # Cache hit?
                cached = await self.phash_cache.lookup(phash)
                if cached:
                    candidate = self._cached_to_candidate(cached, post, captura, fuente, phash)
                    if candidate:
                        candidates.append(candidate)
                    continue

                # No cache: llamar Vision
                response = await self.openai.responses.create(
                    model='gpt-4.1-mini',
                    input=[{
                        'role': 'system', 'content': self.PROMPT_SYSTEM
                    }, {
                        'role': 'user',
                        'content': [
                            {'type': 'text', 'text': f'FECHA_POST: {post["timestamp"]}'},
                            {'type': 'input_image', 'image_url': img_url},
                        ],
                    }],
                    response_format={'type': 'json_schema', 'json_schema': CARTEL_EXTRACTION_SCHEMA},
                )
                extracted = json.loads(response.output_text)

                # Cachear el resultado para futuras apariciones del cartel
                await self.phash_cache.store(phash, extracted, img_bytes)

                if extracted.get('evento'):
                    candidate = self._extracted_to_candidate(
                        extracted['evento'], post, captura, fuente, phash, img_url
                    )
                    if candidate:
                        candidates.append(candidate)

        return candidates
```

---

## Capa Gate pre-LLM

**Responsabilidad**: decidir si un post merece extracción LLM o si su contenido ya está cubierto por una ruta gratis.

**Solo se aplica a fuentes social** (`Tipo_Fuente IN ('RED_SOCIAL_PERFIL', 'RED_SOCIAL_QUERY')`).

**Solo se aplica antes de extracción LLM**, no antes de Apify (Apify ya pagó por el lote).

### Algoritmo

```python
class Gate:

    SEMANTIC_SIMILARITY_THRESHOLD = 0.82
    TEMPORAL_WINDOW_DAYS = 60  # eventos conocidos dentro de ±60 días

    async def evaluate(self, post: SocialPost, fuente: BibliotecaFuente) -> GateDecision:
        # Paso 1: extraer señales mínimas del post sin LLM
        signals = self._extract_signals(post)

        if not signals.has_event_indicators:
            return GateDecision(
                decision='EXTRAER',  # pasamos al LLM, que decidirá si es evento o no
                razon='post_sin_indicadores_filtrar_via_llm',
            )

        # Paso 2: fingerprint determinista
        fingerprint = self._compute_fingerprint(signals, fuente.id_ciudad)
        existing = await self._lookup_fingerprint(fingerprint, fuente.id_ciudad)
        if existing:
            return GateDecision(
                decision='REGISTRAR_FUENTE',
                id_unico_evento_match=existing.id_unico_evento,
                score_match=1.0,
                metodo_match='FINGERPRINT',
                razon='fingerprint_exact_match',
            )

        # Paso 3: similitud semántica contra eventos conocidos en ventana temporal
        candidates_existing = await self._fetch_eventos_recientes(
            id_ciudad=fuente.id_ciudad,
            window_days=self.TEMPORAL_WINDOW_DAYS,
        )

        if not candidates_existing:
            return GateDecision(decision='EXTRAER', razon='no_eventos_recientes_en_municipio')

        # Generar embedding del caption del post (es un coste menor que Vision)
        post_embedding = await self.embedder.embed(signals.caption_normalized)

        best_match = None
        best_score = 0.0
        for existing in candidates_existing:
            sim = cosine_similarity(post_embedding, existing.embedding)
            if sim > best_score:
                best_score = sim
                best_match = existing

        if best_score >= self.SEMANTIC_SIMILARITY_THRESHOLD:
            return GateDecision(
                decision='REGISTRAR_FUENTE',
                id_unico_evento_match=best_match.id_unico_evento,
                score_match=best_score,
                metodo_match='SEMANTIC',
                razon=f'semantic_match_{best_score:.3f}',
            )

        return GateDecision(decision='EXTRAER', razon='no_match_proceder_con_llm')

    def _extract_signals(self, post):
        # Heurística cheap sin LLM
        caption = post.caption or ''
        return Signals(
            has_event_indicators=self._has_event_keywords(caption),
            caption_normalized=normalize_text(caption),
            fechas_detectadas=detect_dates_in_text(caption),
            lugares_detectados=detect_places(caption),
        )

    def _compute_fingerprint(self, signals, id_ciudad):
        # Determinista: ciudad + título normalizado + fecha
        # Si no hay fecha clara, usar primera fecha detectada o hash del título solo
        first_date = signals.fechas_detectadas[0] if signals.fechas_detectadas else None
        title_norm = self._extract_title_candidate(signals.caption_normalized)
        return sha256(f"{id_ciudad}|{title_norm}|{first_date}".encode()).hexdigest()
```

### Métricas a registrar

Por cada decisión del Gate:

- `gate_decisions_total{decision=EXTRAER|REGISTRAR_FUENTE|DESCARTAR}` — contador
- `gate_decision_latency_seconds` — histograma
- `gate_semantic_score` — histograma (solo cuando hace lookup semántico)
- `gate_savings_usd_estimated` — contador de coste evitado (LLM-Vision skipped)

---

## Capa Merger

**Responsabilidad**: agrupar `EventCandidate`s que se refieren al mismo evento real y producir un `MergedEvent`.

### Algoritmo

```python
class Merger:

    async def merge(self, candidates: list[EventCandidate]) -> list[MergedEvent]:
        # Agrupar candidatos por fingerprint
        groups = defaultdict(list)
        for candidate in candidates:
            fp = self._compute_fingerprint(candidate)
            groups[fp].append(candidate)

        merged_events = []
        for fp, group in groups.items():
            # Buscar si ya existe un evento con este fingerprint en BD
            existing = await self._lookup_event_by_fingerprint(fp, group[0].id_ciudad)

            if existing:
                merged = self._merge_into_existing(existing, group)
            else:
                merged = self._merge_new(fp, group)

            merged_events.append(merged)

        return merged_events

    def _compute_fingerprint(self, candidate):
        title_norm = normalize_for_fingerprint(candidate.titulo_es or candidate.titulo_cat)
        return sha256(f"{candidate.id_ciudad}|{title_norm}|{candidate.fecha_inicio}".encode()).hexdigest()

    def _merge_new(self, fingerprint, group):
        # Ordenar candidatos por calidad: la fuente principal es la de score más alto
        sorted_group = sorted(group, key=lambda c: c.score_calidad, reverse=True)
        principal = sorted_group[0]
        secundarios = sorted_group[1:]

        # Empezar con todos los campos de la principal
        merged = MergedEvent(
            id_unico_evento=fingerprint,
            es_evento_nuevo=True,
            metodo_ingesta='SCRAPING',
            fuente_id=self._classify_fuente_id(principal),
            fuente_url_original=principal.url_origen,
            id_ciudad=principal.id_ciudad,
            # ... copiar campos de principal
        )

        # Para cada campo, aplicar política "mejor dato gana"
        for secundario in secundarios:
            self._merge_field_by_field(merged, secundario)

        # Construir las fuentes
        merged.fuentes = [
            EventFuenteRecord(
                id_fuente=principal.id_fuente,
                id_captura=principal.id_captura,
                url_origen=principal.url_origen,
                es_fuente_principal=True,
                aporto_extraccion=True,
                score_calidad=principal.score_calidad,
            )
        ] + [
            EventFuenteRecord(
                id_fuente=s.id_fuente,
                id_captura=s.id_captura,
                url_origen=s.url_origen,
                es_fuente_principal=False,
                aporto_extraccion=True,
                score_calidad=s.score_calidad,
            )
            for s in secundarios
        ]

        return merged
```

### Política "mejor dato por campo"

Reglas concretas, en orden de prioridad por campo:

| Campo | Fuente con prioridad | Razón |
|---|---|---|
| `lugar_nombre`, `direccion_fisica`, `coordenadas` | FUENTE_OFICIAL > AGREGADOR > SOCIAL | La web del ayuntamiento conoce la geografía local mejor |
| `precio_euros`, `link_entradas_inscripcion` | AGREGADOR > FUENTE_OFICIAL > SOCIAL | Los agregadores comerciales son la fuente de verdad para tickets |
| `desc_larga_es`, `desc_larga_cat` | El más largo (con `score_calidad >= 0.7`) | Más texto = más contexto para el embedding |
| `imagen_url_original` | El primero que tenga imagen | Cualquier imagen > sin imagen |
| `titulo_es`, `titulo_cat` | El idioma origen wins primero, el más limpio (sin emojis) si empate | Calidad lingüística |
| `fecha_inicio`, `fecha_fin` | Si difieren entre fuentes → marcar para revisión manual, usar el de mayor `score_calidad` | Conflicto de fechas es señal de problema |
| `organizador_nombre` | FUENTE_OFICIAL > AGREGADOR > SOCIAL | La web suele tener el organizador correcto |
| `tags_ia` | Unión de todas las fuentes (deduplicada) | Más tags = mejor búsqueda semántica |
| `es_gratuito` | FUENTE_OFICIAL si está; si no, AGREGADOR | |

La función `_merge_field_by_field` aplica estas reglas. Es la **lógica más sensible del módulo** porque determina la calidad final del registro. Debe estar exhaustivamente testeada.

---

## Capa Persister

**Responsabilidad**: escribir `MergedEvent` en BD de forma transaccional.

### Transacción de inserción de un evento nuevo

```python
class Persister:

    async def upsert(self, merged: MergedEvent):
        async with self.db.transaction():
            if merged.es_evento_nuevo:
                await self._insert_new(merged)
            else:
                await self._update_existing(merged)

    async def _insert_new(self, merged):
        # 1. EVENTOS_MASTER
        await self.db.execute("""
            INSERT INTO EVENTOS_MASTER (
                ID_Unico_Evento, Metodo_Ingesta, ID_Usuario_Carga, Fuente_ID,
                Fuente_URL_Original, Estado, ID_Ciudad, CP_Evento, Lugar_Nombre,
                Direccion_Fisica, Coordenadas_JSON, Tipo_Organizador,
                Organizador_Nombre, Organizador_Web, Es_Patrocinado, Idioma_Origen,
                Titulo_CAT, Titulo_ES, Desc_Larga_CAT, Desc_Larga_ES,
                Tags_IA_Array, Es_Gratuito, Precio_Euros, Requiere_Inscripcion,
                Aforo_Maximo, Plazas_Disponibles, Link_Entradas_Inscripcion,
                Imagen_Principal_URL
            ) VALUES (...)
        """, [merged.id_unico_evento, merged.metodo_ingesta, ...])

        # 2. EVENTO_HORARIOS (uno por slot)
        for horario in merged.horarios:
            await self.db.execute("INSERT INTO EVENTO_HORARIOS ...", [...])

        # 3. EVENTO_CATEGORIAS
        for categoria in merged.categorias:
            await self.db.execute("INSERT INTO EVENTO_CATEGORIAS ...", [...])

        # 4. EVENTO_FUENTES (una por fuente)
        for fuente in merged.fuentes:
            await self.db.execute("INSERT INTO EVENTO_FUENTES ...", [...])

        # 5. Imágenes: descargar a storage propio y registrar en BINARIOS_STORAGE
        for img in merged.imagenes:
            binario_url = await self._download_and_store_image(img.url_original)
            id_binario = await self.db.execute("INSERT INTO BINARIOS_STORAGE ...", [...])
            if img.phash:
                await self.db.execute("""
                    INSERT INTO PHASH_IMAGENES (Phash_Hex, ID_Binario, ...)
                    VALUES (...)
                    ON DUPLICATE KEY UPDATE
                        Veces_Reutilizado = Veces_Reutilizado + 1,
                        Fecha_Ultimo_Hit = NOW()
                """, [...])
            if img.es_principal:
                await self.db.execute(
                    "UPDATE EVENTOS_MASTER SET Imagen_Principal_URL=%s WHERE ID_Unico_Evento=%s",
                    [binario_url, merged.id_unico_evento],
                )

    async def _download_and_store_image(self, url_original):
        # 1. Descargar
        response = await self.client.get(url_original, follow_redirects=True)
        img_bytes = response.content

        # 2. Detectar formato y validar
        fmt = detect_image_format(img_bytes)  # JPG, PNG, WEBP

        # 3. Generar 2 tamaños (thumbnail, medium)
        thumbnail = resize_image(img_bytes, 400)
        medium = resize_image(img_bytes, 1080)

        # 4. Subir a object storage
        key_original = f"events/{event_id}/{uuid4()}.original.{fmt.lower()}"
        key_thumb = f"events/{event_id}/{uuid4()}.thumb.jpg"
        key_medium = f"events/{event_id}/{uuid4()}.medium.jpg"

        await self.storage.put(key_original, img_bytes)
        await self.storage.put(key_thumb, thumbnail)
        await self.storage.put(key_medium, medium)

        # 5. Devolver URL canónica (la "medium")
        return self.storage.public_url(key_medium)
```

### Actualización de evento existente

Si el merge identificó un evento existente y vienen nuevas fuentes confirmándolo:

- No se reescriben campos a menos que la política "mejor dato" determine cambio.
- Sí se insertan nuevas filas en `EVENTO_FUENTES`.
- Sí se descargan imágenes nuevas si la fuente nueva trae imagen.
- Si algún campo cambia, se encola job de regenerar embedding.

---

## Capa Embedder (async)

**Responsabilidad**: generar embeddings para los tags de eventos, en background, después de persistir.

```python
class Embedder:

    MODEL = 'text-embedding-3-small'
    DIMENSIONS = 1536

    async def process_pending(self):
        # Eventos sin embedding o con embedding obsoleto
        pending = await self.db.execute("""
            SELECT em.ID_Unico_Evento, em.Tags_IA_Array, em.Titulo_ES, em.Titulo_CAT
            FROM EVENTOS_MASTER em
            LEFT JOIN EVENTO_EMBEDDINGS ee
              ON ee.ID_Unico_Evento = em.ID_Unico_Evento
             AND ee.Modelo = %s
             AND ee.Idioma = 'es'
            WHERE em.Estado = 'ACTIVO'
              AND (ee.ID_Embedding IS NULL
                   OR ee.Texto_Fuente_Hash <> %s)
            LIMIT 100
        """, [self.MODEL, self._compute_text_hash])

        for event in pending:
            await self._embed_event(event, idioma='es')
            await self._embed_event(event, idioma='ca')

    async def _embed_event(self, event, idioma):
        text = self._build_embedding_text(event, idioma)
        text_hash = sha256(text.encode()).hexdigest()

        response = await self.openai.embeddings.create(
            model=self.MODEL,
            input=text,
        )
        vector = response.data[0].embedding

        await self.db.execute("""
            INSERT INTO EVENTO_EMBEDDINGS
                (ID_Unico_Evento, Idioma, Modelo, Dimensiones, Vector_JSON, Texto_Fuente_Hash)
            VALUES (%s, %s, %s, %s, %s, %s)
            ON DUPLICATE KEY UPDATE
                Vector_JSON = VALUES(Vector_JSON),
                Texto_Fuente_Hash = VALUES(Texto_Fuente_Hash),
                Fecha_Generacion = NOW()
        """, [event.id_unico_evento, idioma, self.MODEL, self.DIMENSIONS, json.dumps(vector), text_hash])

    def _build_embedding_text(self, event, idioma):
        # Construye el texto a embeber: tags + título + descripción corta
        titulo = event.titulo_es if idioma == 'es' else event.titulo_cat
        tags = ' '.join(event.tags_ia_array or [])
        return f"{titulo}. {tags}"
```

---

## Ejemplo end-to-end

Un caso concreto siguiendo el pipeline completo para un mismo evento captado desde tres fuentes:

**Evento**: "Concert d'inauguració Festes de Sant Roc 2026", Malgrat de Mar, 16/8/2026 21:00, Pl. de l'Ajuntament.

### Captura 1 — Web del ajuntament (T+0h)

- Scheduler dispara target tipo `WEB_LISTADO` apuntando a `https://malgrat.cat/agenda/`.
- `HTMLConnector` hace HEAD, ETag cambia, descarga listado.
- Parsea listado, detecta link a `/agenda/concert-sant-roc-2026/`, crea target `WEB_DETALLE` y lo dispara.
- Detalle descargado contiene JSON-LD `schema.org/Event` con todos los campos.
- `StructuralExtractor` produce un `EventCandidate` con `score_calidad=0.92`.
- `Gate` no aplica (fuente no es social).
- `Merger`: fingerprint nuevo → crea evento.
- `Persister`: inserta `EVENTOS_MASTER` con `Fuente_ID='URL_ESTRUCTURAL'`, inserta `EVENTO_FUENTES` con `Es_Fuente_Principal=1`. Descarga imagen `cartell.jpg`, calcula pHash `0xabc...`, almacena en R2, registra en `BINARIOS_STORAGE` y `PHASH_IMAGENES`.
- `Embedder`: encola job, genera embeddings ES y CA.

### Captura 2 — API Diputació BCN (T+6h)

- Scheduler dispara target tipo `API_AGREGADOR`.
- `AggregatorConnector` pide a la API con `municipi=malgrat-de-mar&data_inici=2026-05-15&data_fi=2026-09-15`.
- Respuesta JSON contiene 12 eventos. Hash de payload nuevo (no idéntico al anterior).
- `MappingExtractor` aplica el mapping configurado, produce 12 `EventCandidate`s con `score_calidad=0.78`.
- Uno de ellos tiene el mismo `fingerprint(id_ciudad=malgrat, titulo_norm='concert inauguracio festes sant roc 2026', fecha=2026-08-16)` que el evento ya persistido.
- `Merger`: detecta evento existente. Aplica política "mejor dato por campo". `lugar_nombre`: la web (FUENTE_OFICIAL) gana (ya en BD). `link_entradas_inscripcion`: la API tiene URL de venta de entradas, gana la API → actualiza.
- `Persister`: actualiza `Link_Entradas_Inscripcion` en `EVENTOS_MASTER`. Inserta fila nueva en `EVENTO_FUENTES` con `Es_Fuente_Principal=0`, `Aporto_Extraccion=1`, `score_calidad=0.78`.

### Captura 3 — Instagram @ajmalgrat (T+12h)

- Scheduler dispara target `SOCIAL_PERFIL`.
- `SocialConnector` llama Apify Actor, recibe los últimos 25 posts. Coste: $0.012.
- Post #3 tiene un caption "Aquest dissabte 16 d'agost, no us perdeu el concert d'inauguració..." más una imagen (cartel).
- Para cada post, `Gate.evaluate(post)`:
  - Signals: tiene keywords de evento, fecha detectada "16 d'agost", lugar implícito Malgrat.
  - Fingerprint determinista con título extraído del caption → `match` con el evento existente.
  - Decision: `REGISTRAR_FUENTE`, `id_unico_evento_match=...`, `metodo_match='FINGERPRINT'`.
- `Persister`: NO llama LLM-Text ni LLM-Vision. Inserta fila en `EVENTO_FUENTES` con `Es_Fuente_Principal=0`, `Aporto_Extraccion=0`, `URL_Origen=https://instagram.com/p/...`.
- `AUDITORIA_SCRAPING`: fila con `Motivo_Skip='GATE_DUPLICADO'`, `Resultado='OK'`, `Detalle='fingerprint match con abc123, ahorro estimado $0.015 en LLM-Vision'`.

### Estado final en BD

```
EVENTOS_MASTER:
  ID_Unico_Evento: abc123
  Fuente_ID: URL_ESTRUCTURAL
  Fuente_URL_Original: https://malgrat.cat/agenda/concert-sant-roc-2026/
  Link_Entradas_Inscripcion: https://entradesdelapatum.cat/concert-sant-roc-2026  (vino del agregador)
  Imagen_Principal_URL: https://cdn.km0lab.com/events/abc123/xyz.medium.jpg  (storage propio)

EVENTO_FUENTES:
  (id_fuente=malgrat_web,         es_principal=1, aporto_extraccion=1, score=0.92)
  (id_fuente=diputacio_bcn_api,   es_principal=0, aporto_extraccion=1, score=0.78)
  (id_fuente=instagram_ajmalgrat, es_principal=0, aporto_extraccion=0, score=0.60)

EVENTO_EMBEDDINGS:
  (idioma=es, modelo=text-embedding-3-small, vector=[...])
  (idioma=ca, modelo=text-embedding-3-small, vector=[...])

BINARIOS_STORAGE:
  (ID_Binario=42, URL=https://cdn.km0lab.com/.../abc123-medium.jpg, Phash en PHASH_IMAGENES)

AUDITORIA_SCRAPING:
  3 filas con Resultado=OK, una con Motivo_Skip=GATE_DUPLICADO
```

**Coste total**: ~$0.012 de Apify + ~$0.001 de embeddings + 0 de LLM-Vision (ahorrado por el Gate).

**Si el Gate no existiera**: se habrían llamado dos LLMs adicionales por el post de IG (Text + Vision), añadiendo ~$0.02 al coste. A escala de 3.000 municipios con cuentas activas, este ahorro es lo que hace viable el módulo.

---

## CLI de referencia (`app.ingestion.cli`)

Proceso batch genérico (misma `.env` que la API: `DB_*`, `OPENAI_API_KEY` obligatoria en Settings aunque esta CLI no llame a OpenAI):

```bash
# venv activado; BD con esquema aplicado (SQL/SCHEMA_SQL_FINAL.sql)
python -m app.ingestion.cli --url "https://ejemplo.cat/ruta/agenda" --cp 08380 --ciudad-id 1 --poblacion "Malgrat de Mar"

# Sin MySQL (solo fetch + extract + merge en memoria)
python -m app.ingestion.cli --url "https://ejemplo.cat/ruta/agenda" --dry-run
```

Si falla la conexión (`Can't connect to MySQL server on 'localhost'`): arranca MySQL o ejecuta `docker compose up -d mysql` en este repo y usa en `.env` `DB_HOST=127.0.0.1` (puerto 3306 mapeado).

Extractores probados en cadena: **iCal** (cuerpo o `Content-Type`), **JSON-LD** (`Event`), **HTML** (`<time datetime>` + heurística). La capa **Embedder** no se ejecuta aquí; rellenar `Tags_Embedding_*` con otro job si hace falta.

