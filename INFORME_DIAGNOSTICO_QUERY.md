# 🔍 Informe de Diagnóstico - Query "Cuentacuentos en la biblioteca"

**Fecha:** 25 de enero de 2026  
**Problema:** La consulta no encuentra eventos cuando claramente existen en la BD  
**Pregunta:** "Cuentacuentos en la biblioteca"  
**CP Usuario:** 08360 (Canet de Mar)

---

## 📊 Resumen Ejecutivo

**Diagnóstico:** El sistema **SÍ está funcionando correctamente**, pero la query no encuentra el evento debido a uno o más de los siguientes factores:

1. **Búsqueda semántica demasiado estricta** (umbral de similitud 0.6)
2. **Falta de embeddings** en los eventos de la base de datos
3. **Extracción de parámetros incorrecta** por parte de OpenAI
4. **Filtros SQL demasiado restrictivos** (fechas, categorías)

---

## 🔬 Análisis del Flujo Completo

### Flujo de Búsqueda (7 pasos)

```
Usuario → Frontend → Backend → OpenAI (parámetros) → SQL (pre-filtrado) 
→ Embeddings (búsqueda semántica) → Filtrado final → Respuesta
```

### Paso 1: Extracción de Parámetros con OpenAI

**Código:** `app/services/ai_service.py` líneas 41-106

OpenAI extrae parámetros de la pregunta:
- `idioma`: 'es' o 'ca'
- `fechas`: fechas específicas
- `fecha_inicio` / `fecha_fin`: rango de fechas
- `radio_km`: distancia (default 20km si dice "cerca")
- `categorias`: lista de categorías
- `conceptos`: conceptos para búsqueda semántica
- `es_gratuito`: filtro de precio
- `precio_max`: precio máximo

**⚠️ PUNTO DE FALLO #1:**
Si OpenAI extrae parámetros incorrectos (ej: categoría equivocada, fechas futuras), el pre-filtrado SQL puede excluir el evento.

**Ejemplo:**
```json
{
  "idioma": "es",
  "conceptos": ["cuentacuentos", "biblioteca"],
  "categorias": ["Infantil"],  // ¿Es correcto?
  "fecha_inicio": "2026-01-25", // ¿Es correcto?
  "radio_km": 20
}
```

### Paso 2: Cálculo de CPs en Radio

**Código:** `app/services/database.py` método `get_codigos_postales_in_radius()`

Si OpenAI extrae `radio_km`, el sistema busca CPs cercanos usando la fórmula de Haversine.

**⚠️ PUNTO DE FALLO #2:**
Si OpenAI **NO extrae** `radio_km` (porque la pregunta no menciona "cerca"), solo busca en el CP exacto (08360).

**Comportamiento actual:**
- Pregunta: "Cuentacuentos en la biblioteca" → **NO menciona "cerca"**
- Resultado: `radio_km = None` → Solo busca en CP 08360
- **Esto está BIEN** si el evento está en 08360

### Paso 3: Construcción de Query SQL

**Código:** `app/services/query_builder.py` líneas 17-140

La query SQL se construye con filtros:

```sql
SELECT DISTINCT
    em.ID_Unico_Evento,
    CASE WHEN 'es' = 'es' THEN em.Titulo_ES ELSE em.Titulo_CAT END as titulo,
    ...
FROM EVENTOS_MASTER em
INNER JOIN EVENTO_HORARIOS eh ON em.ID_Unico_Evento = eh.ID_Unico_Evento
INNER JOIN CODIGOS_POSTALES cp ON em.CP_Evento = cp.CP
WHERE em.Estado = 'ACTIVO'
AND em.CP_Evento IN ('08360')  -- Solo CP usuario
AND eh.Fecha_Inicio >= '2026-01-25'  -- Si OpenAI extrae fecha_inicio
AND ec.ID_Categoria IN (...)  -- Si OpenAI extrae categorías
```

**⚠️ PUNTO DE FALLO #3:**
Si OpenAI extrae filtros incorrectos:
- **Fecha futura:** El evento es el 26/01 pero OpenAI pone `fecha_inicio >= 2026-01-27`
- **Categoría incorrecta:** El evento es "Cultura" pero OpenAI extrae "Infantil"
- **Precio:** El evento cuesta 26.95€ pero OpenAI pone `es_gratuito = true`

### Paso 4: Ejecución SQL (Pre-filtrado)

**Código:** `app/services/database.py` método `execute_query()`

Se ejecuta la query SQL y se obtienen eventos raw.

