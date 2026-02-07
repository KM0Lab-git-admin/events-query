# 👨‍💻 Guía de Desarrollo - Events Query API

**Guía completa para desarrolladores que van a modificar o extender el proyecto**

---

> 📌 **Docs relacionados (documentación unificada)**  
> - [API (Legacy + v1)](./API.md)  
> - [Deploy en Railway](./DEPLOYMENT.md)  
> - [Arquitectura](./ARCHITECTURE.md)  
> - [Modelo de datos + Ingesta IA](./DATA_MODEL.md)  
> - [Desarrollo](./DEVELOPMENT.md)  
> - [Troubleshooting](./TROUBLESHOOTING.md)


## 📋 Tabla de Contenidos

1. [Estructura del Proyecto](#estructura-del-proyecto)
2. [Cómo Funciona la Búsqueda](#cómo-funciona-la-búsqueda)
3. [Sistema de Análisis Detallado](#sistema-de-análisis-detallado)
4. [Cómo Añadir Features](#cómo-añadir-features)
5. [Testing y Validación](#testing-y-validación)
6. [Mejores Prácticas](#mejores-prácticas)
7. [Roadmap Futuro](#roadmap-futuro)

---

## Estructura del Proyecto

```
events-query/
├── app/                          # Backend
│   ├── __init__.py
│   ├── main.py                   # FastAPI app principal
│   ├── config.py                 # Configuración (env vars)
│   ├── api/
│   │   ├── __init__.py
│   │   └── routes.py             # Endpoints REST
│   ├── models/
│   │   ├── __init__.py
│   │   └── schemas.py            # Modelos Pydantic
│   └── services/
│       ├── __init__.py
│       ├── events_service.py     # Orquestador principal
│       ├── ai_service.py         # OpenAI integration
│       ├── database.py           # MySQL connection pool
│       ├── query_builder.py      # SQL query builder
│       └── analysis_service.py   # Análisis detallado
├── frontend/                     # Frontend React
│   ├── src/
│   │   ├── main.jsx              # Entry point
│   │   ├── App.jsx               # Componente principal
│   │   ├── EventsList.jsx        # Lista de eventos
│   │   ├── QueryChat.jsx         # Chat de consultas
│   │   ├── AnalysisView.jsx      # Análisis detallado
│   │   └── index.css             # Estilos
│   ├── index.html
│   ├── vite.config.js
│   └── package.json
├── SQL/
│   └── SCHEMA_SQL_FINAL.sql      # Esquema de BD
├── scripts/
│   ├── generate_fake_data.py     # Generador de datos fake
│   └── schema.sql                # Esquema legacy
├── tests/                        # Tests (TODO)
├── docs/                         # Documentación
│   ├── ARCHITECTURE.md
│   ├── QUICKSTART.md
│   ├── DEVELOPMENT.md            # Este archivo
│   └── TROUBLESHOOTING.md
├── docs-old/                     # Documentación legacy (backup)
├── .env.example                  # Ejemplo de variables de entorno
├── .gitignore
├── requirements.txt              # Dependencias Python
└── README.md                     # README principal
```

---

## Cómo Funciona la Búsqueda

### Flujo Completo (6 Pasos)

```
Usuario → Extracción Parámetros → Cálculo Geográfico → Pre-filtrado SQL 
        → Búsqueda Semántica → Respuesta Natural → Análisis Detallado
```

### Paso 1: Extracción de Parámetros (OpenAI)

**Archivo:** `app/services/ai_service.py`

**Función:** `extract_parameters(pregunta, cp_usuario)`

**Propósito:** Convertir lenguaje natural a parámetros estructurados.

**Input:**
```python
pregunta = "¿Qué hacer este fin de semana con niños?"
cp_usuario = "08380"
```

**Proceso:**
1. Detecta idioma (español/catalán)
2. Extrae conceptos clave ("niños", "fin de semana")
3. Extrae fechas (si se mencionan)
4. Extrae categorías (si se mencionan)
5. Extrae radio (si se menciona)
6. Extrae precio/gratuito (si se menciona)

**Output:**
```python
{
    "idioma": "es",
    "conceptos": ["niños", "fin de semana"],
    "fechas": ["2026-01-25", "2026-01-26"],
    "fecha_inicio": "2026-01-25",
    "fecha_fin": "2026-01-26",
    "categorias": ["infantil"],
    "radio_km": null,
    "es_gratuito": null,
    "precio_max": null
}
```

**Implementación:**

```python
async def extract_parameters(self, pregunta: str, cp_usuario: str) -> ExtractedParameters:
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT},
        {"role": "user", "content": f"Pregunta: {pregunta}\nCP: {cp_usuario}"}
    ]
    
    response = await self.client.chat.completions.create(
        model="gpt-4.1-mini",
        messages=messages,
        functions=[EXTRACTION_FUNCTION],
        function_call={"name": "extract_parameters"}
    )
    
    return ExtractedParameters(**json.loads(response.choices[0].message.function_call.arguments))
```

**Tiempo:** ~500ms

---

### Paso 2: Cálculo Geográfico

**Archivo:** `app/services/database.py`

**Función:** `get_codigos_postales_in_radius(cp_usuario, radio_km)`

**Propósito:** Encontrar códigos postales en un radio de X kilómetros.

**Input:**
```python
cp_usuario = "08380"
radio_km = 20  # o null si no se especifica
```

**Proceso:**
1. Obtiene coordenadas del CP del usuario
2. Si radio es null, retorna solo el CP del usuario
3. Si radio > 0, busca todos los CPs en la BD
4. Calcula distancia con fórmula Haversine
5. Filtra CPs dentro del radio

**Output:**
```python
["08380", "08370", "08360", "08397", "17300"]  # CPs en 20km
```

**Implementación:**

```python
async def get_codigos_postales_in_radius(self, cp_usuario: str, radio_km: float = None):
    # Obtener coordenadas del usuario
    coords_usuario = await self.get_coordinates_by_cp(cp_usuario)
    
    if radio_km is None:
        return [cp_usuario]
    
    # Obtener todos los CPs
    query = "SELECT CP, Latitud, Longitud FROM CODIGOS_POSTALES"
    cps = await self.execute_query(query, ())
    
    # Filtrar por distancia
    cps_validos = []
    for cp in cps:
        distancia = self._calculate_distance(
            coords_usuario['lat'], coords_usuario['lng'],
            cp['Latitud'], cp['Longitud']
        )
        if distancia <= radio_km:
            cps_validos.append(cp['CP'])
    
    return cps_validos
```

**Fórmula Haversine:**

```python
def _calculate_distance(self, lat1, lon1, lat2, lon2):
    R = 6371  # Radio de la Tierra en km
    
    dlat = math.radians(lat2 - lat1)
    dlon = math.radians(lon2 - lon1)
    
    a = math.sin(dlat/2)**2 + math.cos(math.radians(lat1)) * \
        math.cos(math.radians(lat2)) * math.sin(dlon/2)**2
    
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1-a))
    
    return R * c
```

**Tiempo:** ~50ms

---

### Paso 3: Pre-filtrado SQL

**Archivo:** `app/services/query_builder.py`

**Función:** `build_events_query(codigos_postales, params)`

**Propósito:** Construir query SQL con filtros exactos.

**Input:**
```python
codigos_postales = ["08380", "08370", "08360"]
params = ExtractedParameters(
    idioma="es",
    fecha_inicio="2026-01-25",
    fecha_fin="2026-01-26",
    categorias=["infantil"]
)
```

**Query Generada:**

```sql
SELECT DISTINCT
    em.ID_Unico_Evento as id_unico_evento,
    CASE WHEN 'es' = 'es' THEN em.Titulo_ES ELSE em.Titulo_CAT END as titulo,
    CASE WHEN 'es' = 'es' THEN em.Desc_Larga_ES ELSE em.Desc_Larga_CAT END as descripcion_larga,
    em.CP_Evento as cp_evento,
    em.Poblacion_Nombre as poblacion_nombre,
    eh.Fecha_Inicio as fecha_inicio,
    em.Es_Gratuito as es_gratuito,
    em.Precio_Euros as precio_euros,
    CASE WHEN 'es' = 'es' THEN em.Tags_ES ELSE em.Tags_CAT END as tags_json,
    CASE WHEN 'es' = 'es' THEN em.Tags_Embedding_ES ELSE em.Tags_Embedding_CAT END as tags_embedding_json
FROM EVENTOS_MASTER em
INNER JOIN EVENTO_HORARIOS eh ON em.ID_Unico_Evento = eh.ID_Unico_Evento
INNER JOIN CODIGOS_POSTALES cp ON em.CP_Evento = cp.CP
LEFT JOIN EVENTO_CATEGORIAS ec ON em.ID_Unico_Evento = ec.ID_Unico_Evento
LEFT JOIN CATEGORIAS c ON ec.ID_Categoria = c.ID_Categoria
WHERE em.Estado = 'ACTIVO'
  AND em.CP_Evento IN ('08380', '08370', '08360')
  AND eh.Fecha_Inicio BETWEEN '2026-01-25' AND '2026-01-26'
  AND c.Nombre_Categoria IN ('infantil')
ORDER BY eh.Fecha_Inicio ASC, eh.Hora_Inicio ASC
LIMIT 50
```

**Filtros Aplicados:**
- ✅ CP_Evento IN (lista de CPs)
- ✅ Fecha BETWEEN (si se especifica)
- ✅ Categorías (si se especifican)
- ✅ Estado = 'ACTIVO'
- ❌ NO filtra por tags (se hace después)

**Output:** 50 eventos (máximo)

**Tiempo:** ~120ms

---

### Paso 4: Búsqueda Semántica

**Archivo:** `app/services/events_service.py`

**Función:** `_semantic_search(eventos_raw, conceptos, idioma)`

**Propósito:** Filtrar eventos por similitud semántica con los conceptos.

**Input:**
```python
eventos_raw = [...]  # 50 eventos del SQL
conceptos = ["niños", "fin de semana"]
idioma = "es"
```

**Proceso:**

1. **Generar embedding de conceptos:**
   ```python
   conceptos_text = " ".join(conceptos)  # "niños fin de semana"
   query_embedding = await ai_service.generate_embedding(conceptos_text)
   # query_embedding = [0.123, 0.456, ..., 0.789]  # 1536 dims
   ```

2. **Para cada evento:**
   ```python
   for evento in eventos_raw:
       # Obtener embedding del evento (ya pre-calculado)
       evento_embedding = json.loads(evento['tags_embedding_json'])
       
       # Calcular similitud (coseno)
       similitud = cosine_similarity(query_embedding, evento_embedding)
       
       # Añadir al evento
       evento['similitud_score'] = similitud
   ```

3. **Filtrar por umbral:**
   ```python
   umbral = 0.4  # Configurable
   eventos_filtrados = [e for e in eventos_raw if e['similitud_score'] >= umbral]
   ```

**Fórmula de Similitud (Coseno):**

```python
def cosine_similarity(vec1, vec2):
    dot_product = sum(a * b for a, b in zip(vec1, vec2))
    magnitude1 = math.sqrt(sum(a * a for a in vec1))
    magnitude2 = math.sqrt(sum(b * b for b in vec2))
    return dot_product / (magnitude1 * magnitude2)
```

**Output:** 10 eventos (aprox.)

**Tiempo:** ~130ms

---

### Paso 5: Respuesta Natural

**Archivo:** `app/services/ai_service.py`

**Función:** `generate_response(eventos, pregunta, idioma)`

**Propósito:** Generar texto explicativo en lenguaje natural.

**Input:**
```python
eventos = [...]  # 10 eventos filtrados
pregunta = "¿Qué hacer este fin de semana con niños?"
idioma = "es"
```

**Prompt:**

```python
system_prompt = """
Eres un asistente que ayuda a encontrar eventos locales.
Genera una respuesta natural y amigable basada en los eventos encontrados.
"""

user_prompt = f"""
Pregunta del usuario: {pregunta}
Idioma: {idioma}

Eventos encontrados:
{json.dumps(eventos, indent=2)}

Genera una respuesta natural que:
1. Resuma los eventos encontrados
2. Destaque los más relevantes
3. Sea amigable y útil
"""
```

**Output:**

```
"He encontrado 10 eventos perfectos para niños este fin de semana en tu zona. 
Destacan: Cuentacuentos en la biblioteca (gratis, sábado 17:30), 
Taller de manualidades infantiles (domingo 10:00), y 
Parque de aventuras al aire libre (ambos días, 9:00-18:00). 
¿Te gustaría más detalles sobre alguno?"
```

**Tiempo:** ~500ms

---

### Paso 6: Análisis Detallado (Opcional)

**Archivo:** `app/services/analysis_service.py`

**Función:** `analyze_batch(eventos, pregunta_embedding, conceptos, umbral)`

**Propósito:** Analizar paso a paso por qué cada evento pasa o no el filtro.

**Solo se ejecuta si `debug=true` en el request.**

Ver sección [Sistema de Análisis Detallado](#sistema-de-análisis-detallado) para más detalles.

**Tiempo:** ~2000ms (solo en debug mode)

---

## Sistema de Análisis Detallado

### Propósito

Entender **por qué** la IA toma cada decisión y **cómo mejorar** la precisión del sistema.

### Componentes

#### 1. Análisis de Similitud

**Archivo:** `app/services/analysis_service.py`

**Función:** `analyze_event_similarity(evento, pregunta_embedding, conceptos, umbral)`

**Qué Analiza:**

1. **Similitud por tag individual:**
   ```python
   tags = json.loads(evento['tags_json'])  # ["niños", "infantil", "juegos"]
   
   for tag in tags:
       tag_embedding = await ai_service.generate_embedding(tag)
       similitud = cosine_similarity(pregunta_embedding, tag_embedding)
       
       tag_analysis.append({
           "tag": tag,
           "similitud": similitud,
           "relevancia": "alta" if similitud >= 0.5 else "media" if similitud >= 0.3 else "baja"
       })
   ```

2. **Similitud por categoría:**
   ```python
   categoria = evento['categoria']  # "Infantil"
   categoria_embedding = await ai_service.generate_embedding(categoria)
   similitud_categoria = cosine_similarity(pregunta_embedding, categoria_embedding)
   ```

3. **Similitud por descripción:**
   ```python
   descripcion = evento['descripcion_larga']
   desc_embedding = await ai_service.generate_embedding(descripcion)
   similitud_descripcion = cosine_similarity(pregunta_embedding, desc_embedding)
   ```

**Output:**

```python
{
    "evento_id": "EVT123",
    "titulo": "Cuentacuentos en la biblioteca",
    "score_total": 0.75,
    "pasa_filtro": True,
    "umbral": 0.4,
    
    "similitud_por_tag": [
        {"tag": "infantil", "similitud": 0.82, "relevancia": "alta"},
        {"tag": "cultura", "similitud": 0.45, "relevancia": "media"},
        {"tag": "lectura", "similitud": 0.38, "relevancia": "media"}
    ],
    
    "similitud_categoria": {
        "categoria": "Infantil",
        "similitud": 0.78,
        "relevancia": "alta"
    },
    
    "similitud_descripcion": {
        "similitud": 0.62,
        "relevancia": "alta"
    }
}
```

---

#### 2. Diagnóstico Automático

**Función:** `_diagnose_problems(analisis, evento, umbral)`

**Detecta 5 tipos de problemas:**

| Problema | Condición | Severidad |
|----------|-----------|-----------|
| **SCORE_BAJO** | `score < umbral` | CRÍTICA |
| **CATEGORIA_IRRELEVANTE** | `similitud_categoria < 0.3` | ALTA |
| **TAGS_INSUFICIENTES** | `< 3 tags con similitud > 0.3` | MEDIA |
| **DESCRIPCION_POCO_RELEVANTE** | `similitud_descripcion < 0.3` | MEDIA |
| **SIN_EMBEDDING** | `tags_embedding_json is null` | CRÍTICA |

**Output:**

```python
"problemas_detectados": [
    {
        "tipo": "SCORE_BAJO",
        "severidad": "CRÍTICA",
        "descripcion": "Score 0.35 no alcanza el umbral de 0.4",
        "impacto": "Evento descartado en búsqueda"
    },
    {
        "tipo": "CATEGORIA_IRRELEVANTE",
        "severidad": "ALTA",
        "descripcion": "Categoría 'Cultura' tiene similitud 0.15 con la búsqueda",
        "impacto": "Reduce score total significativamente"
    }
]
```

---

#### 3. Propuestas de Mejora

**Función:** `_generate_solutions(problemas, analisis, evento, conceptos)`

**Genera 4 tipos de soluciones:**

##### A. Cambiar Categoría

```python
if problema.tipo == "CATEGORIA_IRRELEVANTE":
    # Buscar categoría más relevante
    categorias_sugeridas = ["Infantil", "Gastronomía", "Deportes", ...]
    
    for cat in categorias_sugeridas:
        cat_embedding = await ai_service.generate_embedding(cat)
        similitud = cosine_similarity(pregunta_embedding, cat_embedding)
        
        if similitud > 0.5:
            soluciones.append({
                "tipo": "cambiar_categoria",
                "prioridad": "ALTA",
                "categoria_actual": evento['categoria'],
                "categoria_sugerida": cat,
                "impacto_estimado": 0.20,
                "score_estimado": evento['score'] + 0.20
            })
```

##### B. Añadir Tags

```python
if problema.tipo == "TAGS_INSUFICIENTES":
    # Generar tags sugeridos desde conceptos
    tags_sugeridos = conceptos + ["relacionado1", "relacionado2"]
    
    soluciones.append({
        "tipo": "añadir_tags",
        "prioridad": "ALTA",
        "tags_actuales": evento['tags'],
        "tags_sugeridos": tags_sugeridos,
        "impacto_estimado": 0.15,
        "score_estimado": evento['score'] + 0.15
    })
```

##### C. Mejorar Descripción

```python
if problema.tipo == "DESCRIPCION_POCO_RELEVANTE":
    soluciones.append({
        "tipo": "mejorar_descripcion",
        "prioridad": "MEDIA",
        "palabras_clave_sugeridas": conceptos,
        "impacto_estimado": 0.08,
        "score_estimado": evento['score'] + 0.08
    })
```

##### D. Generar Embedding

```python
if problema.tipo == "SIN_EMBEDDING":
    soluciones.append({
        "tipo": "generar_embedding",
        "prioridad": "CRÍTICA",
        "impacto_estimado": 0.30,
        "score_estimado": 0.30  # Asume score mínimo
    })
```

**Output Completo:**

```python
{
    "evento_id": "EVT123",
    "titulo": "Cata de vinos y quesos - Malgrat de Mar",
    "score_total": 0.35,
    "pasa_filtro": False,
    "umbral": 0.4,
    
    "problemas_detectados": [
        {
            "tipo": "SCORE_BAJO",
            "severidad": "CRÍTICA",
            "descripcion": "Score 0.35 no alcanza umbral 0.4"
        },
        {
            "tipo": "CATEGORIA_IRRELEVANTE",
            "severidad": "ALTA",
            "descripcion": "Categoría 'Cultura' tiene similitud 0.15"
        }
    ],
    
    "soluciones_propuestas": [
        {
            "tipo": "cambiar_categoria",
            "prioridad": "ALTA",
            "categoria_actual": "Cultura",
            "categoria_sugerida": "Gastronomía",
            "razon": "Similitud 0.75 con la búsqueda 'actividades de comida'",
            "impacto_estimado": 0.20,
            "score_estimado": 0.55
        },
        {
            "tipo": "añadir_tags",
            "prioridad": "ALTA",
            "tags_actuales": ["vinos", "quesos", "cata"],
            "tags_sugeridos": ["comida", "gastronomía", "alimentación", "degustación"],
            "impacto_estimado": 0.15,
            "score_estimado": 0.68
        }
    ]
}
```

---

### Visualización en Frontend

**Componente:** `frontend/src/AnalysisView.jsx`

**Renderiza:**

```jsx
<div className="analysis-view">
  {analisis.map(evento => (
    <div key={evento.evento_id} className="evento-analysis">
      <h3>{evento.titulo}</h3>
      <div className="score">
        Score: {evento.score_total} 
        {evento.pasa_filtro ? "✅" : "❌"}
      </div>
      
      {/* Similitud por tag */}
      <div className="tags">
        {evento.similitud_por_tag.map(tag => (
          <div className="tag-bar">
            <span>{tag.tag}</span>
            <div className="bar" style={{width: `${tag.similitud * 100}%`}} />
            <span>{tag.similitud.toFixed(2)}</span>
          </div>
        ))}
      </div>
      
      {/* Problemas */}
      <div className="problemas">
        {evento.problemas_detectados.map(problema => (
          <div className={`problema ${problema.severidad}`}>
            {problema.descripcion}
          </div>
        ))}
      </div>
      
      {/* Soluciones */}
      <div className="soluciones">
        {evento.soluciones_propuestas.map(solucion => (
          <div className={`solucion ${solucion.prioridad}`}>
            <strong>{solucion.tipo}</strong>
            <p>{solucion.razon}</p>
            <span>Impacto: +{solucion.impacto_estimado}</span>
            <span>Score estimado: {solucion.score_estimado}</span>
          </div>
        ))}
      </div>
    </div>
  ))}
</div>
```

---

## Cómo Añadir Features

### 1. Añadir Nuevo Endpoint

**Ejemplo:** Endpoint para obtener eventos por categoría.

**Paso 1:** Añadir ruta en `app/api/routes.py`

```python
@router.get("/events/by-category/{categoria}")
async def get_events_by_category(categoria: str):
    """Obtiene eventos por categoría"""
    eventos = await events_service.get_events_by_category(categoria)
    return {"eventos": eventos, "total": len(eventos)}
```

**Paso 2:** Añadir método en `app/services/events_service.py`

```python
async def get_events_by_category(self, categoria: str) -> List[Evento]:
    query = """
        SELECT em.*, c.Nombre_Categoria
        FROM EVENTOS_MASTER em
        JOIN EVENTO_CATEGORIAS ec ON em.ID_Unico_Evento = ec.ID_Unico_Evento
        JOIN CATEGORIAS c ON ec.ID_Categoria = c.ID_Categoria
        WHERE c.Nombre_Categoria = %s
        AND em.Estado = 'ACTIVO'
    """
    eventos_raw = await self.db_service.execute_query(query, (categoria,))
    return self._convert_to_eventos(eventos_raw)
```

**Paso 3:** Probar

```bash
curl http://localhost:8000/events/by-category/Infantil
```

---

### 2. Añadir Nuevo Filtro

**Ejemplo:** Filtrar por precio máximo.

**Paso 1:** Añadir campo en `app/models/schemas.py`

```python
class QueryRequest(BaseModel):
    pregunta: str
    cp_usuario: str
    debug: bool = False
    precio_max: Optional[float] = None  # NUEVO
```

**Paso 2:** Modificar `query_builder.py`

```python
def build_events_query(codigos_postales, params):
    query = "SELECT ... WHERE ..."
    
    # NUEVO: Añadir filtro de precio
    if params.precio_max is not None:
        query += " AND (em.Es_Gratuito = TRUE OR em.Precio_Euros <= %s)"
        sql_params.append(params.precio_max)
    
    return query, tuple(sql_params)
```

**Paso 3:** Actualizar prompt de extracción en `ai_service.py`

```python
EXTRACTION_FUNCTION = {
    "name": "extract_parameters",
    "parameters": {
        "properties": {
            ...
            "precio_max": {
                "type": "number",
                "description": "Precio máximo en euros (si se menciona)"
            }
        }
    }
}
```

---

### 3. Añadir Nuevo Análisis

**Ejemplo:** Analizar similitud por organizador.

**Paso 1:** Añadir método en `analysis_service.py`

```python
async def _analyze_organizer_similarity(self, evento, pregunta_embedding):
    organizador = evento.get('organizador_nombre')
    if not organizador:
        return None
    
    org_embedding = await self.ai_service.generate_embedding(organizador)
    similitud = self._cosine_similarity(pregunta_embedding, org_embedding)
    
    return {
        "organizador": organizador,
        "similitud": similitud,
        "relevancia": "alta" if similitud >= 0.5 else "media" if similitud >= 0.3 else "baja"
    }
```

**Paso 2:** Integrar en `analyze_event_similarity`

```python
async def analyze_event_similarity(self, evento, pregunta_embedding, conceptos, umbral):
    analisis = {
        ...
        "similitud_organizador": await self._analyze_organizer_similarity(evento, pregunta_embedding)
    }
    return analisis
```

**Paso 3:** Actualizar frontend `AnalysisView.jsx`

```jsx
{analisis.similitud_organizador && (
  <div className="organizador">
    <strong>Organizador:</strong> {analisis.similitud_organizador.organizador}
    <span>Similitud: {analisis.similitud_organizador.similitud}</span>
  </div>
)}
```

---

## Testing y Validación

### Testing Manual

**Casos de Prueba Recomendados:**

#### 1. Búsqueda Básica

```bash
curl -X POST "http://localhost:8000/query" \
  -H "Content-Type: application/json" \
  -d '{
    "pregunta": "¿Qué hacer este fin de semana?",
    "cp_usuario": "08380",
    "debug": false
  }'
```

**Esperado:** 5-10 eventos relevantes

---

#### 2. Búsqueda con Categoría

```bash
curl -X POST "http://localhost:8000/query" \
  -H "Content-Type: application/json" \
  -d '{
    "pregunta": "Eventos infantiles",
    "cp_usuario": "08380",
    "debug": false
  }'
```

**Esperado:** Solo eventos de categoría "Infantil"

---

#### 3. Búsqueda con Radio

```bash
curl -X POST "http://localhost:8000/query" \
  -H "Content-Type: application/json" \
  -d '{
    "pregunta": "Conciertos en un radio de 20 kilómetros",
    "cp_usuario": "08380",
    "debug": false
  }'
```

**Esperado:** Eventos en 5 poblaciones (08380, 08370, 08360, 08397, 17300)

---

#### 4. Búsqueda Gratuita

```bash
curl -X POST "http://localhost:8000/query" \
  -H "Content-Type: application/json" \
  -d '{
    "pregunta": "Eventos gratuitos",
    "cp_usuario": "08380",
    "debug": false
  }'
```

**Esperado:** Solo eventos con `es_gratuito = true`

---

#### 5. Búsqueda en Catalán

```bash
curl -X POST "http://localhost:8000/query" \
  -H "Content-Type: application/json" \
  -d '{
    "pregunta": "Què fer aquest cap de setmana?",
    "cp_usuario": "08380",
    "debug": false
  }'
```

**Esperado:** Respuesta en catalán

---

### Testing con Análisis

```bash
curl -X POST "http://localhost:8000/query" \
  -H "Content-Type: application/json" \
  -d '{
    "pregunta": "Actividades relacionadas con comida",
    "cp_usuario": "08380",
    "debug": true
  }'
```

**Revisar:**
- `debug_info.parametros_extraidos`
- `debug_info.analisis_detallado`
- Problemas detectados
- Soluciones propuestas

---

### Testing Automatizado (TODO)

**Framework:** pytest + pytest-asyncio

**Estructura:**

```
tests/
├── test_api.py              # Tests de endpoints
├── test_services.py         # Tests de servicios
├── test_ai_service.py       # Tests de OpenAI
├── test_database.py         # Tests de BD
└── test_analysis.py         # Tests de análisis
```

**Ejemplo:**

```python
# tests/test_api.py
import pytest
from httpx import AsyncClient
from app.main import app

@pytest.mark.asyncio
async def test_query_endpoint():
    async with AsyncClient(app=app, base_url="http://test") as client:
        response = await client.post("/query", json={
            "pregunta": "¿Qué hacer este fin de semana?",
            "cp_usuario": "08380",
            "debug": False
        })
        
        assert response.status_code == 200
        data = response.json()
        assert "respuesta_texto" in data
        assert "eventos" in data
        assert len(data["eventos"]) > 0
```

---

## Mejores Prácticas

### 1. Código

- ✅ **Async/Await**: Usa `async def` y `await` para operaciones I/O
- ✅ **Type Hints**: Añade type hints en todas las funciones
- ✅ **Docstrings**: Documenta funciones complejas
- ✅ **Error Handling**: Usa try-except con logging
- ✅ **Validación**: Usa Pydantic para validar inputs

**Ejemplo:**

```python
async def get_events_by_category(self, categoria: str) -> List[Evento]:
    """
    Obtiene eventos por categoría.
    
    Args:
        categoria: Nombre de la categoría (ej: "Infantil")
        
    Returns:
        Lista de eventos de esa categoría
        
    Raises:
        DatabaseError: Si hay error en la BD
    """
    try:
        query = "SELECT ... WHERE c.Nombre_Categoria = %s"
        eventos_raw = await self.db_service.execute_query(query, (categoria,))
        return self._convert_to_eventos(eventos_raw)
    except Exception as e:
        logger.error(f"Error obteniendo eventos por categoría: {e}")
        raise DatabaseError(f"Error en BD: {e}")
```

---

### 2. Base de Datos

- ✅ **Connection Pooling**: Usa aiomysql con pool
- ✅ **Parámetros**: Usa queries parametrizadas (previene SQL injection)
- ✅ **Índices**: Añade índices en columnas frecuentemente filtradas
- ✅ **Transacciones**: Usa transacciones para operaciones múltiples

**Ejemplo:**

```python
# ✅ CORRECTO
query = "SELECT * FROM EVENTOS_MASTER WHERE CP_Evento = %s"
eventos = await db.execute_query(query, (cp,))

# ❌ INCORRECTO (SQL injection)
query = f"SELECT * FROM EVENTOS_MASTER WHERE CP_Evento = '{cp}'"
eventos = await db.execute_query(query, ())
```

---

### 3. OpenAI

- ✅ **Retries**: Usa tenacity para retries automáticos
- ✅ **Timeouts**: Configura timeout de 30s
- ✅ **Error Handling**: Maneja errores de API (rate limit, timeout)
- ✅ **Cache**: Cachea embeddings (TODO: Redis)

**Ejemplo:**

```python
from tenacity import retry, stop_after_attempt, wait_exponential

@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10)
)
async def generate_embedding(self, text: str) -> List[float]:
    try:
        response = await self.client.embeddings.create(
            model="text-embedding-3-small",
            input=text,
            timeout=30
        )
        return response.data[0].embedding
    except openai.RateLimitError:
        logger.warning("Rate limit alcanzado, reintentando...")
        raise
    except openai.Timeout:
        logger.error("Timeout en OpenAI")
        raise
```

---

### 4. Frontend

- ✅ **Loading States**: Muestra loading mientras carga
- ✅ **Error Handling**: Muestra errores al usuario
- ✅ **Debouncing**: Debounce en inputs de búsqueda
- ✅ **Responsive**: Diseño responsive

**Ejemplo:**

```jsx
function QueryChat() {
  const [loading, setLoading] = useState(false)
  const [error, setError] = useState(null)
  
  const handleSubmit = async () => {
    setLoading(true)
    setError(null)
    
    try {
      const response = await fetch('/query', {
        method: 'POST',
        headers: {'Content-Type': 'application/json'},
        body: JSON.stringify({pregunta, cp_usuario})
      })
      
      if (!response.ok) {
        throw new Error(`Error ${response.status}`)
      }
      
      const data = await response.json()
      setResultado(data)
    } catch (err) {
      setError(err.message)
    } finally {
      setLoading(false)
    }
  }
  
  return (
    <div>
      {loading && <div>Buscando...</div>}
      {error && <div className="error">{error}</div>}
      {/* ... */}
    </div>
  )
}
```

---

## Roadmap Futuro

### Fase 2 (Q2 2026)

#### Backend

- [ ] **Redis para cache**
  - Cache de embeddings (reduce llamadas a OpenAI)
  - Cache de queries frecuentes
  - TTL configurable

- [ ] **Rate Limiting**
  - Por IP: 10 req/min
  - Por API key (si se añade auth)

- [ ] **Autenticación JWT**
  - Login/registro
  - API keys para developers

- [ ] **Monitoreo**
  - Prometheus + Grafana
  - OpenTelemetry para tracing
  - Logs estructurados (JSON)

#### Frontend

- [ ] **Dashboard Completo**
  - Estadísticas de uso
  - Métricas de precisión
  - Gráficos de similitud

- [ ] **Testing Automatizado**
  - 50+ casos de prueba
  - CI/CD con GitHub Actions
  - Coverage > 80%

#### Base de Datos

- [ ] **Optimizaciones**
  - Índices adicionales
  - Particionamiento por fecha
  - Replicación (master-slave)

### Fase 3 (Q3 2026)

- [ ] **Eventos Reales**
  - Integración con APIs de eventos
  - Web scraping de fuentes
  - Actualización automática

- [ ] **Personalización**
  - Preferencias de usuario
  - Historial de búsquedas
  - Recomendaciones personalizadas

- [ ] **Notificaciones**
  - Email/SMS cuando hay nuevos eventos
  - Push notifications (PWA)

---

## Conclusión

Esta guía cubre los aspectos principales del desarrollo en Events Query API. Para más detalles:

- **Arquitectura:** [`ARCHITECTURE.md`](ARCHITECTURE.md)
- **Troubleshooting:** [`TROUBLESHOOTING.md`](TROUBLESHOOTING.md)
- **Quick Start:** [`QUICKSTART.md`](QUICKSTART.md)

**Happy coding! 🚀**