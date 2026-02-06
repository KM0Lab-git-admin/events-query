# 📘 Propuesta API REST + Swagger - Events Query

**Fecha:** 2026-02-06  
**Versión:** 1.0  
**Para:** Comunicación entre Frontend React Externo y Backend

---

## 🎯 Resumen Ejecutivo

### Estado Actual
✅ **La API REST ya está implementada** con FastAPI  
✅ **Swagger ya está configurado** y accesible en `/docs`  
✅ **Modelos Pydantic ya definidos** con validación automática  
✅ **CORS ya configurado** para permitir peticiones desde cualquier origen  

### Lo Que Falta
❌ **Documentación Swagger mejorada** con ejemplos completos  
❌ **Configuración CORS específica** para `km0lab.com`  
❌ **Versionado de API** (actualmente sin `/v1/`)  
❌ **Autenticación** (actualmente pública)  
❌ **Rate limiting** (sin límites)  

---

## 📊 Análisis del Código Actual

### Endpoint Principal: `POST /query`

**Ubicación:** `app/api/routes.py` líneas 30-86

#### Request Actual
```json
{
  "pregunta": "¿Qué hacer este fin de semana?",
  "cp_usuario": "08380",
  "debug": false
}
```

**Validaciones:**
- `pregunta`: string, 3-500 caracteres, requerido
- `cp_usuario`: string, 5 dígitos, requerido
- `debug`: boolean, opcional (default: false)

#### Response Actual
```json
{
  "respuesta_texto": "He encontrado 5 eventos para ti este fin de semana...",
  "eventos": [
    {
      "id_unico_evento": "c65f6d2e7e8064a276021c20306592bb98c723726fec4451e4f0b48e7e8600e",
      "titulo": "Cuentacuentos en la biblioteca - Canet de Mar",
      "descripcion_corta": "Sesión de cuentacuentos para niños...",
      "descripcion_larga": "Actividad familiar donde se narran cuentos...",
      "cp_evento": "08360",
      "poblacion_nombre": "Canet de Mar",
      "lugar_nombre": "Biblioteca Municipal",
      "direccion_completa": "Carrer de la Biblioteca, 1",
      "fecha_inicio": "2026-01-26",
      "fecha_fin": "2026-01-26",
      "hora_inicio": "17:30:00",
      "hora_fin": "18:30:00",
      "es_gratuito": false,
      "precio_euros": 26.95,
      "categorias": ["Infantil", "Cultura"],
      "tags": ["infantil", "familia", "educativo", "cuentacuentos", "biblioteca"],
      "url_evento": "https://example.com/evento/123",
      "url_imagen": "https://example.com/imagen.jpg",
      "distancia_km": 2.5,
      "similitud_score": 0.85
    }
  ],
  "total": 5,
  "idioma_respuesta": "es",
  "debug_info": {
    "parametros_extraidos": {
      "idioma": "es",
      "fechas": [],
      "fecha_inicio": null,
      "fecha_fin": null,
      "radio_km": 20,
      "categorias": [],
      "conceptos": ["fin de semana"],
      "es_gratuito": null,
      "precio_max": null
    },
    "codigos_postales": ["08380", "08370", "08397", "17300"],
    "sql_query": "SELECT ...",
    "sql_params": ["es", "es", ...],
    "eventos_pre_filtrado": 50,
    "eventos_post_semantica": 10,
    "analisis_detallado": [...]
  }
}
```

**Campos del Evento (Modelo `Evento`):**
- ✅ `id_unico_evento`: string (hash único)
- ✅ `titulo`: string (en idioma detectado)
- ✅ `descripcion_corta`: string
- ✅ `descripcion_larga`: string
- ✅ `cp_evento`: string (5 dígitos)
- ✅ `poblacion_nombre`: string
- ✅ `lugar_nombre`: string
- ✅ `direccion_completa`: string
- ✅ **`fecha_inicio`**: date (ISO 8601: YYYY-MM-DD) ⭐
- ✅ **`fecha_fin`**: date (ISO 8601: YYYY-MM-DD) ⭐
- ✅ **`hora_inicio`**: string (HH:MM:SS) ⭐
- ✅ **`hora_fin`**: string (HH:MM:SS) ⭐
- ✅ `es_gratuito`: boolean
- ✅ `precio_euros`: float
- ✅ `categorias`: array de strings
- ✅ `tags`: array de strings
- ✅ `url_evento`: string (URL)
- ✅ `url_imagen`: string (URL)
- ✅ `distancia_km`: float
- ✅ `similitud_score`: float (0.0-1.0)

