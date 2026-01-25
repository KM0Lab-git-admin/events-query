# 📋 Plan de Testing y Validación - Events Query API

**Fecha:** 25 de enero de 2026  
**Objetivo:** Garantizar precisión del 95%+ en búsqueda de eventos  
**Problema actual:** Fallos en casos obvios (ej: "comida" no encuentra "Cata de vinos y quesos")

---

## 🎯 Objetivos del Plan

1. **Testing exhaustivo** con 50+ casos de prueba reales
2. **Visibilidad paso a paso** de todo el proceso de búsqueda
3. **Detección automática** de fallos (esperado vs obtenido)
4. **Propuestas de mejora** basadas en análisis de fallos
5. **Simplificación temporal** (sin radio, sin fechas, solo CP + descripción)

---

## 📐 Arquitectura de la Solución

### Componente 1: Simplificación de Búsqueda (Temporal)

**Cambios en `events_service.py`:**

```python
# MODO TESTING: Desactivar filtros temporales y geográficos
TESTING_MODE = True  # Variable de entorno

if TESTING_MODE:
    # Solo filtrar por CP exacto
    # No filtrar por fechas
    # No filtrar por radio
    # Solo usar búsqueda semántica
```

**Beneficios:**
- Aislar el problema de búsqueda semántica
- Eliminar variables confusoras
- Facilitar debugging

---

### Componente 2: Sistema de Testing

**Archivo:** `tests/test_search_accuracy.py`

**Estructura:**

```python
test_cases = [
    {
        "id": 1,
        "pregunta": "Hay actividades relacionadas con comida?",
        "cp": "08380",
        "eventos_esperados": ["Cata de vinos y quesos - Malgrat de Mar"],
        "debe_encontrar": True,
        "categoria_esperada": "Gastronomía"
    },
    {
        "id": 2,
        "pregunta": "Cuentacuentos en la biblioteca",
        "cp": "08360",
        "eventos_esperados": ["Cuentacuentos en la biblioteca - Canet de Mar"],
        "debe_encontrar": True,
        "categoria_esperada": "Infantil"
    },
    # ... 50+ casos
]
```

**Funcionalidad:**
1. Ejecuta cada caso de prueba
2. Compara resultado con esperado
3. Calcula métricas (precisión, recall, F1)
4. Genera informe detallado

---

### Componente 3: Trazabilidad Paso a Paso

**Archivo:** `app/services/trace_service.py`

**Captura en cada paso:**

```python
trace = {
    "paso_1_extraccion": {
        "pregunta_original": "...",
        "parametros_extraidos": {...},
        "prompt_usado": "...",
        "respuesta_openai": "..."
    },
    "paso_2_sql": {
        "query_generada": "...",
        "params": [...],
        "eventos_encontrados": 50,
        "tiempo_ms": 123
    },
    "paso_3_embeddings": {
        "pregunta_embedding": [...],
        "eventos_con_embedding": 45,
        "eventos_sin_embedding": 5
    },
    "paso_4_similitud": {
        "scores": [
            {"id": "EVT001", "titulo": "...", "score": 0.87},
            {"id": "EVT002", "titulo": "...", "score": 0.65},
            ...
        ],
        "umbral_usado": 0.4,
        "eventos_sobre_umbral": 10
    },
    "paso_5_conversion": {
        "eventos_a_convertir": 10,
        "eventos_convertidos": 10,
        "eventos_fallidos": 0,
        "errores": []
    },
    "paso_6_respuesta": {
        "respuesta_generada": "...",
        "eventos_finales": 10,
        "tiempo_total_ms": 2500
    }
}
```

---

### Componente 4: Dashboard de Análisis

**Archivo:** `frontend/src/TestingDashboard.jsx`

**Funcionalidades:**

1. **Lista de Tests**
   - Ver todos los casos de prueba
   - Estado: ✅ Pass / ❌ Fail / ⚠️ Parcial
   - Filtrar por estado, categoría

2. **Detalle de Test**
   - Pregunta y CP
   - Eventos esperados vs obtenidos
   - Trazabilidad paso a paso
   - Scores de similitud
   - Embeddings visualizados

