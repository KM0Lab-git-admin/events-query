# Events Query API - Fase 1 (MVP)

API REST para búsqueda de eventos usando lenguaje natural con inteligencia artificial.

> **Estado / integración real.** Este repositorio es el snapshot **Fase 1
> (MVP)**: expone `POST /query` y `GET /health`. El servicio desplegado que
> consume la app KM0 LAB (host `eventquery.*.km0lab.com`) ha crecido desde
> entonces a una **API versionada `/api/v1/*`** con eventos filtrables
> (`/api/v1/events`, `/api/v1/events/today`, `/api/v1/events/{id}`,
> `/api/v1/query`) y **noticias municipales** (`/api/v1/news`). Si trabajas
> contra la versión desplegada, contrasta el contrato con `services/eventsApi.ts`
> y `services/newsApi.ts` del repo `km0lab`. Los documentos de diseño previos a
> la implementación están en [`ReadMes/`](ReadMes/README.md).

## 🎯 Características

- **Búsqueda en lenguaje natural**: Pregunta en español o catalán
- **IA integrada**: OpenAI GPT-4.1-mini para extracción de parámetros y respuestas
- **Búsqueda semántica**: Embeddings para encontrar eventos relevantes
- **Búsqueda geográfica**: Filtrado por código postal y radio en kilómetros
- **Bilingüe**: Soporte nativo para español y catalán
- **Async/Await**: Arquitectura asíncrona con aiomysql
- **Performance**: < 3 segundos de respuesta garantizado
- **Documentación Swagger**: API docs automática en `/docs`

## 🛠️ Stack Tecnológico

### Backend
- **FastAPI 0.115**: Framework web moderno y rápido
- **ORJSONResponse**: Serialización JSON optimizada
- **Pydantic 2.x**: Validación de datos
- **Uvicorn**: Servidor ASGI

### Base de Datos
- **MySQL 8.0**: Base de datos relacional
- **aiomysql**: Driver async con connection pooling

### Inteligencia Artificial
- **OpenAI GPT-4.1-mini**: Extracción de parámetros y respuestas naturales
- **text-embedding-3-small**: Búsqueda semántica
- **tenacity**: Retries con backoff exponencial

### Testing
- **pytest**: Tests unitarios
- **pytest-asyncio**: Tests asíncronos
- **httpx**: Tests de API

## 📋 Requisitos

- Python 3.11+
- MySQL 8.0+
- OpenAI API Key

## 🚀 Instalación

### 1. Clonar el repositorio

```bash
git clone <repo_url>
cd events-api
```

### 2. Crear entorno virtual

```bash
python3.11 -m venv venv
source venv/bin/activate  # En Windows: venv\Scripts\activate
```

### 3. Instalar dependencias

```bash
pip install -r requirements.txt
```

### 4. Configurar variables de entorno

```bash
cp .env.example .env
# Editar .env con tus credenciales
```

**Variables requeridas:**
- `DB_HOST`, `DB_PORT`, `DB_USER`, `DB_PASSWORD`, `DB_NAME`
- `OPENAI_API_KEY`

### 5. Crear base de datos

```bash
# Conectar a MySQL
mysql -u root -p

# Crear base de datos
CREATE DATABASE events_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'events_user'@'localhost' IDENTIFIED BY 'events_password';
GRANT ALL PRIVILEGES ON events_db.* TO 'events_user'@'localhost';
FLUSH PRIVILEGES;
EXIT;

# Ejecutar esquema
mysql -u events_user -p events_db < scripts/schema.sql
```

### 6. Generar datos fake

```bash
python scripts/generate_fake_data.py
```

Esto generará:
- 5 poblaciones (Malgrat de Mar, Calella, Canet de Mar, Pineda de Mar, Blanes)
- 125 eventos (25 por población)
- 8 categorías
- Datos bilingües (español/catalán)

### 7. Ejecutar la API

```bash
# Desarrollo (con reload)
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# O usando el script
python -m app.main
```

La API estará disponible en: http://localhost:8000

## 📖 Documentación

### Swagger UI (interactiva)
http://localhost:8000/docs

### ReDoc
http://localhost:8000/redoc

### OpenAPI JSON
http://localhost:8000/openapi.json

## 🔍 Uso

### Endpoint principal: POST /query

**Request:**
```json
{
  "pregunta": "¿Qué hacer este fin de semana en mi población?",
  "cp_usuario": "08380",
  "debug": false
}
```