**Nota:** ✅ **Horarios están incluidos** (fecha_inicio, fecha_fin, hora_inicio, hora_fin)

---

### Detección Automática de Idioma

**Ubicación:** `app/services/ai_service.py`

El sistema **YA detecta automáticamente el idioma** de la pregunta:
- Analiza la pregunta con OpenAI
- Detecta si es español (`es`) o catalán (`ca`)
- Devuelve respuesta en el mismo idioma
- **NO es necesario** enviar `idioma` en el request

**Ejemplo:**
```json
// Request
{
  "pregunta": "Què puc fer aquest cap de setmana?",
  "cp_usuario": "08380"
}

// Response
{
  "respuesta_texto": "He trobat 5 esdeveniments per a tu aquest cap de setmana...",
  "idioma_respuesta": "ca"
}
```

---

## 🏗️ Propuesta de Mejoras

### 1. Swagger/OpenAPI Mejorado

#### Estado Actual
✅ Swagger ya está activo en `/docs`  
✅ Modelos Pydantic generan esquemas automáticamente  
✅ Ejemplos básicos en algunos campos  

#### Mejoras Propuestas
- ✅ Añadir **ejemplos completos** de request/response
- ✅ Añadir **descripciones detalladas** en cada campo
- ✅ Añadir **códigos de error** con ejemplos
- ✅ Añadir **tags** para agrupar endpoints
- ✅ Añadir **metadata** (contacto, licencia, términos)

---

### 2. CORS Específico para `km0lab.com`

#### Estado Actual
```python
allow_origins=["*"]  # Permite cualquier origen
```

#### Propuesta
```python
allow_origins=[
    "https://km0lab.com",
    "https://www.km0lab.com",
    "http://localhost:3000",  # Para desarrollo
    "http://localhost:5173"   # Para Vite dev server
]
```

---

### 3. Versionado de API

#### Estado Actual
```
POST /query
GET /health
GET /events/simple
GET /events/list
```

#### Propuesta
```
POST /api/v1/query
GET /api/v1/health
GET /api/v1/events/simple
GET /api/v1/events/list
```

**Ventajas:**
- Permite evolucionar la API sin romper clientes existentes
- Estándar de la industria
- Facilita deprecación de versiones antiguas

---

### 4. Autenticación (Opcional)

#### Opción A: Sin Autenticación (Actual)
✅ Más simple  
✅ Más rápido de integrar  
❌ Sin control de uso  
❌ Sin límites por usuario  

#### Opción B: API Key
```
POST /api/v1/query
Headers:
  X-API-Key: abc123...
```

✅ Simple de implementar  
✅ Control de uso por cliente  
❌ Menos seguro que JWT  

#### Opción C: JWT Token
```
POST /api/v1/query
Headers:
  Authorization: Bearer eyJhbGc...
```

✅ Más seguro  
✅ Permite expiración  
❌ Más complejo  

**Recomendación:** Empezar sin autenticación (Opción A) y añadir API Key (Opción B) si es necesario.

---

### 5. Rate Limiting

#### Propuesta
```
100 requests/minuto por IP
1000 requests/día por IP
```

**Implementación:** Middleware con `slowapi` o `fastapi-limiter`

---

## 📋 Endpoints Propuestos

### Endpoint 1: Búsqueda de Eventos (Principal)

```
POST /api/v1/query
Content-Type: application/json
```

**Request:**
```json
{
  "pregunta": "¿Actividades relacionadas con comida?",
  "cp_usuario": "08380",
  "debug": false
}
```

**Response 200 OK:**
```json
{
  "respuesta_texto": "He encontrado 3 eventos relacionados con gastronomía...",
  "eventos": [
    {
      "id_unico_evento": "abc123...",
      "titulo": "Cata de vinos y quesos - Malgrat de Mar",
      "descripcion_corta": "Degustación de vinos locales...",
      "descripcion_larga": "Actividad gastronómica donde podrás degustar...",
      "cp_evento": "08380",
      "poblacion_nombre": "Malgrat de Mar",
      "lugar_nombre": "Centro Cultural",
      "direccion_completa": "Carrer Major, 10",
      "fecha_inicio": "2026-02-15",
      "fecha_fin": "2026-02-15",
      "hora_inicio": "19:00:00",
      "hora_fin": "21:00:00",
      "es_gratuito": false,
      "precio_euros": 15.50,
      "categorias": ["Gastronomía", "Ocio"],
      "tags": ["gastronomía", "vinos", "quesos", "degustación", "cata"],
      "url_evento": "https://example.com/cata-vinos",
      "url_imagen": "https://example.com/cata.jpg",
      "distancia_km": 0.5,
      "similitud_score": 0.85
    }
  ],
  "total": 3,
  "idioma_respuesta": "es"
}
```