3. **Análisis de Fallos**
   - Por qué falló (sin embedding, score bajo, no en BD)
   - Propuestas de mejora
   - Tags faltantes
   - Categorías incorrectas

4. **Métricas Globales**
   - Precisión: X%
   - Recall: Y%
   - F1 Score: Z%
   - Tiempo promedio: Nms

---

### Componente 5: Sistema de Validación Automática

**Archivo:** `tests/auto_validator.py`

**Lógica:**

```python
def validar_resultado(test_case, resultado):
    """
    Valida automáticamente si el resultado tiene sentido.
    """
    validaciones = []
    
    # Validación 1: ¿Encontró eventos cuando debía?
    if test_case['debe_encontrar'] and len(resultado['eventos']) == 0:
        validaciones.append({
            "tipo": "FALLO_CRITICO",
            "mensaje": "Debía encontrar eventos pero no encontró ninguno",
            "propuesta": "Revisar embeddings y tags"
        })
    
    # Validación 2: ¿Los eventos son del CP correcto?
    for evento in resultado['eventos']:
        if evento['cp_evento'] != test_case['cp']:
            validaciones.append({
                "tipo": "ERROR_CP",
                "mensaje": f"Evento {evento['id']} tiene CP {evento['cp_evento']}, esperado {test_case['cp']}",
                "propuesta": "Revisar filtro de CP"
            })
    
    # Validación 3: ¿Encontró los eventos esperados?
    eventos_esperados = test_case['eventos_esperados']
    eventos_obtenidos = [e['titulo'] for e in resultado['eventos']]
    
    for esperado in eventos_esperados:
        if not any(esperado in obtenido for obtenido in eventos_obtenidos):
            validaciones.append({
                "tipo": "EVENTO_FALTANTE",
                "mensaje": f"No encontró evento esperado: {esperado}",
                "propuesta": "Analizar score de similitud y tags"
            })
    
    # Validación 4: ¿Los scores son razonables?
    for evento in resultado['eventos']:
        if evento.get('similitud_score', 0) < 0.3:
            validaciones.append({
                "tipo": "SCORE_BAJO",
                "mensaje": f"Evento {evento['titulo']} tiene score muy bajo: {evento['similitud_score']}",
                "propuesta": "Revisar embeddings o aumentar umbral"
            })
    
    return validaciones
```

---

### Componente 6: Análisis de Embeddings

**Archivo:** `tools/analyze_embeddings.py`

**Funcionalidades:**

1. **Verificar cobertura**
   - ¿Cuántos eventos tienen embeddings?
   - ¿Cuántos faltan?

2. **Calidad de embeddings**
   - Similitud entre eventos de misma categoría
   - Similitud entre eventos de distinta categoría

3. **Análisis de tags**
   - Tags más comunes
   - Tags faltantes (comparar con categorías)
   - Sugerencias de tags adicionales

4. **Generar embeddings faltantes**
   - Script para generar embeddings de eventos sin ellos

---

## 🛠️ Implementación por Fases

### Fase 1: Simplificación (30 min)

**Tareas:**
1. ✅ Añadir variable `TESTING_MODE` en `.env`
2. ✅ Modificar `events_service.py` para desactivar filtros temporales/geográficos
3. ✅ Modificar extracción de parámetros para ignorar fechas/radio en modo testing

**Resultado:** Búsqueda solo por CP exacto + similitud semántica

---

### Fase 2: Sistema de Testing (1h)

**Tareas:**
1. ✅ Crear `tests/test_cases.json` con 50 casos de prueba
2. ✅ Crear `tests/test_search_accuracy.py` con runner de tests
3. ✅ Implementar comparación esperado vs obtenido
4. ✅ Generar informe JSON con resultados

**Resultado:** Script que ejecuta 50 tests y genera informe

---

### Fase 3: Trazabilidad (1h)

**Tareas:**
1. ✅ Crear `app/services/trace_service.py`
2. ✅ Integrar en cada paso del flujo de búsqueda
3. ✅ Guardar trace en archivo JSON por cada búsqueda
4. ✅ Endpoint `/api/trace/{query_id}` para ver trace