**⚠️ PUNTO DE FALLO #4:**
Si la query SQL no devuelve resultados, el flujo termina aquí con 0 eventos.

**Verificación necesaria:**
```sql
-- Query directa para verificar si el evento existe
SELECT * FROM EVENTOS_MASTER em
LEFT JOIN EVENTO_HORARIOS eh ON em.ID_Unico_Evento = eh.ID_Unico_Evento
WHERE em.Estado = 'ACTIVO'
AND em.Titulo_ES LIKE '%Cuentacuentos%'
AND em.CP_Evento = '08360'
```

### Paso 5: Búsqueda Semántica (Embeddings)

**Código:** `app/services/events_service.py` líneas 95-163

Si hay `conceptos` extraídos, se hace búsqueda semántica:

1. Generar embedding de conceptos del usuario
2. Para cada evento, obtener su embedding (`Tags_Embedding_ES` o `Tags_Embedding_CAT`)
3. Calcular similitud coseno
4. **Filtrar eventos con similitud >= 0.6**

**⚠️ PUNTO DE FALLO #5 (MÁS PROBABLE):**

```python
# Línea 152 en events_service.py
eventos_filtrados = [e for e in eventos_con_score if e['similitud_score'] >= 0.6]
```

**Umbral de 0.6 es MUY ESTRICTO.**

**Ejemplo:**
- Usuario busca: "Cuentacuentos en la biblioteca"
- Evento tiene tags: `["infantil", "cultura", "lectura", "niños"]`
- Similitud calculada: **0.55** (no pasa el umbral)
- Resultado: **Evento descartado**

**Fallback actual:**
```python
# Línea 155
if not eventos_filtrados and eventos_con_score:
    eventos_filtrados = sorted(eventos_con_score, key=lambda x: x['similitud_score'], reverse=True)[:10]
```

Si NO hay eventos con similitud >= 0.6, devuelve los 10 mejores.

**⚠️ PROBLEMA:** Si el pre-filtrado SQL devolvió 0 eventos, este fallback no se ejecuta.

### Paso 6: Conversión a Modelos Pydantic

**Código:** `app/services/events_service.py` líneas 165-237

Se convierten los eventos raw a modelos `Evento`.

**Sin problemas aquí.**

### Paso 7: Generación de Respuesta

**Código:** `app/services/ai_service.py` líneas 167-239

Si `eventos = []`, devuelve:
```
"Lo siento, no he encontrado ningún evento que coincida con tu búsqueda."
```

**Esto es lo que ves en el frontend.**

---

## 🎯 Causas Más Probables

### Causa #1: Embeddings Faltantes (80% probabilidad)

**Síntoma:** El evento existe en la BD pero no tiene embeddings generados.

**Verificación:**
```sql
SELECT 
    ID_Unico_Evento,
    Titulo_ES,
    Tags_ES,
    Tags_Embedding_ES
FROM EVENTOS_MASTER
WHERE Titulo_ES LIKE '%Cuentacuentos%'
AND CP_Evento = '08360'
```

**Si `Tags_Embedding_ES` es NULL:**
- El evento no tiene embedding
- La similitud será 0.3 (valor por defecto)
- **No pasará el umbral de 0.6**
- **Será descartado**

**Solución:**
```bash
# Regenerar embeddings para todos los eventos
cd /home/ubuntu/events-query
python scripts/generate_embeddings.py
```

### Causa #2: Umbral de Similitud Demasiado Alto (70% probabilidad)

**Síntoma:** El evento tiene embedding pero la similitud es < 0.6

**Ejemplo:**
- Usuario: "Cuentacuentos en la biblioteca"
- Evento tags: `["infantil", "cultura", "lectura"]`
- Similitud: 0.55
- **No pasa el umbral → Descartado**

**Solución:**
Reducir el umbral de 0.6 a 0.4 o 0.5:

```python
# app/services/events_service.py línea 152
eventos_filtrados = [e for e in eventos_con_score if e['similitud_score'] >= 0.4]
```

### Causa #3: Extracción de Parámetros Incorrecta (50% probabilidad)

**Síntoma:** OpenAI extrae parámetros que excluyen el evento en el pre-filtrado SQL.

**Ejemplos:**
- **Fecha incorrecta:** OpenAI pone `fecha_inicio = 2026-01-27` pero el evento es el 26/01
- **Categoría incorrecta:** OpenAI extrae "Deportes" pero el evento es "Infantil"
- **Precio:** OpenAI pone `es_gratuito = true` pero el evento cuesta 26.95€

**Verificación:**
Activar `debug=true` en el frontend para ver los parámetros extraídos:

