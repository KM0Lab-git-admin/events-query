# El Viajero Animalista — Diseño del módulo sobre events-query

**Fecha:** 12-10-2026 · **Repo:** `events-query` · **Estado:** propuesta para validar antes de implementar

> Módulo independiente de noticias y eventos del mundo animalista en España,
> construido reutilizando el pipeline de ingesta de KM0 LAB. Este documento
> recoge el análisis de lo que existe, las decisiones cerradas con el
> product owner, la arquitectura propuesta, el modelo de datos, la taxonomía,
> el enriquecimiento con IA, la estrategia de fuentes, la interfaz de
> operaciones y el plan por fases.

---

## 0. Decisiones cerradas (12-10-2026)

| Tema | Decisión |
| --- | --- |
| Arquitectura | **Opción A**: mismo repo, código compartido extraído del pipeline actual, base de datos separada |
| Idioma | Solo **castellano** en el MVP. Esquema preparado para añadir idiomas |
| Vigencia | Noticias **caducan a 10 días y se borran** físicamente, igual que en KM0. Eventos pasados se purgan |
| Geografía | **Comunidad autónoma y provincia**. Municipio se guarda si se detecta. Coordenadas y mapa en fase posterior |
| Animales | **Perros y gatos** prioritarios; el resto agrupado (propuesta en §3.3) |
| Fuentes | Gestionadas **a mano** por nosotros. Descubrimiento con RSS y Google News, **sin proveedores de pago** |
| Legal | Respetar `robots.txt` y `Crawl-delay` |
| Ejecución | **Bajo demanda**, sin cron. El coste por run no es limitante |
| Relevancia | **Mismo criterio que KM0**: el clasificador decide, sin validación manual previa |
| Acceso | Sin login. La UI de ops de events-query, nada público |
| Tipos en MVP | **Noticias y eventos**. El modelo contempla los otros tipos para fase 2 |
| Nombres | Paquete `app/animalista/`, base de datos `animalista_db` |
| Validación previa | Antes de implementar, mockup con datos reales en `docs/animalista-mockup/` (XML de 50 contenidos + prompt para Lovable) para que el amigo valide el paradigma |

---

## 1. Lo que existe y qué se reutiliza

### 1.1. El pipeline real

El pipeline de producción es `scripts/ingest_all.py` (~5.300 líneas, un solo
proceso síncrono, pymysql, OpenAI chat con JSON Schema estricto). El módulo
`app/ingestion/` que describe la documentación es un esqueleto sin LLM que no
se usa. Las tablas `CAPTURAS_RAW`, `AUDITORIA_SCRAPING` y `COVERAGE_METRICS`
se eliminaron del esquema (`SQL/migrate_drop_aux_tables.sql`).

### 1.2. Piezas reutilizables (se extraen a un paquete común)

| Pieza | Dónde está hoy | Qué hace |
| --- | --- | --- |
| Cliente HTTP + fingerprint | `make_http_client`, `fetch_si_cambiado`, `content_fingerprint` | GET condicional ETag/Last-Modified, hash del HTML limpio, skip si no cambió |
| Limpieza y paginación | `clean_html`, `html_a_texto_enlaces`, `recolectar_paginas_listado` | Reduce tokens; sigue `?pag=N` |
| Extractor JSON-LD | `extract_listing_jsonld` | Eventos `schema.org/Event` sin LLM |
| Wrapper LLM | `llm_json`, `llm_json_vision` | Chat con `response_format=json_schema`, temperatura 0, coste contabilizado |
| Contabilidad de coste | `CostTracker`, `INGESTA_RUNS`, `INGESTA_COSTES` | Tokens reales por run, ámbito y operación |
| PDF | `pdf_bytes_a_texto`, `pdf_bytes_a_imagenes` | Texto y visión por páginas |
| Telegram | `telegram_fetch_mensajes` | Canal público `t.me/s/handle` |
| Imágenes | `image_store`, `IMAGENES_BLOB`, `generar_imagen_ia_evento` | Descarga, orientación, blob durable, portada IA |
| Lock y run | `adquirir_lock`, `ingest_run.py` | Evita solapes, endpoint protegido para lanzar |
| Fuentes en BD | `BIBLIOTECA_FUENTES`, `SCRAPING_TARGETS`, `import_fuentes.py` | Registro, estado, auto-pausa, semillas JSON |
| Dedupe semántico | `dedupe_events.py` | Embeddings + juez LLM (se reimplementa sin borrado físico) |

