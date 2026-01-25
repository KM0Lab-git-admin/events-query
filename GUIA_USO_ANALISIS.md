# 🔬 Guía de Uso del Sistema de Análisis Detallado

**Fecha:** 25 de enero de 2026  
**Versión:** 1.0  
**Commit:** feature/frontend-poc

---

## 🎯 ¿Qué es el Sistema de Análisis?

El sistema de análisis detallado te permite entender **exactamente por qué** un evento pasa o no el filtro de búsqueda semántica. Proporciona:

1. **Similitud por tag individual** - Qué tags aportan más a la similitud
2. **Similitud por categoría** - Si la categoría es relevante
3. **Similitud por descripción** - Relevancia de la descripción
4. **Diagnóstico automático** - Problemas detectados
5. **Propuestas de mejora** - Soluciones con impacto estimado

---

## 🚀 Cómo Usar el Sistema

### Paso 1: Iniciar Backend y Frontend

**Terminal 1 - Backend:**
```bash
cd /home/ubuntu/events-query
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**Terminal 2 - Frontend:**
```bash
cd /home/ubuntu/events-query/frontend
pnpm dev
```

### Paso 2: Abrir la Aplicación

Abre http://localhost:3000 en tu navegador.

### Paso 3: Hacer una Consulta

1. Escribe una pregunta en el campo de texto
   - Ejemplo: "Actividades relacionadas con comida?"
   
2. Ingresa el código postal
   - Ejemplo: 08380

3. Click en "Buscar"

4. **Espera 5-10 segundos** (el análisis detallado toma más tiempo)

### Paso 4: Ver el Análisis

Después de la respuesta, verás una nueva sección:

```
🔬 Análisis Detallado de Similitud
```

Esta sección muestra los primeros 20 eventos analizados.

---

## 📊 Interpretando los Resultados

### Tarjeta de Evento

Cada evento muestra:

```
┌─────────────────────────────────────────────────────────────┐
│ ✅ Cata de vinos y quesos - Malgrat de Mar                  │
│ ID: EVT123                                                   │
│                                                              │
│ Score: 0.55 ✅    Umbral: 0.4                               │
└─────────────────────────────────────────────────────────────┘
```

- **✅ Verde:** Evento pasa el filtro (score >= umbral)
- **❌ Rojo:** Evento NO pasa el filtro (score < umbral)

### Similitud por Tag

Al expandir un evento, verás:

```
📊 Similitud por Tag:
  • vinos:        ████░░░░░░ 0.25
  • quesos:       ████████░░ 0.42 ⭐
  • cata:         ███░░░░░░░ 0.18
  • gastronomía:  ███████████ 0.55 ⭐⭐
```

**Interpretación:**
- **Barra verde:** Similitud > 0.4 (relevante)
- **Barra gris:** Similitud < 0.4 (poco relevante)
- **⭐:** Tag relevante para la búsqueda

**Ejemplo:**
Si buscas "comida" y el tag "gastronomía" tiene 0.55, significa que OpenAI considera que "gastronomía" es muy similar a "comida".

### Similitud por Categoría

```
📂 Similitud por Categoría:
  • Cultura:  ██░░░░░░░░ 0.15
  ⚠️ Categoría poco relevante para la búsqueda
```

**Interpretación:**
- **< 0.3:** Categoría poco relevante (rojo)
- **> 0.3:** Categoría relevante (verde)

**Ejemplo:**
Si buscas "comida" pero el evento está en categoría "Cultura", la similitud será baja (0.15).

### Diagnóstico Automático

```
🔍 Diagnóstico

⚠️ Problemas Detectados:
  [ALTA] CATEGORIA_IRRELEVANTE
  Categoría 'Cultura' tiene similitud muy baja (0.15)

  [ALTA] TAGS_INSUFICIENTES
  Solo 1 tags con similitud > 0.4

💡 Soluciones Propuestas:
  [ALTA] cambiar_categoria  +0.20
  Cambiar categoría a 'Gastronomía'
  Cambiar: Cultura → Gastronomía

  [ALTA] añadir_tags  +0.15
  Añadir tags: comida, alimentación, degustación
  Tags: comida, alimentación, degustación