**Resultado:** Visibilidad total del proceso

---

### Fase 4: Validación Automática (45 min)

**Tareas:**
1. ✅ Crear `tests/auto_validator.py`
2. ✅ Implementar 10 validaciones automáticas
3. ✅ Integrar con test runner
4. ✅ Generar propuestas de mejora

**Resultado:** Sistema que detecta fallos automáticamente

---

### Fase 5: Dashboard (2h)

**Tareas:**
1. ✅ Crear `frontend/src/TestingDashboard.jsx`
2. ✅ Vista de lista de tests
3. ✅ Vista de detalle con trazabilidad
4. ✅ Vista de métricas globales
5. ✅ Vista de propuestas de mejora

**Resultado:** Interfaz visual para analizar tests

---

### Fase 6: Análisis y Mejoras (1h)

**Tareas:**
1. ✅ Ejecutar 50 tests
2. ✅ Analizar fallos
3. ✅ Generar informe de mejoras propuestas
4. ✅ Implementar mejoras prioritarias

**Resultado:** Sistema mejorado con mayor precisión

---

## 📊 Casos de Prueba Propuestos

### Categoría: Gastronomía

| ID | Pregunta | CP | Evento Esperado | Debe Encontrar |
|----|----------|-----|-----------------|----------------|
| 1 | "Actividades relacionadas con comida?" | 08380 | Cata de vinos y quesos | ✅ SÍ |
| 2 | "Hay alguna cata de vinos?" | 08380 | Cata de vinos y quesos | ✅ SÍ |
| 3 | "Eventos gastronómicos" | 08380 | Cata de vinos y quesos | ✅ SÍ |
| 4 | "Restaurantes nuevos" | 08380 | - | ❌ NO |

### Categoría: Infantil

| ID | Pregunta | CP | Evento Esperado | Debe Encontrar |
|----|----------|-----|-----------------|----------------|
| 5 | "Cuentacuentos en la biblioteca" | 08360 | Cuentacuentos biblioteca Canet | ✅ SÍ |
| 6 | "Actividades para niños" | 08360 | Cuentacuentos biblioteca Canet | ✅ SÍ |
| 7 | "Qué hacer con mis hijos" | 08360 | Cuentacuentos biblioteca Canet | ✅ SÍ |

### Categoría: Cultura

| ID | Pregunta | CP | Evento Esperado | Debe Encontrar |
|----|----------|-----|-----------------|----------------|
| 8 | "Exposiciones de arte" | 17300 | [Evento cultural en Blanes] | ✅ SÍ |
| 9 | "Museos abiertos" | 17300 | - | ❌ NO |

### Categoría: Deportes

| ID | Pregunta | CP | Evento Esperado | Debe Encontrar |
|----|----------|-----|-----------------|----------------|
| 10 | "Partidos de fútbol" | 08370 | [Evento deportivo en Calella] | ✅ SÍ |
| 11 | "Gimnasios cerca" | 08370 | - | ❌ NO |

---

## 🔍 Análisis del Caso de Fallo Reportado

### Caso: "Actividades relacionadas con comida?"

**Pregunta:** "Hay actividades relacionadas con comida?"  
**CP:** 08380 (Malgrat de Mar)  
**Evento en BD:** "Cata de vinos y quesos - Malgrat de Mar"  
**Resultado:** NO encontrado ❌  
**Esperado:** SÍ encontrado ✅

---

### Análisis Paso a Paso

#### Paso 1: Extracción de Parámetros

**Esperado:**
```json
{
  "conceptos": ["comida", "gastronomía", "alimentación"],
  "categorias": ["Gastronomía"]
}
```

**Posible problema:**
- OpenAI no extrae "comida" como concepto
- O extrae pero con embedding diferente

#### Paso 2: SQL Pre-filtrado

**Query:**
```sql
WHERE CP_Evento = '08380' AND Estado = 'ACTIVO'
```

**Esperado:** Evento "Cata de vinos y quesos" SÍ aparece