### 1.3. Acoplamientos que obligan a separar datos y prompts

- Todo gira sobre población y CP: `CP_Evento NOT NULL` con FK, `ID_Ciudad NOT NULL` en fuentes y noticias, targets cargados por ciudad, costes por población.
- Bilingüe CA/ES cableado en columnas, prompts y esquemas.
- Catálogo de categorías cerrado en código (`CATEGORIES_FLAT`) y en BD, incrustado como `enum` en el esquema del LLM.
- Solo dos tipos de contenido (evento, noticia).
- Sin modelo de provincia ni comunidad autónoma (`CIUDADES.Provincia` es texto libre y el persister escribe `""`).

Conclusión: se comparte **código**, no **tablas ni prompts**.

---

## 2. Arquitectura propuesta

```
events-query (repo)
├── app/
│   ├── ingest_core/            ← NUEVO: paquete común extraído de ingest_all.py
│   │   ├── http.py             (cliente, fingerprint, GET condicional, robots)
│   │   ├── html.py             (clean, texto+enlaces, paginación, og:image)
│   │   ├── jsonld.py
│   │   ├── llm.py              (llm_json, llm_json_vision)
│   │   ├── costs.py            (CostTracker + persistencia de runs)
│   │   ├── pdf.py
│   │   ├── telegram.py
│   │   ├── images.py
│   │   └── lock.py
│   ├── animalista/             ← NUEVO: dominio El Viajero Animalista
│   │   ├── schemas.py          (JSON Schemas del LLM)
│   │   ├── prompts.py
│   │   ├── taxonomia.py        (tipos, temas, animales)
│   │   ├── geo.py              (resolución contra maestro INE)
│   │   ├── pipeline.py         (fuentes → clasificación → detalle → enriquecimiento → dedupe → persistencia)
│   │   ├── persister.py
│   │   └── db.py               (conexión a animalista_db)
│   └── api/v1/animalista/      ← NUEVO: router /api/v1/animalista/*
├── scripts/
│   ├── ingest_all.py           (KM0, pasa a importar ingest_core; comportamiento intacto)
│   ├── ingest_animalista.py    ← NUEVO: CLI bajo demanda
│   ├── import_fuentes_animalista.py
│   └── fuentes_animalista/     (semillas JSON por tipo de fuente)
├── SQL/animalista/
│   ├── schema.sql
│   ├── seed_geo.sql            (CCAA + provincias; municipios desde fichero INE)
│   └── seed_taxonomia.sql
└── frontend/src/animalista/    ← NUEVO: pestaña con sub-vistas
```

**Bases de datos.** `events_db` (KM0) y `animalista_db` conviven en el mismo
MySQL local (docker compose) y, cuando toque, en el mismo proyecto Railway
como segundo servicio MySQL. La API abre un segundo pool solo si existe
`ANIMALISTA_DB_*` en el entorno; si no, el router animalista responde 503 y
KM0 no se ve afectado.

**Ejecución.** `python scripts/ingest_animalista.py --target local` desde
el PC, o `POST /api/v1/animalista/ingest/run` desde la pestaña de ops (mismo
mecanismo de lock y secret que KM0). Sin cron.

**Regla de no regresión.** La extracción de `ingest_core` no cambia el
comportamiento de KM0. Verificación: `ingest_all.py --poblacion "Malgrat de
Mar" --refresh --dry-run` antes y después debe dar los mismos candidatos y
el mismo coste estimado.

---

## 3. Modelo de datos (`animalista_db`)

### 3.1. Principios