**Response 400 Bad Request:**
```json
{
  "error": "validation_error",
  "message": "Código postal inválido",
  "detail": "El código postal debe tener 5 dígitos",
  "timestamp": "2026-02-06T10:30:00Z"
}
```

**Response 500 Internal Server Error:**
```json
{
  "error": "internal_server_error",
  "message": "Error interno del servidor",
  "timestamp": "2026-02-06T10:30:00Z"
}
```

---

### Endpoint 2: Health Check

```
GET /api/v1/health
```

**Response 200 OK:**
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "timestamp": "2026-02-06T10:30:00Z",
  "checks": {
    "database": "healthy",
    "openai": "configured",
    "api": "healthy"
  }
}
```

---

### Endpoint 3: Listar Eventos (Simple)

```
GET /api/v1/events/simple
```

**Response 200 OK:**
```json
{
  "eventos": [
    {
      "id": "abc123...",
      "titulo_es": "Cuentacuentos en la biblioteca",
      "titulo_cat": "Contacontes a la biblioteca",
      "cp": "08380",
      "poblacion": "Malgrat de Mar",
      "es_gratuito": false,
      "precio": 5.0,
      "fecha": "2026-02-15",
      "hora": "17:30:00",
      "categorias": "Infantil, Cultura"
    }
  ],
  "total": 125
}
```

---

### Endpoint 4: Listar Eventos (Con Filtros)

```
GET /api/v1/events/list?poblacion=Malgrat%20de%20Mar&categoria=gastronomia&es_gratuito=true&limit=20
```

**Parámetros:**
- `poblacion`: string (opcional)
- `categoria`: string (opcional, slug)
- `tipo_organizador`: string (opcional: PUBLICO, PRIVADO, ASOCIACION)
- `tags`: string (opcional, búsqueda en tags)
- `fecha_desde`: date (opcional, YYYY-MM-DD)
- `fecha_hasta`: date (opcional, YYYY-MM-DD)
- `es_gratuito`: boolean (opcional)
- `es_recurrente`: boolean (opcional)
- `limit`: integer (opcional, default: 50, max: 200)
- `offset`: integer (opcional, default: 0)

**Response 200 OK:**
```json
{
  "eventos": [...],
  "total": 15,
  "limit": 20,
  "offset": 0
}
```

---

## 🔧 Configuración CORS Detallada

### Actual
```python
allow_origins=["*"]
allow_credentials=True
allow_methods=["*"]
allow_headers=["*"]
```

### Propuesta para Producción
```python
allow_origins=[
    "https://km0lab.com",
    "https://www.km0lab.com"
]
allow_credentials=True
allow_methods=["GET", "POST", "OPTIONS"]
allow_headers=[
    "Content-Type",
    "Authorization",
    "X-API-Key"
]
```

### Propuesta para Desarrollo
```python
allow_origins=[
    "https://km0lab.com",
    "https://www.km0lab.com",
    "http://localhost:3000",
    "http://localhost:5173"
]
allow_credentials=True
allow_methods=["*"]
allow_headers=["*"]
```

---

## 📚 Documentación Swagger Mejorada

### Metadata Propuesta

```python
app = FastAPI(
    title="Events Query API",
    version="1.0.0",
    description="""
    API REST para búsqueda inteligente de eventos locales usando lenguaje natural.
    
    ## Características
    
    * **Búsqueda en lenguaje natural** - Pregunta como hablarías normalmente
    * **Detección automática de idioma** - Español y catalán
    * **Búsqueda semántica** - Encuentra eventos relevantes aunque no contengan las palabras exactas
    * **Análisis detallado** - Modo debug para entender cómo funciona la búsqueda
    
    ## Poblaciones Soportadas
    
    * Malgrat de Mar (08380)
    * Blanes (17300)
    
    ## Ejemplos de Preguntas
    
    * "¿Qué hacer este fin de semana?"
    * "Actividades para niños"
    * "Eventos gastronómicos"
    * "Què puc fer aquest cap de setmana?" (catalán)
    """,
    contact={
        "name": "KM0Lab",
        "url": "https://km0lab.com",
        "email": "info@km0lab.com"
    },
    license_info={
        "name": "Propietario",
        "url": "https://km0lab.com/license"
    },
    docs_url="/docs",
    redoc_url="/redoc",
    openapi_url="/openapi.json"
)
```

---

## 🎯 Ejemplo de Integración desde React

### Código Frontend (React)

```javascript
// api/eventsApi.js
const API_BASE_URL = 'https://api.km0lab.com/api/v1';