**Verificación necesaria:**
- ¿El evento existe en la BD?
- ¿Tiene CP 08380?
- ¿Está ACTIVO?

#### Paso 3: Embeddings

**Pregunta embedding:** `["comida", "actividades"]`  
**Evento tags:** `["vinos", "quesos", "cata", "gastronomía"]`

**Problema potencial:**
- Similitud entre "comida" y ["vinos", "quesos"] puede ser baja
- "Cata" no se asocia directamente con "comida"

**Solución:**
- Añadir tag "comida" al evento
- Añadir tag "gastronomía" si no existe
- Añadir tag "alimentación"

#### Paso 4: Similitud Semántica

**Score actual:** Probablemente < 0.4 (por eso no pasa)

**Causas posibles:**
1. Tags insuficientes
2. Embedding de pregunta no captura "cata" como "comida"
3. Umbral demasiado alto

**Soluciones:**
1. Añadir más tags relacionados
2. Ajustar prompt de extracción para capturar sinónimos
3. Bajar umbral a 0.3 (temporalmente)

---

### Propuestas de Mejora para Este Caso

#### Mejora 1: Enriquecer Tags

**Evento:** "Cata de vinos y quesos"

**Tags actuales:** `["vinos", "quesos", "cata", "gastronomía"]`

**Tags propuestos:**
```json
[
  "vinos", "quesos", "cata", "gastronomía",
  "comida", "alimentación", "degustación",
  "enología", "productos locales", "maridaje"
]
```

#### Mejora 2: Ajustar Categorías

**Categoría actual:** Probablemente "Cultura" o "Ocio"

**Categoría propuesta:** "Gastronomía" (principal) + "Cultura" (secundaria)

#### Mejora 3: Mejorar Descripción

**Descripción actual:** (desconocida)

**Descripción propuesta:**
```
Disfruta de una experiencia gastronómica única con nuestra cata de vinos 
y quesos locales. Aprende sobre maridaje y descubre los sabores de la región. 
Actividad perfecta para amantes de la comida y el buen vino.
```

**Palabras clave añadidas:** "gastronómica", "comida", "sabores"

---

## 🎯 Métricas de Éxito

### Objetivo: 95% de Precisión

**Métricas a medir:**

1. **Precisión (Precision)**
   - De los eventos devueltos, ¿cuántos son relevantes?
   - Objetivo: > 90%

2. **Recall (Cobertura)**
   - De los eventos relevantes, ¿cuántos se devuelven?
   - Objetivo: > 95%

3. **F1 Score**
   - Media armónica de precisión y recall
   - Objetivo: > 92%

4. **Tiempo de Respuesta**
   - Tiempo total de búsqueda
   - Objetivo: < 2 segundos

5. **Tasa de Fallos Críticos**
   - Casos donde debía encontrar y no encontró
   - Objetivo: < 5%

---

## 🚀 Roadmap de Implementación

### Semana 1: Infraestructura

- [x] Simplificar búsqueda (modo testing)
- [ ] Sistema de testing con 50 casos
- [ ] Trazabilidad paso a paso
- [ ] Validación automática

### Semana 2: Dashboard y Análisis

- [ ] Dashboard de testing
- [ ] Análisis de embeddings
- [ ] Ejecución de tests
- [ ] Informe de mejoras

### Semana 3: Mejoras

- [ ] Enriquecer tags (top 50 eventos)
- [ ] Ajustar categorías
- [ ] Mejorar descripciones
- [ ] Generar embeddings faltantes

### Semana 4: Validación

- [ ] Re-ejecutar tests
- [ ] Medir mejora en métricas
- [ ] Ajustar umbrales
- [ ] Desplegar a producción

---

## 📝 Próximos Pasos Inmediatos

1. **Confirmar plan** con el usuario
2. **Priorizar fases** (¿empezar por testing o por simplificación?)
3. **Definir 20 casos de prueba** iniciales (los más críticos)
4. **Implementar Fase 1** (simplificación)
5. **Ejecutar tests manuales** para validar

---

**¿Aprobado para empezar?**