1. **Una tabla de contenidos** con `Tipo_Contenido`, no una tabla por tipo. Los filtros de la web final son transversales y cuatro de los seis tipos no tienen fecha.
2. **Cinco dimensiones independientes**: tipo de contenido, tema, animal, geografía y tags libres. Nunca se mezclan en la misma lista.
3. **Procedencia por atributo**: cada campo relevante sabe si fue extraído, inferido o generado.
4. **Multi-fuente**: la misma noticia en tres medios es un contenido con tres fuentes.
5. **Ciclo de vida por tipo**: noticias 10 días, eventos hasta su fecha, resto sin caducidad automática.

### 3.2. Tablas

**Maestros geográficos** (semilla, no los toca la ingesta)

```
GEO_CCAA         (Codigo_INE CHAR(2) PK, Nombre)                   -- 17 + Ceuta y Melilla
GEO_PROVINCIAS   (Codigo_INE CHAR(2) PK, Nombre, Codigo_CCAA FK)   -- 52
GEO_MUNICIPIOS   (Codigo_INE CHAR(5) PK, Nombre, Nombre_Norm, Codigo_Provincia FK,
                  Poblacion INT NULL, Lat NULL, Lng NULL)          -- ~8.100 desde el fichero INE
```

**Taxonomía** (semilla, editable)

```
CAT_TEMAS        (Slug PK, Nombre, Descripcion, Orden, Activo)
CAT_ANIMALES     (Slug PK, Nombre, Grupo, Orden, Activo)
```

**Fuentes** (mismo patrón que KM0, sin `ID_Ciudad`)

```
FUENTES          (ID_Fuente PK, Nombre, Tipo_Fuente ENUM(OFICIAL, MEDIO, PORTAL, ASOCIACION,
                  AGREGADOR, RED_SOCIAL, FEED_CONSULTA), Tipo_Contenido ENUM(NOTICIAS, EVENTOS, MIXTO),
                  URL_Base, Plataforma NULL, Handle NULL, Ambito_Default ENUM(NACIONAL, CCAA, PROVINCIA,
                  MUNICIPIO) NULL, Codigo_Geo_Default NULL, Imagenes_Permitidas TINYINT DEFAULT 0,
                  Activa, Prioridad, Config_JSON, Notas, Fecha_Alta, Fecha_Modificacion)
TARGETS          (= SCRAPING_TARGETS de KM0: URL_Target, Tipo_Target, Estado, ETag, LastModified,
                  Content_Fingerprint, Last_Run_At, contadores, Last_Error)
```

`Ambito_Default` y `Codigo_Geo_Default` son el sesgo geográfico de la fuente
(una web de un ayuntamiento ya dice el municipio). `Imagenes_Permitidas`
decide si se descargan fotos de esa fuente (ver §5.6).

**Contenidos**

