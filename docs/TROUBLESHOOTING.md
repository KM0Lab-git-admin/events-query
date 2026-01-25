# 🔧 Troubleshooting - Events Query API

**Guía completa para solucionar problemas comunes**

---

## 📋 Tabla de Contenidos

1. [Problemas de Setup](#problemas-de-setup)
2. [Problemas de Búsqueda](#problemas-de-búsqueda)
3. [Análisis No Se Muestra](#análisis-no-se-muestra)
4. [Eventos No Encontrados](#eventos-no-encontrados)
5. [Errores Comunes](#errores-comunes)
6. [Logs y Debugging](#logs-y-debugging)
7. [FAQ](#faq)

---

## Problemas de Setup

### Error: "Database pool not initialized"

**Síntoma:**

```
ERROR - app.services.database - Database pool not initialized
```

**Causas Posibles:**

1. MySQL no está corriendo
2. Credenciales incorrectas en `.env`
3. Base de datos no existe
4. Puerto incorrecto

**Solución:**

```bash
# 1. Verificar que MySQL está corriendo
sudo systemctl status mysql  # Linux
brew services list           # macOS

# Si no está corriendo:
sudo systemctl start mysql   # Linux
brew services start mysql    # macOS

# 2. Verificar credenciales en .env
cat .env | grep DB_

# Debería mostrar:
# DB_HOST=localhost
# DB_PORT=3306
# DB_USER=events_user
# DB_PASSWORD=events_password
# DB_NAME=events_db

# 3. Probar conexión manual
mysql -u events_user -p events_db

# Si falla, recrear usuario:
mysql -u root -p
CREATE USER 'events_user'@'localhost' IDENTIFIED BY 'events_password';
GRANT ALL PRIVILEGES ON events_db.* TO 'events_user'@'localhost';
FLUSH PRIVILEGES;
EXIT;

# 4. Verificar que la base de datos existe
mysql -u events_user -p
SHOW DATABASES;

# Si no existe events_db:
CREATE DATABASE events_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
EXIT;

# 5. Ejecutar esquema
mysql -u events_user -p events_db < SQL/SCHEMA_SQL_FINAL.sql

# 6. Reiniciar backend
# Ctrl+C en la terminal del backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

---

### Error: "OpenAI API key not configured"

**Síntoma:**

```
ERROR - app.services.ai_service - OpenAI API key not configured
```

**Causa:** Falta `OPENAI_API_KEY` en `.env`

**Solución:**

```bash
# 1. Verificar que existe
cat .env | grep OPENAI_API_KEY

# Si no existe o está vacío:
nano .env  # O tu editor favorito

# Añadir:
OPENAI_API_KEY=sk-tu-api-key-aqui

# 2. Verificar que la API key es válida
curl https://api.openai.com/v1/models \
  -H "Authorization: Bearer sk-tu-api-key-aqui"

# Debería retornar lista de modelos

# 3. Reiniciar backend
# Ctrl+C
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

---

### Error: "Module not found"

**Síntoma:**

```
ModuleNotFoundError: No module named 'fastapi'
```

**Causa:** Dependencias no instaladas o entorno virtual no activado

**Solución:**

```bash
# 1. Verificar que el entorno virtual está activado
which python3.11
# Debería mostrar: /ruta/a/events-query/venv/bin/python3.11

# Si no está activado:
source venv/bin/activate  # Linux/macOS
venv\Scripts\activate     # Windows

# 2. Instalar dependencias
pip install -r requirements.txt

# 3. Verificar instalación
pip list | grep fastapi
# Debería mostrar: fastapi 0.115.x

# 4. Si persiste, recrear entorno virtual
deactivate
rm -rf venv
python3.11 -m venv venv
source venv/bin/activate
pip install -r requirements.txt
```

---

### Error: Frontend no arranca

**Síntoma:**

```
Error: Cannot find module 'vite'
```

**Causa:** Dependencias del frontend no instaladas

**Solución:**

```bash
cd frontend

# 1. Verificar que pnpm está instalado
pnpm --version

# Si no está instalado:
npm install -g pnpm

# 2. Instalar dependencias
pnpm install

# 3. Si persiste, limpiar cache
rm -rf node_modules
rm pnpm-lock.yaml
pnpm install

# 4. Iniciar frontend
pnpm dev
```

---

## Problemas de Búsqueda

### Performance Lenta (> 5 segundos)

**Síntoma:** Las búsquedas tardan más de 5 segundos.

**Diagnóstico:**

```bash
# Activar modo debug
curl -X POST "http://localhost:8000/query" \
  -H "Content-Type: application/json" \
  -d '{
    "pregunta": "¿Qué hacer este fin de semana?",
    "cp_usuario": "08380",
    "debug": true
  }'

# Revisar debug_info en la respuesta
# Buscar tiempos de cada paso
```

**Causas Posibles:**

1. **Primera llamada a OpenAI** (normal: ~3s, siguientes ~1.5s)
2. **Sin índices en BD**
3. **Demasiados eventos en pre-filtrado**
4. **Debug mode activado** (añade ~2s)

**Solución:**

```bash
# 1. Verificar índices en BD
mysql -u events_user -p events_db

SHOW INDEX FROM EVENTOS_MASTER;
SHOW INDEX FROM EVENTO_HORARIOS;
SHOW INDEX FROM CODIGOS_POSTALES;

# Si faltan índices, añadirlos:
CREATE INDEX idx_cp_evento ON EVENTOS_MASTER(CP_Evento);
CREATE INDEX idx_estado ON EVENTOS_MASTER(Estado);
CREATE INDEX idx_fecha_inicio ON EVENTO_HORARIOS(Fecha_Inicio);
CREATE INDEX idx_cp ON CODIGOS_POSTALES(CP);

# 2. Limitar eventos en pre-filtrado
# Editar app/services/query_builder.py
# Cambiar LIMIT 50 a LIMIT 30

# 3. Desactivar debug mode en producción
# En el request, poner "debug": false
```

---

### Error: "Rate limit exceeded"

**Síntoma:**

```
ERROR - openai.RateLimitError: Rate limit exceeded
```

**Causa:** Demasiadas llamadas a OpenAI en poco tiempo.

**Solución:**

```bash
# 1. Esperar 1 minuto y reintentar

# 2. Verificar límites de tu cuenta OpenAI
# https://platform.openai.com/account/limits

# 3. Implementar cache (TODO: Redis)
# Por ahora, reducir frecuencia de requests

# 4. El sistema tiene retries automáticos (3 intentos)
# Debería recuperarse solo
```

---

### Error: "Timeout"

**Síntoma:**

```
ERROR - openai.Timeout: Request timed out
```

**Causa:** OpenAI no responde en 30 segundos.

**Solución:**

```bash
# 1. Verificar conexión a internet
ping api.openai.com

# 2. Verificar estado de OpenAI
# https://status.openai.com

# 3. Aumentar timeout (si es necesario)
# Editar app/services/ai_service.py
# Cambiar timeout=30 a timeout=60

# 4. El sistema tiene retries automáticos
# Debería recuperarse solo
```

---

## Análisis No Se Muestra

### Síntoma: No aparece la sección "Análisis Detallado"

**Diagnóstico:**

```bash
# 1. Abrir consola del navegador (F12)
# 2. Buscar logs:
#    - "DEBUG: analisis_detallado = ..."
#    - "DEBUG App: Recibiendo análisis..."
#    - "DEBUG AnalysisView: Recibiendo analisis..."
```

**Causas Posibles:**

1. **Debug mode no activado**
2. **No hay conceptos extraídos**
3. **Frontend no reiniciado**
4. **Error en backend**

**Solución:**

### Causa 1: Debug Mode No Activado

```jsx
// Verificar en frontend/src/QueryChat.jsx línea ~40
const response = await fetch('/query', {
  method: 'POST',
  headers: {'Content-Type': 'application/json'},
  body: JSON.stringify({
    pregunta,
    cp_usuario: codigoPostal,
    debug: true  // ← Debe ser true
  })
})
```

**Si está en false:**

```bash
cd frontend/src
nano QueryChat.jsx

# Cambiar debug: false a debug: true
# Guardar (Ctrl+O, Enter, Ctrl+X)

# Reiniciar frontend
# Ctrl+C en la terminal del frontend
pnpm dev
```

---

### Causa 2: No Hay Conceptos Extraídos

**Verificar en el JSON de respuesta:**

```json
{
  "debug_info": {
    "parametros_extraidos": {
      "conceptos": []  // ← Vacío
    }
  }
}
```

**Solución:** La pregunta es demasiado genérica. Prueba con:

- ✅ "Actividades relacionadas con comida"
- ✅ "Eventos infantiles"
- ✅ "Conciertos de música"
- ❌ "Eventos" (muy genérico)

---

### Causa 3: Frontend No Reiniciado

```bash
# Reiniciar frontend
cd frontend
# Ctrl+C
pnpm dev

# Limpiar cache del navegador
# Ctrl+Shift+R (hard refresh)
```

---

### Causa 4: Error en Backend

**Revisar logs del backend:**

```bash
# En la terminal del backend, buscar:
ERROR - app.services.analysis_service - ...

# Si hay error, revisar stack trace
# Reportar issue con el error completo
```

---

## Eventos No Encontrados

### Síntoma: "No he encontrado ningún evento que coincida"

**Diagnóstico:**

```bash
# Activar debug mode y revisar:
# 1. parametros_extraidos
# 2. codigos_postales
# 3. sql_query
# 4. eventos_pre_filtrado
# 5. eventos_post_semantica
# 6. analisis_detallado
```

**Causas Posibles:**

1. **Umbral de similitud muy alto**
2. **Tags insuficientes en eventos**
3. **Categoría incorrecta**
4. **Sin embeddings**
5. **CP incorrecto**
6. **Fechas filtran todo**

---

### Causa 1: Umbral de Similitud Muy Alto

**Verificar en `app/services/events_service.py` línea ~152:**

```python
eventos_filtrados = [e for e in eventos_con_score if e['similitud_score'] >= 0.4]
```

**Si el umbral es > 0.4:**

```bash
# Editar app/services/events_service.py
nano app/services/events_service.py

# Buscar línea ~152
# Cambiar >= 0.6 a >= 0.4

# Guardar y reiniciar backend
# Ctrl+C
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**Recomendaciones:**

- **0.3**: Muy permisivo (muchos falsos positivos)
- **0.4**: Balance recomendado ✅
- **0.5**: Estricto (pocos resultados)
- **0.6**: Muy estricto (muy pocos resultados)

---

### Causa 2: Tags Insuficientes

**Verificar en `analisis_detallado`:**

```json
{
  "problemas_detectados": [
    {
      "tipo": "TAGS_INSUFICIENTES",
      "descripcion": "Solo 1 tags con similitud > 0.3"
    }
  ]
}
```

**Solución:** Añadir más tags al evento.

```sql
-- En MySQL
mysql -u events_user -p events_db

-- Ver evento
SELECT ID_Unico_Evento, Titulo_ES, Tags_ES 
FROM EVENTOS_MASTER 
WHERE Titulo_ES LIKE '%Cata de vinos%';

-- Actualizar tags
UPDATE EVENTOS_MASTER 
SET Tags_ES = '["vinos", "quesos", "cata", "comida", "gastronomía", "degustación"]'
WHERE ID_Unico_Evento = 'EVT123';

-- Regenerar embedding (TODO: script automático)
```

---

### Causa 3: Categoría Incorrecta

**Verificar en `analisis_detallado`:**

```json
{
  "problemas_detectados": [
    {
      "tipo": "CATEGORIA_IRRELEVANTE",
      "descripcion": "Categoría 'Cultura' tiene similitud 0.15"
    }
  ],
  "soluciones_propuestas": [
    {
      "tipo": "cambiar_categoria",
      "categoria_sugerida": "Gastronomía"
    }
  ]
}
```

**Solución:** Cambiar categoría del evento.

```sql
-- En MySQL
mysql -u events_user -p events_db

-- Ver categoría actual
SELECT em.ID_Unico_Evento, em.Titulo_ES, c.Nombre_Categoria
FROM EVENTOS_MASTER em
JOIN EVENTO_CATEGORIAS ec ON em.ID_Unico_Evento = ec.ID_Unico_Evento
JOIN CATEGORIAS c ON ec.ID_Categoria = c.ID_Categoria
WHERE em.Titulo_ES LIKE '%Cata de vinos%';

-- Cambiar categoría
-- 1. Obtener ID de nueva categoría
SELECT ID_Categoria FROM CATEGORIAS WHERE Nombre_Categoria = 'Gastronomía';
-- Supongamos que retorna ID_Categoria = 5

-- 2. Actualizar relación
UPDATE EVENTO_CATEGORIAS 
SET ID_Categoria = 5 
WHERE ID_Unico_Evento = 'EVT123';
```

---

### Causa 4: Sin Embeddings

**Verificar en `analisis_detallado`:**

```json
{
  "problemas_detectados": [
    {
      "tipo": "SIN_EMBEDDING",
      "descripcion": "Evento no tiene embedding generado"
    }
  ]
}
```

**Solución:** Generar embedding para el evento.

```python
# TODO: Script automático
# Por ahora, manual:

import asyncio
from app.services.ai_service import AIService

async def generate_embedding_for_event(event_id):
    ai_service = AIService()
    
    # Obtener tags del evento
    query = "SELECT Tags_ES FROM EVENTOS_MASTER WHERE ID_Unico_Evento = %s"
    result = await db.execute_query(query, (event_id,))
    tags = json.loads(result[0]['Tags_ES'])
    
    # Generar embedding
    tags_text = " ".join(tags)
    embedding = await ai_service.generate_embedding(tags_text)
    
    # Guardar en BD
    update_query = "UPDATE EVENTOS_MASTER SET Tags_Embedding_ES = %s WHERE ID_Unico_Evento = %s"
    await db.execute_query(update_query, (json.dumps(embedding), event_id))

# Ejecutar
asyncio.run(generate_embedding_for_event('EVT123'))
```

---

### Causa 5: CP Incorrecto

**Verificar en `debug_info.codigos_postales`:**

```json
{
  "codigos_postales": ["08380"]
}
```

**Si el CP no incluye la población del evento:**

```bash
# Verificar CPs disponibles
mysql -u events_user -p events_db

SELECT DISTINCT CP_Evento, Poblacion_Nombre 
FROM EVENTOS_MASTER 
ORDER BY CP_Evento;

# Usar el CP correcto en la búsqueda
```

---

### Causa 6: Fechas Filtran Todo

**Verificar en `debug_info.sql_query`:**

```sql
WHERE ... AND eh.Fecha_Inicio BETWEEN '2026-01-25' AND '2026-01-26'
```

**Si las fechas son muy restrictivas:**

```bash
# Opción 1: No mencionar fechas en la pregunta
# En lugar de: "¿Qué hacer este fin de semana?"
# Usa: "¿Qué hacer?"

# Opción 2: Usar rango más amplio
# "¿Qué hacer esta semana?"
# "¿Qué hacer este mes?"

# Opción 3: Verificar fechas de eventos en BD
mysql -u events_user -p events_db

SELECT Fecha_Inicio, COUNT(*) 
FROM EVENTO_HORARIOS 
GROUP BY Fecha_Inicio 
ORDER BY Fecha_Inicio;
```

---

## Errores Comunes

### Error: "Decimal - float TypeError"

**Síntoma:**

```
TypeError: unsupported operand type(s) for -: 'Decimal' and 'float'
```

**Causa:** MySQL devuelve `Decimal` para campos numéricos, pero Python espera `float`.

**Solución:** Ya está solucionado en commit `686ad17`. Si persiste:

```python
# Editar app/services/database.py
# Línea ~170

coords = result[0]
return {
    'lat': float(coords['lat']) if coords.get('lat') is not None else None,
    'lng': float(coords['lng']) if coords.get('lng') is not None else None
}
```

---

### Error: "ValidationError"

**Síntoma:**

```
pydantic.ValidationError: 1 validation error for Evento
fecha_inicio
  field required (type=value_error.missing)
```

**Causa:** Campo requerido en modelo Pydantic viene como `None` desde BD.

**Solución:** Ya está solucionado en commit `75f015f`. Si persiste:

```python
# Editar app/models/schemas.py
# Cambiar campo requerido a Optional

from typing import Optional
from datetime import date

class Evento(BaseModel):
    id_unico_evento: str
    titulo: Optional[str] = None  # ← Añadir Optional
    fecha_inicio: Optional[date] = None  # ← Añadir Optional
    ...
```

---

### Error: "Connection pool exhausted"

**Síntoma:**

```
ERROR - aiomysql - Connection pool exhausted
```

**Causa:** Demasiadas conexiones simultáneas.

**Solución:**

```python
# Editar app/services/database.py
# Línea ~25

self.pool = await aiomysql.create_pool(
    minsize=5,
    maxsize=50,  # ← Aumentar de 20 a 50
    ...
)
```

---

## Logs y Debugging

### Activar Logs Detallados

```bash
# Editar .env
LOG_LEVEL=DEBUG  # En lugar de INFO

# Reiniciar backend
# Ctrl+C
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**Logs Disponibles:**

```
2026-01-25 10:30:00 - app.services.events_service - INFO - Búsqueda iniciada: pregunta='...', cp=08380
2026-01-25 10:30:01 - app.services.ai_service - DEBUG - Extrayendo parámetros...
2026-01-25 10:30:01 - app.services.database - DEBUG - Ejecutando query: SELECT ...
2026-01-25 10:30:02 - app.services.events_service - INFO - Eventos encontrados: 10
```

---

### Debugging en Frontend

```bash
# Abrir consola del navegador (F12)
# Buscar logs:
console.log("DEBUG: data.debug_info = ", data.debug_info)
console.log("DEBUG: analisis_detallado = ", analisis_detallado)
console.log("DEBUG App: Recibiendo análisis con", analisis.length, "eventos")
console.log("DEBUG AnalysisView: Recibiendo analisis =", analisis)
```

---

### Debugging en Backend

```python
# Añadir prints en el código
print(f"DEBUG: eventos_raw = {len(eventos_raw)}")
print(f"DEBUG: eventos_filtrados = {len(eventos_filtrados)}")
print(f"DEBUG: similitud_score = {evento['similitud_score']}")

# O usar logging
import logging
logger = logging.getLogger(__name__)

logger.debug(f"Eventos raw: {len(eventos_raw)}")
logger.info(f"Eventos filtrados: {len(eventos_filtrados)}")
logger.error(f"Error: {e}")
```

---

## FAQ

### ¿Por qué la primera búsqueda es lenta?

**Respuesta:** La primera llamada a OpenAI siempre es más lenta (~3s) porque establece la conexión. Las siguientes son más rápidas (~1.5s).

---

### ¿Cómo ajusto el umbral de similitud?

**Respuesta:** Edita `app/services/events_service.py` línea ~152:

```python
eventos_filtrados = [e for e in eventos_con_score if e['similitud_score'] >= 0.4]
#                                                                            ↑
#                                                                    Cambiar aquí
```

Reinicia el backend.

---

### ¿Cómo añado más eventos fake?

**Respuesta:**

```bash
# Editar scripts/generate_fake_data.py
# Cambiar num_events_per_city de 25 a 50

# Ejecutar
python scripts/generate_fake_data.py

# Esto añadirá 125 eventos más (250 total)
```

---

### ¿Cómo limpio la base de datos?

**Respuesta:**

```bash
mysql -u events_user -p events_db

-- Eliminar todos los eventos
DELETE FROM EVENTO_HORARIOS;
DELETE FROM EVENTO_CATEGORIAS;
DELETE FROM EVENTO_ORGANIZADORES;
DELETE FROM EVENTOS_MASTER;

-- Regenerar datos fake
EXIT;
python scripts/generate_fake_data.py
```

---

### ¿Cómo cambio el puerto del backend?

**Respuesta:**

```bash
# En lugar de:
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Usar:
uvicorn app.main:app --reload --host 0.0.0.0 --port 8080

# También actualizar proxy en frontend/vite.config.js:
# proxy: {
#   '/query': 'http://localhost:8080',
#   ...
# }
```

---

### ¿Cómo despliego en producción?

**Respuesta:** Ver roadmap en [`DEVELOPMENT.md`](DEVELOPMENT.md). Por ahora:

```bash
# Backend
uvicorn app.main:app --host 0.0.0.0 --port 8000 --workers 4

# Frontend
cd frontend
pnpm build
# Servir dist/ con nginx o similar
```

---

### ¿Dónde reporto bugs?

**Respuesta:**

1. **GitHub Issues:** https://github.com/KM0Lab-git-admin/events-query/issues
2. **Email:** [tu-email]
3. **Incluir:**
   - Descripción del problema
   - Pasos para reproducir
   - Logs del backend
   - Logs de la consola del navegador
   - Versión del proyecto

---

## Conclusión

Si ninguna de estas soluciones funciona:

1. **Revisa los logs** del backend y frontend
2. **Activa debug mode** para ver más información
3. **Reporta el issue** en GitHub con logs completos

**Documentación adicional:**

- **[🏗️ Arquitectura](ARCHITECTURE.md)**
- **[👨‍💻 Desarrollo](DEVELOPMENT.md)**
- **[🚀 Quick Start](QUICKSTART.md)**

---

**¡Buena suerte! 🚀**
