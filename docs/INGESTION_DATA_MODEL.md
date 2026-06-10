# 🗄️ Módulo de Ingesta — Modelo de datos

**Versión:** 1.0
**Última actualización:** 2026-05-15

---

> 📌 **Docs relacionados (módulo de ingesta)**
> - [Visión general](./INGESTION_OVERVIEW.md)
> - [Modelo de datos del módulo](./INGESTION_DATA_MODEL.md) ← estás aquí
> - [Pipeline detallado](./INGESTION_PIPELINE.md)
> - [Optimización y escala](./INGESTION_OPTIMIZATION.md)
> - [Operaciones y observabilidad](./INGESTION_OPERATIONS.md)
>
> 📌 **Schema SQL unificado**: [`SCHEMA_SQL_FINAL.sql`](../SQL/SCHEMA_SQL_FINAL.sql) (init Docker: `scripts/schema.sql`)  
> 📌 **Modelo documental**: [`DATA_MODEL.md`](./DATA_MODEL.md)

---

## 📋 Tabla de contenidos

1. [Principios del modelo](#principios-del-modelo)
2. [Mapeo: roles del módulo ↔ tablas](#mapeo-roles-del-módulo--tablas)
3. [Tablas existentes reutilizadas](#tablas-existentes-reutilizadas)
4. [Tablas nuevas añadidas](#tablas-nuevas-añadidas)
5. [Modificaciones a tablas existentes](#modificaciones-a-tablas-existentes)
6. [Modelos Pydantic intermedios](#modelos-pydantic-intermedios)
7. [Diagrama ER textual](#diagrama-er-textual)
8. [Reglas de integridad y consistencia](#reglas-de-integridad-y-consistencia)

---

## Principios del modelo

El modelo de datos del módulo de ingesta se rige por cinco principios. Todas las decisiones de diseño en este documento se justifican apelando a uno o varios de ellos.

**1. Captura inmutable.** Lo que se descarga de una fuente externa se conserva tal cual antes de procesarlo. Esto permite re-procesar sin re-scrapear, auditar fallos forenses, y cumplir trazabilidad. La tabla `CAPTURAS_RAW` materializa este principio.

**2. Separación captura / extracción.** El payload bruto y los datos estructurados extraídos viven en tablas distintas. Una captura puede producir cero, uno o varios eventos. Cambiar el extractor no requiere modificar la captura.

**3. Multi-fuente por evento, fuente principal explícita.** Un evento real puede aparecer en varias fuentes. El modelo refleja esto con una tabla N:M (`EVENTO_FUENTES`) en vez de un solo campo. `EVENTOS_MASTER` mantiene una "fuente principal" por compatibilidad con la spec VAC 360, pero el grafo completo de fuentes vive en la relación.

**4. Embeddings versionables.** Los vectores se guardan en una tabla aparte (`EVENTO_EMBEDDINGS`) para no penalizar los queries que no los necesitan y para permitir múltiples versiones por evento sin migraciones.

**5. Auditoría con o sin evento.** No todas las capturas producen eventos. Las que no lo hacen también deben auditarse (para mejorar el sistema, detectar problemas de extracción, medir eficiencia). `AUDITORIA_SCRAPING` admite `ID_Unico_Evento NULL` y categoriza el motivo de skip.

---

## Mapeo: roles del módulo ↔ tablas

El módulo tiene varios roles conceptuales. Esta es la traducción de cada rol a la(s) tabla(s) concreta(s):

| Rol conceptual | Tabla(s) | Notas |
|---|---|---|
| Registro de fuentes externas | `BIBLIOTECA_FUENTES` | Ya existía. Una fila por URL/cuenta externa. |
| Cola de trabajos de scraping | `SCRAPING_TARGETS` | Ya existía. Una fila por trabajo programado contra una fuente. |
| Almacén de capturas crudas | `CAPTURAS_RAW` | **Nueva**. Inmutable, "fuente de verdad". |
| Asociación evento ↔ fuentes | `EVENTO_FUENTES` | **Nueva**. N:M con metadatos por enlace. |
| Trazabilidad y auditoría | `AUDITORIA_SCRAPING` | Ya existía. Modificada para admitir capturas sin evento. |
| Almacén de imágenes propias | `BINARIOS_STORAGE` | Ya existía. Apunta a URLs de storage propio (R2/S3). |
| Caché de extracción de carteles | `PHASH_IMAGENES` | **Nueva**. Evita pagar LLM-Vision dos veces. |
| Vectores semánticos | `EVENTO_EMBEDDINGS` | **Nueva**. Separada de `EVENTOS_MASTER`. |
| Métricas para scheduling adaptativo | `COVERAGE_METRICS` | **Nueva**. Materializada, recalculada diariamente. |
| Tabla final consumida por la API | `EVENTOS_MASTER` + hijas | Ya existía. El módulo es su productor. |

---

## Tablas existentes reutilizadas

Estas tablas forman parte del esquema unificado en [`SCHEMA_SQL_FINAL.sql`](../SQL/SCHEMA_SQL_FINAL.sql). El módulo las usa tal cual o con las extensiones descritas en este documento (ver sección [Modificaciones](#modificaciones-a-tablas-existentes)).

### `BIBLIOTECA_FUENTES`

Una fila por URL/cuenta/endpoint externo que el sistema sabe consultar.

**Campos clave**:
- `Tipo_Fuente` (ENUM): `FUENTE_OFICIAL`, `AGREGADOR`, `RED_SOCIAL_PERFIL`, `RED_SOCIAL_QUERY`. Determina qué conector se aplica.
- `Plataforma` (ENUM): para redes sociales — `INSTAGRAM`, `FACEBOOK`, `X_TWITTER`, `TIKTOK`. Determina qué Actor de Apify usar.
- `Handle`: nombre de cuenta para perfiles sociales.
- `Query_Default`: búsqueda por defecto para fuentes `RED_SOCIAL_QUERY`.
- `Hashtags_JSON`: lista de hashtags asociados.
- `URL_Base`: URL canónica del sitio o cuenta.
- `Activa`: 0/1, soft-disable sin borrar histórico.
- `Prioridad`: orden de procesamiento (menor = más prioritaria).
- `Config_JSON` **(añadido)**: configuración específica del conector.
- `Notas`, `Fecha_Alta`, `Fecha_Modificacion` **(añadidos)**.

**Relaciones**:
- 1:N con `SCRAPING_TARGETS` (una fuente tiene N trabajos asociados).
- 1:N con `CAPTURAS_RAW` (una fuente produce N capturas a lo largo del tiempo).
- 1:N con `EVENTO_FUENTES` (una fuente aporta a N eventos).

**Uso por el módulo**: el scheduler lee las fuentes activas, escoge sus targets vencidos, y dispara conectores. Los conectores consultan `Config_JSON` para parametrizarse.

### `SCRAPING_TARGETS`

Una fila por trabajo programado. Una fuente puede tener varios targets (ej. una web con sitemap + listado + endpoint de detalle).

**Campos clave**:
- `Tipo_Target` (ENUM): **definido en el delta** como `WEB_LISTADO`, `WEB_DETALLE`, `WEB_SITEMAP`, `API_AGREGADOR`, `SOCIAL_PERFIL`, `SOCIAL_QUERY`. Determina qué llamada concreta hace el conector.
- `URL_Target` / `Query_Target`: la URL exacta a llamar o la query a ejecutar.
- `Origen_Tabla`, `Origen_ID`: trazabilidad de cómo se descubrió este target. Permite añadir targets dinámicamente (ej. una entrada en `WEB_LISTADO` puede descubrir N entradas en `WEB_DETALLE`).
- `Estado` (ENUM): `PENDIENTE`, `PROCESANDO`, `OK`, `ERROR`, `PAUSADO`.
- `Frecuencia_Horas`: cada cuánto re-ejecutar este target.
- `Next_Run_At`, `Last_Run_At`: scheduling.
- `Http_ETag`, `Http_LastModified`: para HEAD check (cascade).
- `Content_Fingerprint`: hash del último payload exitoso (para detectar cambios).
- `Last_Changed_At`: marca cuándo cambió el contenido por última vez.
- `Frecuencia_Base_Horas` **(añadido)**: frecuencia configurada manualmente. La efectiva es `Frecuencia_Horas`.
- `Coverage_Score` **(añadido)**: score actual del scheduling adaptativo.
- `Capturas_Utiles_Consecutivas`, `Capturas_Vacias_Consecutivas` **(añadidos)**: para backoff.

**Uso por el módulo**: el scheduler hace `SELECT ... WHERE Estado IN ('PENDIENTE','OK') AND Next_Run_At <= NOW() ORDER BY Prioridad, Next_Run_At LIMIT N`. Cada worker procesa un target a la vez.

### `AUDITORIA_SCRAPING`

Log de cada intento de ingesta. Existe **independientemente de si la captura produjo evento**.

**Campos clave**:
- `ID_Unico_Evento` **(ahora NULL permitido)**: si la captura no produjo evento, NULL.
- `ID_Captura` **(añadido)**: FK a `CAPTURAS_RAW`.
- `URL_Procesada`, `Metodo_Usado`.
- `Resultado` (ENUM): `OK`, `WARNING`, `ERROR`.
- `Motivo_Skip` **(añadido, ENUM)**: si la captura no produjo evento, por qué (`GATE_DUPLICADO`, `FILTRO_TEMPORAL`, `SIN_FECHA_DETECTADA`, `CONTENIDO_NO_EVENTO`, `ERROR_EXTRACCION`, `NA`).
- `Texto_Bruto_Caption`, `Texto_Bruto_OCR`: contenido extraído antes de procesarse.
- `Payload_Extra` (JSON): info ad-hoc por extractor (latencia, tokens, etc.).

### `BINARIOS_STORAGE`

Imágenes y otros binarios asociados a eventos, **descargados a storage propio**. Una fila por imagen.

**Campos clave**:
- `ID_Unico_Evento`: el evento al que pertenece.
- `Nombre_Archivo`, `Tipo_Archivo` (ENUM): `PDF`, `JPG`, `JPEG`, `PNG`, `WEBP`, `DOCX`.
- `URL_Almacenamiento_Nube`: URL en CDN propio (Cloudflare R2 / S3). Esta es la URL que sirve la app.
- `Checksum_SHA256`: integridad y dedup binario.

**Patrón de uso**:
1. Conector descarga la imagen del origen (CDN de FB/IG, web del ayuntamiento, etc.).
2. Calcula SHA256 + pHash.
3. Sube a object storage propio.
4. Inserta fila en `BINARIOS_STORAGE`.
5. Actualiza `EVENTOS_MASTER.Imagen_Principal_URL` con la URL propia (la primera imagen del evento típicamente).
6. Si tiene pHash, registra/actualiza `PHASH_IMAGENES`.

### `EVENTOS_MASTER` y tablas hijas

Documentadas en [`DATA_MODEL.md`](./DATA_MODEL.md). El módulo es su productor exclusivo (excepto eventos `Metodo_Ingesta = 'MANUAL'`).

Campos relevantes para ingesta:
- `Fuente_ID` (ENUM): la categoría de la **fuente principal** del evento. La lista completa de fuentes está en `EVENTO_FUENTES`.
- `Fuente_URL_Original`: URL canónica de la fuente principal. Otras URLs en `EVENTO_FUENTES`.
- `Estado`: `ACTIVO`, `CANCELADO`, `APLAZADO`. El módulo solo inserta `ACTIVO`. Cambios a `CANCELADO`/`APLAZADO` los hace un proceso separado al detectar inconsistencias entre fuentes.

---

## Tablas nuevas añadidas

Definidas en [`SCHEMA_SQL_FINAL.sql`](../SQL/SCHEMA_SQL_FINAL.sql). Aquí va la racional de cada una.

### `CAPTURAS_RAW`

**Por qué existe**: principio 1 (captura inmutable) + principio 2 (separación captura/extracción).

**Modelo de uso**:

1. Conector ejecuta. Captura payload (HTML, JSON, lote de posts).
2. Inserta una fila en `CAPTURAS_RAW` con `Status = 'PENDIENTE_EXTRACCION'`.
3. Si el payload es pequeño (< 1 MB), va en `Payload_Bytes`. Si es grande, se sube a object storage y se guarda solo `Payload_Storage_URL`.
4. Extractor toma capturas pendientes, las procesa, actualiza `Status` a `EXTRAIDA` o `ERROR_EXTRACCION`, registra `Coste_Estimado_USD`.
5. Si `Status = 'EXTRAIDA'`, los `EventCandidate` generados se enganchan a esta captura vía `EVENTO_FUENTES.ID_Captura`.

**Caso especial — captura sin cambio**: si el conector detecta vía HEAD/sitemap que el contenido no ha cambiado, **no** crea fila en `CAPTURAS_RAW`. Solo actualiza `SCRAPING_TARGETS.Last_Run_At`. Esto evita inflar la tabla con duplicados.

**Caso especial — captura idéntica a una anterior** (mismo `Content_Hash_SHA256`): se crea la fila con `Status = 'SKIPPED_SIN_CAMBIOS'` y se referencia la captura previa para reutilizar su extracción. Esto sí queda en `CAPTURAS_RAW` porque a veces el contenido vuelve a ser el mismo tras haber cambiado (rollback de la web), y es relevante saberlo.

### `EVENTO_FUENTES`

**Por qué existe**: principio 3 (multi-fuente).

**Modelo de uso**:

- Al persistir un evento nuevo, se inserta una fila con `Es_Fuente_Principal = 1` y `Aporto_Extraccion = 1`.
- Cuando el merge detecta que una captura confirma un evento existente, se inserta una fila con `Es_Fuente_Principal = 0` y `Aporto_Extraccion = 1` (o 0 si el Gate evitó la extracción).
- Unicidad: `(ID_Unico_Evento, URL_Origen)` — no se permite la misma URL apuntando dos veces al mismo evento.
- `Score_Calidad` se llena al persistir y se usa en futuros merges para decidir prioridad de campo.

**Patrón típico de un evento popular**:

```
ID_Unico_Evento: abc123
  EVENTO_FUENTES:
    (1) URL=https://malgrat.cat/agenda/concert-festes-2026  Es_Principal=1  Aporto_Extraccion=1  Score=0.95
    (2) URL=https://api.diputaciobcn.cat/event/12345         Es_Principal=0  Aporto_Extraccion=1  Score=0.80
    (3) URL=https://instagram.com/p/CxX_abc/                Es_Principal=0  Aporto_Extraccion=0  Score=0.60  <- Gate ahorró LLM
    (4) URL=https://facebook.com/ajmalgrat/posts/789        Es_Principal=0  Aporto_Extraccion=0  Score=0.60  <- Gate ahorró LLM
```

### `EVENTO_EMBEDDINGS`

**Por qué existe**: principio 4 (embeddings versionables).

**Modelo de uso**:

- Job async tras persistir un evento. Concatena tags (o tags + título + descripción según política) y llama al modelo de embeddings.
- Una fila por (evento, idioma, modelo). Permite tener simultáneamente `text-embedding-3-small` y un modelo posterior, p.ej., durante una migración.
- Para queries de búsqueda semántica, la API consulta la fila con el modelo "vigente" (configurable). Los antiguos se mantienen mientras dure la migración.
- `Texto_Fuente_Hash`: si los tags del evento cambian, se compara el hash para decidir si regenerar el embedding.

**Migración a columnas VECTOR (futuro)**: MySQL 9+ tiene tipo `VECTOR` con índices ANN. Cuando el proyecto migre a esa versión, esta tabla se transforma de `Vector_JSON` a `Vector_Embedding VECTOR(1536)` sin cambiar el modelo conceptual.

### `PHASH_IMAGENES`

**Por qué existe**: optimización clave para escala. Evita pagar LLM-Vision varias veces por el mismo cartel (típico de eventos provinciales).

**Modelo de uso**:

1. Al capturar una imagen de un post social, se calcula pHash (16 bytes, hex 32 chars).
2. `SELECT * FROM PHASH_IMAGENES WHERE Phash_Hex = ?`.
3. Si existe: se incrementa `Veces_Reutilizado`, se actualiza `Fecha_Ultimo_Hit`, y se usa `Extraccion_JSON` directamente sin llamar LLM. La nueva captura/evento queda asociado mediante `EVENTO_FUENTES` con `Aporto_Extraccion = 0`.
4. Si no existe: se llama LLM-Vision, se inserta fila nueva con `Extraccion_JSON = resultado`.

**Tolerancia de pHash**: el algoritmo (típicamente `imagehash.phash` de Python) es robusto a recompresión, recorte ligero y resize. Un cartel publicado en JPEG calidad 80 y republicado en PNG con marca de agua del organizador puede tener pHash idéntico. Si no es idéntico pero la **distancia de Hamming es <= 5**, se considera match y se reutiliza.

**No es perfecto**: imágenes muy modificadas (texto sobrepuesto cambiando fecha) **no** matchean. Eso es deseable — si el cartel cambió, hay que re-extraer.

### `COVERAGE_METRICS`

**Por qué existe**: alimentar el scheduling adaptativo. Sin estos números, la decisión "¿bajo la frecuencia de Apify para este municipio porque ya tengo cobertura?" no se puede tomar automáticamente.

**Modelo de uso**:

- Job batch nocturno que agrega los últimos 30 días por `(ID_Ciudad, Tipo_Fuente)`.
- Calcula `Score_Eficiencia = Aportados / (Aportados + Capturas_Sin_Evento)`. Score bajo → la fuente está aportando poco respecto a lo que cuesta scrapearla.
- `Frecuencia_Sugerida_Horas` = función de `Score_Eficiencia` + `Eventos_Aportados_30d`. Ver fórmula en [`INGESTION_OPTIMIZATION.md`](./INGESTION_OPTIMIZATION.md).
- El scheduler aplica `Frecuencia_Sugerida_Horas` al actualizar `Next_Run_At` de los targets correspondientes.

---

## Modificaciones a tablas existentes

Detalle en [`SCHEMA_SQL_FINAL.sql`](../SQL/SCHEMA_SQL_FINAL.sql). Resumen:

**`SCRAPING_TARGETS`**:
- Concretar `Tipo_Target` (estaba como placeholder en el SQL original).
- Añadir `Frecuencia_Base_Horas`, `Coverage_Score`, `Capturas_Utiles_Consecutivas`, `Capturas_Vacias_Consecutivas`.

**`AUDITORIA_SCRAPING`**:
- Permitir `ID_Unico_Evento` NULL.
- Añadir `ID_Captura` (FK a `CAPTURAS_RAW`).
- Añadir `Motivo_Skip` (ENUM).

**`BIBLIOTECA_FUENTES`**:
- Añadir `Config_JSON`, `Notas`, `Fecha_Alta`, `Fecha_Modificacion`.

---

## Modelos Pydantic intermedios

Los modelos Python que circulan entre capas del módulo. **No tienen tablas asociadas** directamente — son objetos en memoria que se transforman en filas de BD al persistir.

### `RawCapture`

Representa una captura cruda recién hecha por un conector, antes de extracción.

```python
class RawCapture(BaseModel):
    id_captura: Optional[int] = None  # asignado tras INSERT
    id_target: int
    id_fuente: int
    fecha_captura: datetime
    content_type: str
    content_hash_sha256: str
    payload_bytes: Optional[bytes] = None
    payload_storage_url: Optional[str] = None
    payload_size_bytes: int

    class Config:
        # bytes <-> base64 al serializar para colas
        json_encoders = {bytes: lambda b: base64.b64encode(b).decode()}
```

**Invariante**: exactamente uno de `payload_bytes` o `payload_storage_url` no nulo.

### `EventCandidate`

Lo que produce un extractor. Es la "intención" de un evento, antes de pasar por gate y merge.

```python
class EventCandidate(BaseModel):
    # Trazabilidad
    id_captura: int
    id_fuente: int
    extractor_usado: str  # 'structural_html', 'mapping_eventbrite', 'llm_text', 'llm_vision'
    url_origen: str       # URL específica del item
    score_calidad: float  # 0..1, asignado por el extractor según completitud y confianza

    # Geografía
    id_ciudad: int
    cp_evento: Optional[str] = None
    lugar_nombre: Optional[str] = None
    direccion_fisica: Optional[str] = None
    coordenadas: Optional[dict] = None  # {"lat": ..., "lng": ...}

    # Identidad del evento
    titulo_es: Optional[str] = None
    titulo_cat: Optional[str] = None
    idioma_origen: str  # 'es' o 'ca'
    desc_larga_es: Optional[str] = None
    desc_larga_cat: Optional[str] = None

    # Temporal
    fecha_inicio: date
    fecha_fin: Optional[date] = None
    hora_inicio: Optional[time] = None
    hora_fin: Optional[time] = None
    es_recurrente: bool = False
    recurrencia: Optional[dict] = None

    # Económico y operativo
    es_gratuito: Optional[bool] = None
    precio_euros: Optional[Decimal] = None
    requiere_inscripcion: Optional[bool] = None
    aforo_maximo: Optional[int] = None
    link_entradas_inscripcion: Optional[str] = None

    # Organización
    tipo_organizador: Optional[str] = None  # PUBLICO, PRIVADO, ASOCIACION
    organizador_nombre: Optional[str] = None
    organizador_web: Optional[str] = None

    # Multimedia
    imagen_url_original: Optional[str] = None  # URL en origen, antes de descargar a storage propio
    imagen_phash: Optional[str] = None         # asignado tras descargar y procesar

    # Tags (sin embeddings aún)
    tags_ia: list[str] = []

    # Categorías sugeridas (la categoría definitiva se asigna en merge)
    categorias_sugeridas: list[str] = []  # códigos de CATEGORIAS.Codigo
```

**Notas**:
- Casi todos los campos son `Optional` porque cada extractor llena un subconjunto. El merge se encarga de combinar.
- `fecha_inicio` es obligatoria: un candidato sin fecha se descarta antes de crear el `EventCandidate` (Motivo_Skip = SIN_FECHA_DETECTADA).
- `score_calidad` lo asigna el extractor según heurísticas: parser estructural típicamente 0.85-0.95, mapping de agregador 0.70-0.85, LLM-text 0.55-0.75, LLM-vision 0.60-0.80.

### `MergedEvent`

Resultado del paso de merge: candidato consolidado, listo para insertar en `EVENTOS_MASTER`.

```python
class MergedEvent(BaseModel):
    # Identidad
    id_unico_evento: str  # generado en el merge: hash(id_ciudad + titulo_normalizado + fecha_inicio)
    es_evento_nuevo: bool  # True si no existía; False si actualiza uno existente

    # Todos los campos de EVENTO_MASTER (no Optional aquí — el merge ya rellenó)
    metodo_ingesta: str = 'SCRAPING'
    id_usuario_carga: str = 'SYSTEM'
    fuente_id: str  # 'URL_ESTRUCTURAL', 'SOCIAL_VISUAL', 'SOCIAL_SEMANTICA'
    fuente_url_original: str
    estado: str = 'ACTIVO'

    id_ciudad: int
    cp_evento: Optional[str]
    lugar_nombre: str
    # ... (resto de campos como EventCandidate pero ya consolidados)

    # Lista de fuentes a registrar en EVENTO_FUENTES
    fuentes: list['EventFuenteRecord']

    # Lista de horarios a registrar en EVENTO_HORARIOS
    horarios: list['HorarioRecord']

    # Lista de imágenes a descargar y registrar en BINARIOS_STORAGE
    imagenes: list['ImagenRecord']

    # Categorías a asignar
    categorias: list['CategoriaAsignacion']


class EventFuenteRecord(BaseModel):
    id_fuente: int
    id_captura: Optional[int]
    url_origen: str
    es_fuente_principal: bool
    aporto_extraccion: bool
    score_calidad: float


class HorarioRecord(BaseModel):
    fecha_inicio: date
    fecha_fin: Optional[date]
    hora_inicio: Optional[time]
    hora_fin: Optional[time]
    es_recurrente: bool
    recurrencia: Optional[dict]
    horario_texto_es: Optional[str]


class ImagenRecord(BaseModel):
    url_original: str
    phash: Optional[str]
    tipo_archivo: str
    es_principal: bool


class CategoriaAsignacion(BaseModel):
    codigo: str  # CATEGORIAS.Codigo
    score: float
    es_principal: bool
```

### `GateDecision`

Resultado del Gate pre-LLM. Indica qué hacer con un post antes de extraer.

```python
class GateDecision(BaseModel):
    decision: Literal['EXTRAER', 'REGISTRAR_FUENTE', 'DESCARTAR']
    id_unico_evento_match: Optional[str] = None  # solo si decision == 'REGISTRAR_FUENTE'
    score_match: Optional[float] = None
    metodo_match: Optional[Literal['FINGERPRINT', 'SEMANTIC']] = None
    razon: str  # descriptivo, para auditoría
```

---

## Diagrama ER textual

Las relaciones que importan al módulo de ingesta. `→` indica FK desde la tabla origen hacia la destino. `↔` indica relación N:M.

```
CIUDADES
  ↑ id_ciudad
  │
  ├── BIBLIOTECA_FUENTES (id_ciudad → ciudades.id_ciudad)
  │     ↑ id_fuente
  │     │
  │     ├── SCRAPING_TARGETS (id_fuente → biblioteca_fuentes.id_fuente)
  │     │     ↑ id_target
  │     │     │
  │     │     └── CAPTURAS_RAW (id_target → scraping_targets.id_target,
  │     │           ↑ id_captura  id_fuente → biblioteca_fuentes.id_fuente)
  │     │           │
  │     │           ├── AUDITORIA_SCRAPING (id_captura → capturas_raw.id_captura)
  │     │           └── EVENTO_FUENTES (id_captura → capturas_raw.id_captura)
  │     │
  │     └── EVENTO_FUENTES (id_fuente → biblioteca_fuentes.id_fuente)
  │
  ├── EVENTOS_MASTER (id_ciudad → ciudades.id_ciudad)
  │     ↑ id_unico_evento
  │     │
  │     ├── EVENTO_HORARIOS (id_unico_evento → eventos_master.id_unico_evento)
  │     ├── EVENTO_CATEGORIAS (id_unico_evento → eventos_master.id_unico_evento)
  │     ├── BINARIOS_STORAGE (id_unico_evento → eventos_master.id_unico_evento)
  │     │     ↑ id_binario
  │     │     │
  │     │     └── PHASH_IMAGENES (id_binario → binarios_storage.id_binario)
  │     │
  │     ├── AUDITORIA_SCRAPING (id_unico_evento → eventos_master.id_unico_evento, NULLABLE)
  │     ├── EVENTO_FUENTES (id_unico_evento → eventos_master.id_unico_evento)
  │     └── EVENTO_EMBEDDINGS (id_unico_evento → eventos_master.id_unico_evento)
  │
  └── COVERAGE_METRICS (id_ciudad → ciudades.id_ciudad)
        PK compuesta: (id_ciudad, tipo_fuente)
```

---

## Reglas de integridad y consistencia

Reglas que deben mantenerse a nivel aplicación (algunas no se pueden expresar como constraints SQL).

### Sobre `EVENTO_FUENTES`

**R1**: para cada `id_unico_evento`, existe **exactamente una** fila con `Es_Fuente_Principal = 1`. La fuente principal es la cuya extracción se usó como base del registro en `EVENTOS_MASTER`. Si cambia (porque una fuente con mayor `score_calidad` aparece después), se actualiza con una transacción que cambia el `Es_Fuente_Principal` de la antigua a 0 y de la nueva a 1.

**R2**: `EVENTOS_MASTER.Fuente_URL_Original` debe coincidir con la `URL_Origen` de la fila con `Es_Fuente_Principal = 1` en `EVENTO_FUENTES`. Lo mantiene la lógica de merge.

**R3**: una fila con `Aporto_Extraccion = 0` solo puede existir si hay al menos una fila con `Aporto_Extraccion = 1` para el mismo evento. (No puede haber un evento "todo confirmado, nada extraído"; siempre hubo una primera extracción.)

### Sobre `CAPTURAS_RAW`

**R4**: `Status = 'EXTRAIDA'` implica que el extractor ya corrió y `Extraccion_Ended_At` no es NULL. Si `Status = 'EXTRAIDA'` pero `Extraccion_Ended_At IS NULL`, hay un bug.

**R5**: una captura con `Status = 'SKIPPED_SIN_CAMBIOS'` referencia (vía búsqueda por `Content_Hash_SHA256`) una captura previa con el mismo hash. No es necesario mantener una FK explícita pero el código debe poder reconstruir la cadena.

### Sobre embeddings

**R6**: para cada evento `ACTIVO` debe existir al menos un embedding en el modelo "vigente" (configurable). Si no existe, la búsqueda semántica falla silenciosamente sobre ese evento. Un job de reconciliación nocturno regenera embeddings faltantes.

**R7**: si `EVENTOS_MASTER.Tags_IA_Array` cambia, los embeddings asociados deben regenerarse. Esto se detecta comparando `EVENTO_EMBEDDINGS.Texto_Fuente_Hash` con el hash actual de los tags.

### Sobre `BINARIOS_STORAGE`

**R8**: cuando se elimina un evento (caso raro, normalmente solo se marca `CANCELADO`), los binarios asociados deben moverse a un bucket "archive" en object storage durante 90 días antes de borrarse físicamente. Esto da margen para recuperación.

**R9**: `EVENTOS_MASTER.Imagen_Principal_URL` debe apuntar a una URL en el dominio del CDN propio, no a CDNs de terceros (FB, IG). Lo enforça la lógica de persistencia.

### Sobre auditoría

**R10**: toda ejecución de un `SCRAPING_TARGET` produce **al menos una** fila en `AUDITORIA_SCRAPING`, independientemente del resultado. Incluso una ejecución con `SKIPPED_SIN_CAMBIOS` produce auditoría (con `Resultado = 'OK'` y `Detalle = 'no changes'`).

**R11**: si `AUDITORIA_SCRAPING.Resultado = 'ERROR'`, el campo `Detalle` debe contener al menos: tipo de excepción, mensaje, primeros 200 caracteres del traceback. Esto es lo mínimo para debug.

---

## Apéndice (junio 2026): noticias y fuentes multi-contenido (fase 1 implementada)

Cambios de schema implementados con la fase 1 del pipeline multi-fuente
(deltas: `SQL/noticias_delta.sql` y `SQL/fuentes_delta.sql`):

### NOTICIAS_MASTER + NOTICIA_BINARIOS

Contenido informativo municipal (comunicados, avisos, noticias) separado de
`EVENTOS_MASTER`: una noticia no tiene horarios ni recinto y su ciclo de vida
es por antigüedad, no por fecha de celebración.

- `ID_Unico_Noticia` CHAR(64): sha256 de `noticia|poblacion|titulo_norm`
  (mismo patrón determinista que los eventos).
- Bilingüe: `Titulo_CAT/ES`, `Cuerpo_CAT/ES`, `Tags_CAT/ES` (JSON).
- Vigencia: `Fecha_Caducidad = Fecha_Publicacion + NEWS_TTL_DIAS` (45 por
  defecto). Al caducar: `Estado='ARCHIVADA'` + borrado de binarios; borrado
  definitivo a los 90 días.
- `NOTICIA_BINARIOS`: espejo de BINARIOS_STORAGE con FK a NOTICIAS_MASTER
  ON DELETE CASCADE (BINARIOS_STORAGE tiene FK a EVENTOS_MASTER).
- Dedupe cross-fuente: título similar en la misma ciudad con fecha de
  publicación a ±7 días (la misma noticia en el ayuntamiento y la radio local).

### BIBLIOTECA_FUENTES.Tipo_Contenido

`ENUM('EVENTOS','NOTICIAS','MIXTO')`, hint para el clasificador del pipeline:

- `EVENTOS` → ruta de extracción clásica directa (sin clasificador, coste 0 extra).
- `NOTICIAS`/`MIXTO` → clasificación LLM por item (EVENTO/NOTICIA/DESCARTAR).

Es un sesgo, no determinante: el LLM decide por contenido.

### ENUM Plataforma ampliado

`+ 'YOUTUBE','TELEGRAM'` en BIBLIOTECA_FUENTES y SCRAPING_TARGETS. Telegram se
modela como `Tipo_Fuente='RED_SOCIAL_PERFIL'` + `Plataforma='TELEGRAM'` con
target `SOCIAL_PERFIL`; su conector (scraping de `t.me/s/{handle}`) está
implementado en fase 1. IG/FB/X/YouTube quedan registradas con `Activa=0`
hasta el conector Apify (fase 2).

### Uso real de SCRAPING_TARGETS (fase 1)

El pipeline usa: `Http_ETag`/`Http_LastModified` (GET condicional),
`Content_Fingerprint` (sha256 del HTML limpio; en Telegram, del id del último
mensaje), `Last_Changed_At`, `Last_Run_At`/`Next_Run_At` (+Frecuencia_Horas),
`Estado` (OK/ERROR/PAUSADO; WEB_DETALLE se auto-pausa tras 3 capturas vacías),
`Intentos`/`Last_Error` y los contadores de capturas. `Coverage_Score` y el
scheduling adaptativo siguen pendientes (fase 2). `AUDITORIA_SCRAPING` y
`CAPTURAS_RAW` siguen siendo diseño no implementado.