```
CONTENIDOS
  ID_Contenido CHAR(64) PK          -- sha256(tipo|titulo_norm|fecha_clave)
  Tipo_Contenido ENUM(NOTICIA, EVENTO, INICIATIVA, ALOJAMIENTO, PROMOCION, RECURSO)
  Estado ENUM(ACTIVO, PASADO, RETIRADO)
  Titulo VARCHAR(255)
  Resumen VARCHAR(1200)             -- generado, 3 frases máx. Nunca el artículo entero
  Idioma_Origen CHAR(2)
  Fecha_Publicacion DATE            -- noticias
  Fecha_Caducidad DATE NULL         -- noticias: publicación + 10
  Fecha_Inicio DATE NULL            -- eventos
  Fecha_Fin DATE NULL
  Hora_Inicio TIME NULL
  Lugar_Nombre VARCHAR(255) NULL
  Direccion VARCHAR(255) NULL
  Es_Gratuito TINYINT NULL
  Precio_Euros DECIMAL NULL
  Requiere_Inscripcion TINYINT NULL
  URL_Inscripcion VARCHAR(2048) NULL
  Entidad_Nombre VARCHAR(255) NULL  -- organizador, autor institucional, protectora...
  Entidad_Tipo ENUM(PUBLICA, ASOCIACION, EMPRESA, MEDIO, PARTICULAR) NULL
  Ambito ENUM(NACIONAL, CCAA, PROVINCIA, MUNICIPIO, MULTI)
  Tema_Principal FK CAT_TEMAS
  Relevancia DECIMAL(3,2)           -- 0..1 del clasificador
  Tags JSON                         -- 5-10 tags genéricos en castellano
  Embedding JSON NULL               -- text-embedding-3-small de "título + resumen"
  Imagen_Principal_URL VARCHAR(2048) NULL
  Procedencia JSON                  -- {"fecha_inicio":"extraido","ambito":"inferido","resumen":"generado",...}
  Fuente_Principal_ID FK FUENTES
  Fuente_URL_Original VARCHAR(2048)
  Fecha_Creacion, Fecha_Actualizacion

CONTENIDO_GEO        (ID_Contenido, Nivel ENUM(CCAA, PROVINCIA, MUNICIPIO), Codigo_INE, Es_Principal)
CONTENIDO_ANIMALES   (ID_Contenido, Slug_Animal, Es_Principal)
CONTENIDO_TEMAS      (ID_Contenido, Slug_Tema, Score)
CONTENIDO_FUENTES    (ID_Contenido, ID_Fuente, URL_Origen, Es_Principal, Aporto_Extraccion, Score)
CONTENIDO_BINARIOS   (= NOTICIA_BINARIOS de KM0, FK ON DELETE CASCADE)
IMAGENES_BLOB        (igual que KM0)
INGESTA_RUNS / INGESTA_COSTES  (igual que KM0; la columna Poblacion guarda el nombre de la fuente)
INGESTA_DESCARTES    (ID_Run, ID_Fuente, Motivo ENUM(NO_RELEVANTE, SIN_FECHA, CADUCADO, DUPLICADO,
                      ERROR_EXTRACCION, ROBOTS), Cantidad, Muestra_JSON)
```

`INGESTA_DESCARTES` es la pieza que el plan de septiembre pedía para KM0 y
nunca llegó: responde a "¿por qué no salió este contenido?" sin releer logs.

### 3.3. Taxonomía propuesta

**Tipo de contenido** (qué es): `NOTICIA`, `EVENTO`, `INICIATIVA`,
`ALOJAMIENTO`, `PROMOCION`, `RECURSO`. En el MVP solo se ingieren los dos
primeros. `INICIATIVA` es una noticia con entidad pública como protagonista;
se distingue porque la web final querrá listarlas aparte.

**Tema** (de qué trata). Se elimina de la lista original todo lo que era
tipo de contenido:

| Slug | Nombre | Cubre |
| --- | --- | --- |
| `adopcion-proteccion` | Adopción y protección | Adopciones, acogidas, abandono, rescates, protectoras |
| `bienestar-salud` | Bienestar y salud | Veterinaria, nutrición, comportamiento, cuidados |
| `legislacion` | Legislación y normativa | Leyes, ordenanzas, multas, sanciones, trámites |
| `turismo-viajes` | Turismo y viajes | Viajar con animales, destinos, transporte, alojamientos |
| `espacios-convivencia` | Espacios y convivencia | Playas, parques, zonas caninas, acceso a locales, transporte urbano |
| `ocio-deporte` | Ocio y deporte | Agility, canicross, paseos, exposiciones, concursos |
| `educacion-divulgacion` | Educación y divulgación | Charlas, talleres, campañas de sensibilización |
| `fauna-conservacion` | Fauna y conservación | Fauna silvestre, especies protegidas, centros de recuperación |
| `sociedad-tendencias` | Sociedad y tendencias | Datos, estudios, consumo, curiosidades |

Uno a tres temas por contenido, con uno principal.

**Animales**. Dos prioritarios y cuatro grupos:

| Slug | Nombre | Grupo |
| --- | --- | --- |
| `perros` | Perros | prioritario |
| `gatos` | Gatos | prioritario |
| `pequenos-mamiferos` | Conejos y pequeños mamíferos | otros domésticos |
| `aves` | Aves | otros domésticos |
| `exoticos` | Exóticos y reptiles | otros domésticos |
| `caballos` | Caballos y équidos | otros |
| `granja` | Animales de granja | otros |
| `fauna-silvestre` | Fauna silvestre | otros |
| `general` | Animales en general | transversal |

Cero o varios por contenido. `general` solo cuando el texto no concreta.

**Geografía**. `Ambito` dice el alcance; `CONTENIDO_GEO` dice dónde. Una
noticia del Ayuntamiento de Mataró lleva `MUNICIPIO` + `08121` y el sistema
deriva Barcelona y Cataluña del maestro. Una ley estatal lleva `NACIONAL` y
ninguna fila geo. Una campaña en tres provincias lleva `MULTI` y tres filas.

**Tags**. Libres, 5-10, genéricos, en castellano, generados por el LLM con
las mismas reglas que KM0 (sin nombres propios ni lugares).

### 3.4. Ciclo de vida

| Tipo | Caduca | Acción |
| --- | --- | --- |
| NOTICIA, INICIATIVA | `Fecha_Publicacion + 10` | Borrado físico con binarios, al inicio de cada run |
| EVENTO | `Fecha_Fin` o `Fecha_Inicio` pasada | Borrado físico, igual que KM0 |
| PROMOCION | `Fecha_Fin` o 30 días | Fase 2 |
| ALOJAMIENTO, RECURSO | No caduca | `RETIRADO` si la fuente deja de listarlo (fase 2) |

---

## 4. Enriquecimiento con IA

Mismo modelo y mismo wrapper que KM0 (`gpt-4.1-mini` por defecto,
`gpt-4.1-nano` opcional para clasificación de listados). Cuatro llamadas
como máximo por contenido nuevo; cero para lo que ya existe o no cambió.

### 4.1. Pasos

1. **Captura** del target con GET condicional y fingerprint. Si no cambió, fin.
2. **Clasificación del listado** (una llamada por página de listado). Esquema `items[]` con `tipo ∈ {NOTICIA, EVENTO, DESCARTAR}`, `relevancia 0..1`, `motivo`, `titulo`, `url_detalle`, `fecha`, `lugar_corto`, `imagen_url`. La relevancia pregunta explícitamente: "¿trata de animales de compañía, protección animal, convivencia con animales o viajar con ellos en España?". Umbral de corte configurable, 0,6 por defecto. Todo lo descartado se cuenta en `INGESTA_DESCARTES` con una muestra.
3. **Filtro barato previo**: título ya existente en BD (similitud como KM0), fecha fuera de ventana, dominio no permitido por robots.
4. **Detalle** (una llamada, extractiva). Cuerpo, fecha, lugar, entidad, precio, inscripción, lugares mencionados, animales mencionados. Solo datos que estén en el texto; `null` si no están. Esto es lo "extraído".
5. **Enriquecimiento** (una llamada, generativa). Título normalizado, resumen de 3 frases, tags, temas del catálogo con principal, animales del catálogo, ámbito geográfico y nombres de lugar normalizados, tipo de entidad. Esto es lo "inferido" y "generado".
6. **Resolución geográfica** sin LLM: los nombres de lugar se normalizan y se buscan en `GEO_MUNICIPIOS` y `GEO_PROVINCIAS`. Ambigüedad (varios municipios con el mismo nombre) se resuelve con la provincia si el texto la menciona, si no con el `Ambito_Default` de la fuente, y si sigue ambigua se sube el nivel a provincia o se deja `NACIONAL`. Nunca se inventa un municipio.
7. **Deduplicación multi-fuente**: embedding de "título + resumen", coseno contra contenidos activos del mismo tipo y ventana de ±7 días. Por encima de 0,92 se registra como fuente adicional del contenido existente. Entre 0,80 y 0,92 decide un juez LLM. Nunca se borra el perdedor: se enlaza.
8. **Persistencia transaccional** con procedencia por campo y, si procede, imagen.