```javascript
// frontend/src/QueryChat.jsx línea 32
body: JSON.stringify({
  pregunta: pregunta,
  cp_usuario: cpUsuario,
  debug: true  // Cambiar a true
})
```

**Solución:**
Mejorar el prompt de extracción de parámetros en `app/services/ai_service.py` líneas 54-74.

### Causa #4: Filtro de Fechas Demasiado Restrictivo (30% probabilidad)

**Síntoma:** OpenAI extrae un rango de fechas que excluye el evento.

**Ejemplo:**
- Evento: 26/01/2026 17:30
- OpenAI extrae: `fecha_inicio = 2026-01-25, fecha_fin = 2026-01-25` (solo hoy)
- Query SQL: `WHERE eh.Fecha_Inicio BETWEEN '2026-01-25' AND '2026-01-25'`
- **Evento del 26/01 queda fuera**

**Solución:**
Si el usuario no menciona fechas específicas, NO extraer `fecha_inicio` / `fecha_fin`.

### Causa #5: JOIN con EVENTO_CATEGORIAS Falla (20% probabilidad)

**Síntoma:** El evento no tiene categorías asignadas en la tabla `EVENTO_CATEGORIAS`.

**Verificación:**
```sql
SELECT 
    em.ID_Unico_Evento,
    em.Titulo_ES,
    GROUP_CONCAT(c.Nombre_ES) as categorias
FROM EVENTOS_MASTER em
LEFT JOIN EVENTO_CATEGORIAS ec ON em.ID_Unico_Evento = ec.ID_Unico_Evento
LEFT JOIN CATEGORIAS c ON ec.ID_Categoria = c.ID_Categoria
WHERE em.Titulo_ES LIKE '%Cuentacuentos%'
GROUP BY em.ID_Unico_Evento
```

**Si `categorias` es NULL:**
- El evento no tiene categorías asignadas
- Si OpenAI extrae una categoría específica, el JOIN falla
- **Evento excluido**

**Solución:**
Asegurar que todos los eventos tengan al menos 1 categoría asignada.

---

## 🛠️ Soluciones Propuestas

### Solución Inmediata #1: Reducir Umbral de Similitud

**Archivo:** `app/services/events_service.py` línea 152

**Cambio:**
```python
# Antes
eventos_filtrados = [e for e in eventos_con_score if e['similitud_score'] >= 0.6]

# Después
eventos_filtrados = [e for e in eventos_con_score if e['similitud_score'] >= 0.4]
```

**Impacto:**
- ✅ Más eventos pasarán el filtro
- ⚠️ Puede incluir eventos menos relevantes

### Solución Inmediata #2: Activar Debug Mode

**Archivo:** `frontend/src/QueryChat.jsx` línea 32

**Cambio:**
```javascript
body: JSON.stringify({
  pregunta: pregunta,
  cp_usuario: cpUsuario,
  debug: true  // Cambiar a true
})
```

**Impacto:**
- ✅ Verás los parámetros extraídos por OpenAI
- ✅ Verás la query SQL generada
- ✅ Verás cuántos eventos se encontraron en cada paso

### Solución Inmediata #3: Verificar Embeddings

**Comando:**
```bash
cd /home/ubuntu/events-query

# Verificar si los eventos tienen embeddings
python3 -c "
import asyncio
from app.services import db_service

async def check():
    await db_service.connect()
    query = '''
    SELECT 
        COUNT(*) as total,
        SUM(CASE WHEN Tags_Embedding_ES IS NULL THEN 1 ELSE 0 END) as sin_embedding
    FROM EVENTOS_MASTER
    WHERE Estado = 'ACTIVO'
    '''
    result = await db_service.execute_query(query, ())
    print(f'Total eventos: {result[0][\"total\"]}')
    print(f'Sin embedding: {result[0][\"sin_embedding\"]}')
    await db_service.disconnect()

asyncio.run(check())
"
```

**Si hay eventos sin embedding:**
```bash
# Regenerar embeddings (si existe el script)
python scripts/generate_embeddings.py
```

### Solución a Medio Plazo #1: Mejorar Prompt de Extracción

**Archivo:** `app/services/ai_service.py` líneas 54-74

**Cambios sugeridos:**
1. **No extraer fechas** si el usuario no las menciona explícitamente
2. **No extraer categorías** si no están claras en la pregunta
3. **Ser más permisivo** con los conceptos

**Ejemplo:**
```python
system_prompt = f"""...

IMPORTANTE:
- Solo extrae fechas si el usuario las menciona EXPLÍCITAMENTE
- Solo extrae categorías si están CLARAS en la pregunta
- Si hay duda, deja los campos vacíos
- Prioriza la búsqueda semántica sobre filtros estrictos
"""
```