📈 Score Estimado con Mejoras:
  Actual: 0.35  →  Estimado: 0.70  ✅ Pasaría el filtro
```

**Interpretación:**

1. **Problemas Detectados:**
   - **CRÍTICA:** Debe solucionarse inmediatamente
   - **ALTA:** Impacto significativo
   - **MEDIA:** Impacto moderado
   - **BAJA:** Impacto menor

2. **Soluciones Propuestas:**
   - **Prioridad:** Orden de implementación
   - **Tipo:** Qué hacer (cambiar categoría, añadir tags, etc.)
   - **Impacto:** Cuánto mejorará el score (+0.20 = +20%)

3. **Score Estimado:**
   - Score actual vs score después de aplicar mejoras
   - Si el estimado >= umbral, muestra "✅ Pasaría el filtro"

---

## 🎯 Casos de Uso

### Caso 1: Evento No Encontrado (Falso Negativo)

**Problema:** Buscas "comida" pero no encuentras "Cata de vinos y quesos"

**Pasos:**
1. Haz la búsqueda
2. Ve al análisis detallado
3. Busca el evento "Cata de vinos y quesos"
4. Verás que tiene score 0.35 (< 0.4)
5. Mira el diagnóstico:
   - Problema: Categoría incorrecta
   - Solución: Cambiar a "Gastronomía" y añadir tags

**Acción:**
Actualiza el evento en la BD:
```sql
UPDATE EVENTOS_MASTER
SET 
  Categoria = 'Gastronomía',
  Tags_ES = JSON_ARRAY('vinos', 'quesos', 'cata', 'gastronomía', 'comida', 'alimentación')
WHERE ID_Unico_Evento = 'EVT123';
```

### Caso 2: Evento Irrelevante Encontrado (Falso Positivo)

**Problema:** Buscas "comida" y aparece un "Concierto de rock"

**Pasos:**
1. Haz la búsqueda
2. Ve al análisis detallado
3. Busca el evento "Concierto de rock"
4. Verás que tiene score 0.45 (>= 0.4) pero no es relevante
5. Mira la similitud por tag:
   - Algún tag tiene alta similitud incorrectamente

**Acción:**
Revisar los tags del evento y eliminar los que no corresponden.

### Caso 3: Evento Sin Embedding

**Problema:** Un evento siempre tiene score 0.3

**Pasos:**
1. Haz la búsqueda
2. Ve al análisis detallado
3. Busca el evento
4. Verás en el diagnóstico:
   - **[CRÍTICA] SIN_EMBEDDING**
   - "El evento no tiene embedding generado"

**Acción:**
Generar embedding para el evento:
```python
# Script para generar embeddings faltantes
python tools/generate_missing_embeddings.py
```

---

## 🔧 Ajustando el Sistema

### Cambiar el Umbral de Similitud

**Ubicación:** `app/services/events_service.py` línea 152

```python
# Actual
eventos_filtrados = [e for e in eventos_con_score if e['similitud_score'] >= 0.4]

# Más permisivo (más resultados)
eventos_filtrados = [e for e in eventos_con_score if e['similitud_score'] >= 0.3]

# Más estricto (menos resultados)
eventos_filtrados = [e for e in eventos_con_score if e['similitud_score'] >= 0.5]
```

**Recomendación:**
- **0.3:** Búsqueda amplia, puede incluir eventos menos relevantes
- **0.4:** Balance (actual)
- **0.5:** Búsqueda estricta, solo eventos muy relevantes

### Cambiar Cantidad de Eventos Analizados

**Ubicación:** `app/services/events_service.py` línea 93

```python
# Actual (20 eventos)
analisis_detallado = await analysis_service.analyze_batch(
    eventos_raw[:20],
    ...
)