### 4.2. Procedencia

`Procedencia` guarda para cada campo uno de `extraido`, `inferido`,
`generado`, `fuente` (viene de la configuración de la fuente) o `maestro`
(resuelto contra el maestro geográfico). La UI lo muestra con un icono por
campo. Es el requisito explícito de trazabilidad del brief.

### 4.3. Conjunto de evaluación

Antes de fiarse del clasificador: 100 ítems etiquetados a mano (tipo,
relevante sí/no, tema principal, animales, ámbito) en un CSV versionado en
`scripts/fuentes_animalista/eval/`. Un script calcula precisión y cobertura
por dimensión en cada cambio de prompt. Sin esto, cualquier ajuste es a ciegas.

---

## 5. Estrategia de fuentes

### 5.1. Principio

No se rastrea Internet. Se mantiene a mano una lista corta de fuentes de
calidad, y se usa **Google News RSS por consulta** como capa de
descubrimiento que trae enlaces de cientos de medios locales sin tener que
registrarlos uno a uno.

### 5.2. Tipos de fuente y conector

| Tipo | Conector | Coste LLM | Ejemplo |
| --- | --- | --- | --- |
| `FEED_CONSULTA` | RSS (Google News) → resolver redirección → detalle | Clasificación + detalle + enriquecimiento | `bienestar animal perros when:14d` |
| `MEDIO` con RSS | RSS → detalle | Igual, sin clasificación de listado | Animal's Health |
| `MEDIO` / `PORTAL` sin RSS | Listado HTML → clasificación → detalle | Igual que KM0 | Secciones de mascotas de diarios |
| `OFICIAL` | Listado HTML o RSS | Igual | Ministerio, consejerías, ayuntamientos |
| `ASOCIACION` | RSS o listado | Igual | FAPAM, protectoras |
| `AGREGADOR` de eventos | HTML con JSON-LD si existe | Cero si hay JSON-LD | Eventbrite, Fires Catalanes |
| `RED_SOCIAL` Telegram | Conector KM0 | Clasificación en lote | Canales de protectoras |

Instagram, Facebook y X quedan fuera: sin proveedor de pago no hay acceso fiable.

### 5.3. Fuentes verificadas en vivo (12-10-2026)

| Fuente | URL | Resultado |
| --- | --- | --- |
| Google News RSS, consulta "bienestar animal perros" | `news.google.com/rss/search?q=...&hl=es&gl=ES&ceid=ES:es` | RSS válido, ítems del mismo día de La Vanguardia, El Español, Telecinco, Madridiario… |
| Google News RSS, consulta de ferias y eventos de mascotas | ídem con `feria OR evento mascotas perros when:14d` | RSS válido: Feria de Animales de Compañía de Pontevedra, feria de adopciones de Albacete, Festival Mascotear… |
| Animal's Health | `animalshealth.es/rss` | RSS válido, 18+ ítems, sector veterinario y bienestar |
| FAPAM | `fapam.org/feed/` | RSS válido, adopciones del CIAAM de Colmenar Viejo |

### 5.4. Candidatas pendientes de verificar

Fallaron o no se pudieron comprobar desde esta sesión. Hay que probarlas
desde el PC antes de darlas de alta:

- Secciones de mascotas de diarios generalistas: 20minutos Animaleros, La Vanguardia Mascotas, ABC Mascotas, El País. Bloqueadas o sin feed conocido; probable listado HTML.
- Portales pet-friendly: SrPerro (su `/feed/` devuelve 410, probar listado), Travelguau, Redcanina (agenda de eventos caninos), Viajar con perros.
- Protectoras y fundaciones: El Refugio, ANAA, Fundación Affinity (sala de prensa, sin feed), Altarriba.
- Instituciones: Dirección General de Derechos de los Animales (web del Ministerio de Derechos Sociales), prensa del MAPA (error de certificado desde aquí), BOE API de datos abiertos (`/datosabiertos/api/boe/sumario/AAAAMMDD` devolvió 400; revisar formato).
- Ferias: IFEMA Iberzoo+Propet (profesional), 100x100 Mascota, Expo Mascotas Alicante, FIMASCOTA Valladolid, Espacio Mascotas Gijón. Webs de recinto, una página por edición.
- Agregadores de eventos: Eventbrite (listado por palabra clave; JSON-LD no confirmado en el texto renderizado, comprobar en el HTML crudo), Meetup, Fires Catalanes (ya en KM0).
- Calendario RSCE de exposiciones caninas: la URL probada devolvió una imagen; localizar la página real.