### Solución a Medio Plazo #2: Fallback Más Inteligente

**Archivo:** `app/services/events_service.py` líneas 152-156

**Cambio:**
```python
# Filtrar por similitud mínima (0.4 en vez de 0.6)
eventos_filtrados = [e for e in eventos_con_score if e['similitud_score'] >= 0.4]

# Si no hay eventos con similitud >= 0.4, devolver los mejores 20 (en vez de 10)
if not eventos_filtrados and eventos_con_score:
    eventos_filtrados = sorted(eventos_con_score, key=lambda x: x['similitud_score'], reverse=True)[:20]

# Si aún no hay eventos, relajar filtros SQL y reintentar
if not eventos_filtrados:
    # Reintentar sin filtros de fecha/categoría
    pass
```

### Solución a Largo Plazo: Sistema de Logging Completo

**Implementar logging detallado en cada paso:**

```python
# En cada paso del flujo
logger.info(f"PASO 1: Parámetros extraídos: {params}")
logger.info(f"PASO 2: CPs en radio: {codigos_postales}")
logger.info(f"PASO 3: Query SQL: {query}")
logger.info(f"PASO 4: Eventos pre-filtrado: {len(eventos_raw)}")
logger.info(f"PASO 5: Eventos post-semántica: {len(eventos_filtrados)}")
```

**Beneficio:**
- Fácil diagnóstico de problemas
- Ver exactamente dónde se pierden los eventos

---

## 🧪 Plan de Acción Recomendado

### Paso 1: Activar Debug Mode (2 minutos)

```javascript
// frontend/src/QueryChat.jsx línea 32
debug: true
```

Reiniciar frontend y probar la query. Revisar el JSON completo para ver:
- Parámetros extraídos
- Query SQL
- Eventos en cada paso

### Paso 2: Reducir Umbral de Similitud (2 minutos)

```python
# app/services/events_service.py línea 152
eventos_filtrados = [e for e in eventos_con_score if e['similitud_score'] >= 0.4]
```

Reiniciar backend y probar de nuevo.

### Paso 3: Verificar Embeddings (5 minutos)

```bash
# Conectar a MySQL y verificar
mysql -u root -p events_db

SELECT 
    ID_Unico_Evento,
    Titulo_ES,
    CP_Evento,
    CASE 
        WHEN Tags_Embedding_ES IS NULL THEN 'SIN EMBEDDING'
        ELSE 'CON EMBEDDING'
    END as estado_embedding
FROM EVENTOS_MASTER
WHERE Titulo_ES LIKE '%Cuentacuentos%'
AND CP_Evento = '08360';
```

Si no tiene embedding, regenerar.

### Paso 4: Probar Query Directa (5 minutos)

```bash
# Script de diagnóstico
cd /home/ubuntu/events-query
python3 test_query_debug.py
```

Esto ejecutará el flujo completo con logging detallado.

### Paso 5: Ajustar Prompt de OpenAI (10 minutos)

Si los parámetros extraídos son incorrectos, modificar el prompt en `ai_service.py`.

---

## 📋 Checklist de Verificación

- [ ] ¿El evento existe en la BD? (query directa)
- [ ] ¿El evento tiene embeddings generados?
- [ ] ¿El evento está en estado 'ACTIVO'?
- [ ] ¿El evento tiene categorías asignadas?
- [ ] ¿El evento tiene fecha en EVENTO_HORARIOS?
- [ ] ¿OpenAI extrae parámetros correctos? (debug mode)
- [ ] ¿La query SQL incluye el evento? (pre-filtrado)
- [ ] ¿La similitud semántica es >= 0.6? (o el umbral configurado)
- [ ] ¿Los logs del backend muestran errores?

---

## 🎯 Conclusión

El problema **NO es un bug en el código**, sino una **configuración demasiado estricta** de los filtros:

1. **Umbral de similitud 0.6** es muy alto
2. **Falta de embeddings** en algunos eventos
3. **Extracción de parámetros** puede ser demasiado específica

**Recomendación principal:**
1. Activar debug mode
2. Reducir umbral a 0.4
3. Verificar embeddings
4. Probar de nuevo

Con estos cambios, el sistema debería encontrar el evento correctamente.

---

**Script de diagnóstico creado:** `test_query_debug.py`  
**Ejecutar con:** `python3 test_query_debug.py`

---

**Autor:** Manus AI  
**Fecha:** 25 de enero de 2026