**Response:**
```json
{
  "respuesta_texto": "He encontrado 5 eventos para ti este fin de semana en Malgrat de Mar...",
  "eventos": [
    {
      "id_unico_evento": "abc123...",
      "titulo": "Cineclub: Clásicos del cine",
      "descripcion_corta": "Evento de cultura en Malgrat de Mar",
      "cp_evento": "08380",
      "poblacion_nombre": "Malgrat de Mar",
      "fecha_inicio": "2026-01-26",
      "hora_inicio": "21:00:00",
      "es_gratuito": false,
      "precio_euros": 6.00,
      "categorias": ["Cultura"],
      "tags": ["#cine", "#clasicos", "#cultura"],
      "distancia_km": 0.0,
      "similitud_score": 0.85
    }
  ],
  "total": 5,
  "idioma_respuesta": "es"
}
```

### Ejemplos de preguntas

**Español:**
- "¿Qué hacer este fin de semana?"
- "Eventos gratuitos para niños"
- "Actividades al aire libre cerca de mi"
- "Conciertos de música en un radio de 20 kilómetros"

**Catalán:**
- "Què fer aquest cap de setmana?"
- "Esdeveniments gratuïts per a nens"
- "Activitats a l'aire lliure prop meu"
- "Concerts de música en un radi de 20 quilòmetres"

### Health Check: GET /health

```bash
curl http://localhost:8000/health
```

**Response:**
```json
{
  "status": "healthy",
  "version": "1.0.0",
  "timestamp": "2026-01-25T10:30:00",
  "checks": {
    "database": "healthy",
    "openai": "configured",
    "api": "healthy"
  }
}
```

## 🧪 Testing

```bash
# Ejecutar todos los tests
pytest

# Con coverage
pytest --cov=app --cov-report=html

# Tests específicos
pytest tests/test_api.py
pytest tests/test_services.py
```

## 📁 Estructura del Proyecto

```
events-api/
├── app/
│   ├── __init__.py
│   ├── main.py              # Aplicación FastAPI principal
│   ├── config.py            # Configuración (env vars)
│   ├── api/
│   │   ├── __init__.py
│   │   └── routes.py        # Endpoints de la API
│   ├── models/
│   │   ├── __init__.py
│   │   └── schemas.py       # Modelos Pydantic
│   └── services/
│       ├── __init__.py
│       ├── database.py      # Servicio de BD (aiomysql)
│       ├── ai_service.py    # Servicio de OpenAI
│       ├── query_builder.py # Constructor de queries SQL
│       └── events_service.py # Servicio principal de búsqueda
├── scripts/
│   ├── schema.sql           # Esquema de BD
│   └── generate_fake_data.py # Generador de datos fake
├── tests/
│   └── (tests aquí)
├── .env.example             # Ejemplo de variables de entorno
├── requirements.txt         # Dependencias Python
└── README.md               # Este archivo
```

## ⚡ Performance

**Objetivo:** < 3 segundos de respuesta

**Performance actual (Fase 1):**
```
Extracción parámetros (IA):    500ms
Cálculo geográfico:             50ms
Pre-filtrado SQL:              120ms
Búsqueda semántica:            130ms
Respuesta natural (IA):        500ms
Serialización (ORJSONResponse): 30ms
Otros:                         100ms
──────────────────────────────────
TOTAL:                        1430ms ✅
```

**Throughput:** ~10 req/s (single instance)

## 🔐 Seguridad

- ✅ SQL parametrizado (previene SQL injection)
- ✅ Validación Pydantic en todos los inputs
- ✅ Connection pooling (previene agotamiento de conexiones)
- ✅ Timeouts configurables para OpenAI
- ✅ Retries con backoff exponencial

## 🐛 Troubleshooting

### Error: "Database pool not initialized"
- Asegúrate de que MySQL esté corriendo
- Verifica las credenciales en `.env`
- Comprueba que la base de datos existe

### Error: "OpenAI API key not configured"
- Añade `OPENAI_API_KEY` en `.env`
- Verifica que la API key sea válida

### Performance lenta
- Activa modo debug: `"debug": true` en el request
- Revisa los logs para identificar el cuello de botella
- Verifica que hay índices en la BD

## 📝 Logs

Los logs se escriben en stdout con el siguiente formato:
```
2026-01-25 10:30:00 - app.services.events_service - INFO - Búsqueda iniciada: pregunta='...', cp=08380
```

Nivel de log configurable en `.env`:
```
LOG_LEVEL=INFO  # DEBUG, INFO, WARNING, ERROR
```

## 🚀 Próximos Pasos (Fase 2)

- [ ] Redis para cache de embeddings
- [ ] Rate limiting
- [ ] OpenTelemetry + Prometheus
- [ ] Logs estructurados
- [ ] Docker Compose
- [ ] CI/CD

## 📄 Licencia

[Tu licencia aquí]

## 👥 Autores

[Tu nombre aquí]

## 🙏 Agradecimientos

- OpenAI por la API de IA
- FastAPI por el excelente framework
- Comunidad Python

---

**Versión:** 1.0.0 (Fase 1 - MVP)  
**Fecha:** Enero 2026