### 5.5. Catálogo inicial de consultas Google News

Una fuente `FEED_CONSULTA` por consulta. Ventana `when:7d` para runs
semanales, `when:14d` para quincenales.

```
bienestar animal perros | bienestar animal gatos | ley bienestar animal
adopción perros protectora | adopción gatos colonia felina
playa para perros | parque canino | zona de esparcimiento canino
hotel admite mascotas | viajar con perro | pet friendly
feria mascotas | exposición canina | agility | canicross
ayuntamiento animales ordenanza | sanción maltrato animal
```

Cada consulta puede acotarse por comunidad añadiendo su nombre. Google
devuelve enlaces de redirección: el conector los resuelve y aplica robots del
dominio final antes de descargar el detalle.

### 5.6. Reglas de respeto y derechos

- `robots.txt` y `Crawl-delay` se leen y cachean por dominio. Un dominio que prohíbe la ruta se cuenta en `INGESTA_DESCARTES` con motivo `ROBOTS`.
- Se persiste **solo el resumen generado y el enlace**, nunca el artículo. Es el mismo patrón que ya aplica KM0 a noticias.
- Imágenes: se descargan solo de fuentes con `Imagenes_Permitidas=1` (organismos públicos, asociaciones que lo autoricen). Para el resto, portada generada por IA con el mecanismo que ya existe, o sin imagen. **Decisión pendiente** del product owner (ver §8).
- Un `User-Agent` identificable con URL de contacto.

### 5.7. Cobertura territorial progresiva

Semana 1: consultas nacionales y las fuentes verificadas. Semana 2: una
consulta por comunidad autónoma para las cinco con más población. A partir de
ahí, se añaden provincias y ayuntamientos grandes según lo que la pestaña de
calidad muestre como huecos. El maestro INE permite medir cobertura por
provincia desde el primer día.

---

## 6. Interfaz en events-query

Nueva pestaña **El Viajero Animalista** en `frontend/src/App.jsx`, al mismo
nivel que Eventos, Noticias y Costes, con tres sub-vistas. Mismo React 18 y
mismo CSS; nada de librerías nuevas.

**Contenidos.** Tarjetas con tipo, título, resumen, fecha, badges de temas y
animales, ámbito y lugares, relevancia, fuente principal con enlace y número
de fuentes adicionales. Filtros: tipo, tema, animal, comunidad, provincia,
fuente, rango de fechas, relevancia mínima, texto libre. Detalle expandible
con la procedencia por campo y la lista de fuentes.

**Fuentes.** Tabla de `FUENTES` con estado del último target, ítems
aportados, descartes por motivo y último error. Acciones: activar,
desactivar, añadir fuente por URL o consulta, editar prioridad. Esta es la
única escritura de la UI.

**Ejecuciones.** Botón "Ejecutar ingesta" (pide el secret, igual que el
endpoint de KM0), estado del lock, lista de runs con coste, contenidos
persistidos y descartes por fuente y motivo. Es la vista de calidad.

**Endpoints**

```
GET   /api/v1/animalista/contenidos        filtros + paginación
GET   /api/v1/animalista/contenidos/{id}
GET   /api/v1/animalista/taxonomia         temas, animales, ccaa, provincias
GET   /api/v1/animalista/fuentes
POST  /api/v1/animalista/fuentes           (secret)
PATCH /api/v1/animalista/fuentes/{id}      (secret)
POST  /api/v1/animalista/ingest/run        (secret)
GET   /api/v1/animalista/ingest/status
GET   /api/v1/animalista/runs
GET   /api/v1/animalista/runs/{id}         costes y descartes
```