# Analizar más eventos (50)
analisis_detallado = await analysis_service.analyze_batch(
    eventos_raw[:50],
    ...
)
```

**Nota:** Más eventos = más tiempo de procesamiento (cada embedding toma ~100ms)

---

## 📝 Mejorando los Eventos

### Estrategia de Mejora

1. **Priorizar por impacto:**
   - Eventos con score 0.35-0.45 (cerca del umbral)
   - Eventos con soluciones de prioridad ALTA o CRÍTICA

2. **Aplicar mejoras en orden:**
   1. Generar embeddings faltantes
   2. Corregir categorías
   3. Añadir tags relevantes
   4. Mejorar descripciones

3. **Validar mejoras:**
   - Re-ejecutar la búsqueda
   - Verificar que el score aumentó
   - Confirmar que el evento ahora aparece

### Plantilla de Tags por Categoría

**Gastronomía:**
```json
["gastronomía", "comida", "alimentación", "degustación", "culinaria", "cocina"]
```

**Infantil:**
```json
["infantil", "niños", "familia", "educativo", "entretenimiento", "diversión"]
```

**Cultura:**
```json
["cultura", "arte", "exposición", "museo", "patrimonio", "historia"]
```

**Deportes:**
```json
["deportes", "deporte", "actividad física", "salud", "fitness", "competición"]
```

**Música:**
```json
["música", "concierto", "musical", "artista", "espectáculo", "entretenimiento"]
```

---

## 🎯 Métricas de Éxito

### Antes de las Mejoras

```
Búsqueda: "Actividades relacionadas con comida?"
Eventos esperados: 5
Eventos encontrados: 1
Precisión: 20%
```

### Después de las Mejoras

```
Búsqueda: "Actividades relacionadas con comida?"
Eventos esperados: 5
Eventos encontrados: 5
Precisión: 100%
```

---

## 🐛 Troubleshooting

### Problema: No veo la sección de análisis

**Causa:** El análisis solo se muestra si hay eventos en la BD

**Solución:** Verifica que hay eventos con el CP buscado

### Problema: El análisis tarda mucho

**Causa:** Generar embeddings para 20 eventos toma ~2 segundos

**Solución:** Reducir la cantidad de eventos analizados (línea 93 de events_service.py)

### Problema: Todos los eventos tienen score 0.3

**Causa:** Los eventos no tienen embeddings generados

**Solución:** Ejecutar script de generación de embeddings

### Problema: El diagnóstico no sugiere nada

**Causa:** El mapeo de conceptos a categorías/tags es limitado

**Solución:** Ampliar el mapeo en `analysis_service.py` (líneas 150-200)

---

## 📚 Ejemplos de Búsquedas para Probar

### Búsquedas Gastronómicas

1. "Actividades relacionadas con comida?"
2. "Hay alguna cata de vinos?"
3. "Eventos gastronómicos"
4. "Dónde comer bien?"
5. "Restaurantes con eventos"

### Búsquedas Infantiles

1. "Cuentacuentos en la biblioteca"
2. "Actividades para niños"
3. "Qué hacer con mis hijos"
4. "Talleres infantiles"
5. "Eventos familiares"

### Búsquedas Culturales

1. "Exposiciones de arte"
2. "Museos abiertos"
3. "Eventos culturales"
4. "Conciertos de música clásica"
5. "Teatro este fin de semana"

### Búsquedas Deportivas

1. "Partidos de fútbol"
2. "Carreras populares"
3. "Eventos deportivos"
4. "Gimnasios con actividades"
5. "Torneos de tenis"

---

## 🔄 Flujo de Trabajo Recomendado

### 1. Identificar Fallos

```
1. Hacer búsqueda
2. Ver respuesta
3. ¿Falta algún evento esperado?
   → SÍ: Ir al análisis detallado
   → NO: Búsqueda exitosa
```

### 2. Analizar Causa

```
1. Buscar el evento faltante en el análisis
2. Ver su score
3. ¿Score < umbral?
   → SÍ: Ver diagnóstico
   → NO: Problema en otro lugar
```

### 3. Aplicar Solución

```
1. Leer soluciones propuestas
2. Priorizar por impacto
3. Aplicar en la BD
4. Regenerar embedding si es necesario
```

### 4. Validar

```
1. Re-ejecutar búsqueda
2. Verificar que el evento ahora aparece
3. Confirmar que el score aumentó
```

---

## 📞 Soporte

Si tienes dudas o encuentras problemas:

1. Revisa esta guía
2. Revisa los logs del backend (terminal 1)
3. Revisa la consola del navegador (F12)
4. Contacta al equipo de desarrollo

---

**Autor:** Manus AI  
**Fecha:** 25 de enero de 2026  
**Versión:** 1.0