export async function buscarEventos(pregunta, codigoPostal, debug = false) {
  const response = await fetch(`${API_BASE_URL}/query`, {
    method: 'POST',
    headers: {
      'Content-Type': 'application/json',
      // Si usas API Key:
      // 'X-API-Key': 'tu-api-key'
    },
    body: JSON.stringify({
      pregunta: pregunta,
      cp_usuario: codigoPostal,
      debug: debug
    })
  });

  if (!response.ok) {
    const error = await response.json();
    throw new Error(error.message || 'Error en la búsqueda');
  }

  return await response.json();
}

// Uso en componente
import { buscarEventos } from './api/eventsApi';

function BuscadorEventos() {
  const [pregunta, setPregunta] = useState('');
  const [eventos, setEventos] = useState([]);
  const [loading, setLoading] = useState(false);

  const handleBuscar = async () => {
    setLoading(true);
    try {
      const resultado = await buscarEventos(pregunta, '08380');
      setEventos(resultado.eventos);
      console.log(resultado.respuesta_texto);
    } catch (error) {
      console.error('Error:', error);
    } finally {
      setLoading(false);
    }
  };

  return (
    <div>
      <input 
        value={pregunta}
        onChange={(e) => setPregunta(e.target.value)}
        placeholder="¿Qué quieres hacer?"
      />
      <button onClick={handleBuscar} disabled={loading}>
        {loading ? 'Buscando...' : 'Buscar'}
      </button>
      
      {eventos.map(evento => (
        <div key={evento.id_unico_evento}>
          <h3>{evento.titulo}</h3>
          <p>{evento.descripcion_corta}</p>
          <p>📅 {evento.fecha_inicio} {evento.hora_inicio}</p>
          <p>📍 {evento.lugar_nombre}, {evento.poblacion_nombre}</p>
          <p>💰 {evento.es_gratuito ? 'Gratis' : `${evento.precio_euros}€`}</p>
        </div>
      ))}
    </div>
  );
}
```

---

## ✅ Resumen de Cambios Necesarios

### Cambios Mínimos (Para Empezar Ya)
1. ✅ **Configurar CORS** para `km0lab.com`
2. ✅ **Mejorar documentación Swagger** con ejemplos completos
3. ✅ **Añadir metadata** (contacto, licencia)

### Cambios Recomendados (Corto Plazo)
4. ✅ **Añadir versionado** (`/api/v1/`)
5. ✅ **Añadir rate limiting** (100 req/min)
6. ✅ **Mejorar manejo de errores** con códigos específicos

### Cambios Opcionales (Largo Plazo)
7. ⚠️ **Añadir autenticación** (API Key o JWT)
8. ⚠️ **Añadir analytics** (tracking de uso)
9. ⚠️ **Añadir caché** (Redis para respuestas frecuentes)

---

## 🔗 URLs de Acceso

### Desarrollo (Local)
- **API:** http://localhost:8000
- **Swagger UI:** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc
- **OpenAPI JSON:** http://localhost:8000/openapi.json

### Producción (Propuesta)
- **API:** https://api.km0lab.com
- **Swagger UI:** https://api.km0lab.com/docs
- **ReDoc:** https://api.km0lab.com/redoc
- **OpenAPI JSON:** https://api.km0lab.com/openapi.json

---

## ❓ Preguntas Pendientes

1. **¿Necesitas autenticación?** (API Key, JWT, o pública)
2. **¿Necesitas rate limiting?** (límites de peticiones)
3. **¿Quieres versionado de API?** (`/api/v1/` vs `/`)
4. **¿Dominio de producción?** (api.km0lab.com, km0lab.com/api, otro)
5. **¿Necesitas otros endpoints?** (ej: detalle de evento por ID)

---

## 🎯 Recomendación Final

### Opción A: Mínima (Empezar Ya)
- Configurar CORS para `km0lab.com`
- Mejorar documentación Swagger
- **Tiempo:** 30 minutos

### Opción B: Recomendada (Producción)
- Todo lo de Opción A
- Añadir versionado (`/api/v1/`)
- Añadir rate limiting
- Mejorar manejo de errores
- **Tiempo:** 2 horas

### Opción C: Completa (Enterprise)
- Todo lo de Opción B
- Añadir autenticación (API Key)
- Añadir analytics
- Añadir caché
- **Tiempo:** 4-6 horas

---

**¿Qué opción prefieres? ¿Alguna pregunta o ajuste a la propuesta?**