---

## 7. Plan por fases

Estimaciones de orden de magnitud en días de trabajo efectivo.

| Fase | Entregable | Verificación | Días |
| --- | --- | --- | --- |
| **0. Cimientos** | Esquema `animalista_db`, maestro INE cargado, taxonomía sembrada, 15-20 fuentes semilla verificadas desde el PC, CSV de evaluación vacío con plantilla | SQL idempotente aplicado en docker compose; `SELECT COUNT(*)` de municipios ≈ 8.100 | 1-2 |
| **1. Núcleo común** | `app/ingest_core/` extraído; `ingest_all.py` lo importa | Dry-run de Malgrat antes y después con mismos candidatos y coste | 2-3 |
| **2. Pipeline animalista** | Conectores RSS y Google News, clasificación con relevancia, detalle, enriquecimiento, geo-resolución, dedupe no destructivo, persistencia, purga, descartes | Run completo sobre las fuentes semilla; informe de descartes por fuente | 4-6 |
| **3. API y pestaña** | Router y tres sub-vistas | Entrar, filtrar por Cataluña y perros, lanzar ingesta desde la UI | 3-4 |
| **4. Calibración** | 100 ítems etiquetados, script de métricas, ajuste de prompts y umbral | Precisión de relevancia y tipo por encima del 85 % en el set | 2 |
| **5. UAT** | Segundo MySQL en Railway, variables `ANIMALISTA_DB_*`, pestaña visible en `eventquery.uat` | Run bajo demanda desde la UI en UAT | 1 |

Después del MVP, por este orden: alojamientos y promociones (fuentes de
otro tipo, ciclo de vida propio), coordenadas y mapa, API pública para la web
de El Viajero Animalista, y personalización por usuario.

### Estado

- **12-10-2026, tarde.** Validación del paradigma cerrada con el mockup (todo OK). Fichas de adopción pasan a tipo `RECURSO` desde el MVP. Decisiones pendientes de §8 cerradas con los valores propuestos.
- **Fase 0 escrita** en la rama `feature/animalista-fase0`: `SQL/animalista/` (schema, grant local, seed geo, seed taxonomía), `scripts/animalista/` (conexión, cargador INE probado en seco con 8.132 municipios, semilla de 18 fuentes, plantilla de evaluación), montaje en `docker-compose.yml` y variables en `.env.example`. Pendiente aplicar contra MySQL local (Docker parado al escribirlo).

### Qué gana KM0 de paso

La fase 1 es el refactor que el plan de septiembre pedía. `INGESTA_DESCARTES`
y la comprobación de robots se pueden activar después en KM0 sin tocar su
esquema de eventos.

---

## 8. Decisiones pendientes

1. **Imágenes de medios de prensa**: ¿se descargan como hace KM0 con las webs municipales, o solo de fuentes autorizadas y el resto con portada IA? Propuesta: lo segundo.
2. **Umbral de relevancia** inicial: 0,6 propuesto; se ajusta en la fase 4.
3. **Ventana de eventos**: ¿cuántos días hacia delante interesan? Propuesta: sin límite superior, se purgan al pasar.
4. **Consultas Google News por comunidad** desde el día 1 o solo nacionales en la primera semana. Propuesta: nacionales primero para medir ruido.
5. **Nombre técnico** de BD y paquete: `animalista_db` y `app/animalista/`. Cualquier otro vale, pero conviene fijarlo antes de la fase 0.

---

## Apéndice — Qué está verificado y qué no

**Verificado leyendo el código del repo (12-10-2026):** todo lo descrito en §1.

**Verificado en vivo:** las cuatro fuentes de §5.3.

**No verificado:** las fuentes de §5.4, la disponibilidad de JSON-LD en los
listados de Eventbrite, el formato correcto de la API de datos abiertos del
BOE, y el volumen real de ruido de Google News hasta hacer el primer run.
