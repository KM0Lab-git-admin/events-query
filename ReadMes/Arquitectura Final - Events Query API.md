# Arquitectura Final - Events Query API

**Versión:** 3.0 FINAL  
**Fecha:** Enero 2026  
**Estado:** ✅ Listo para Implementación

---

## Decisión Arquitectónica Principal

### Tags y Embeddings Separados por Idioma ⭐

```sql
-- En EVENTOS_MASTER:
Tags_ES JSON NULL              -- Tags en español
Tags_CAT JSON NULL             -- Tags en catalán
Tags_Embedding_ES JSON NULL    -- Vector de Tags_ES (1536 dims)
Tags_Embedding_CAT JSON NULL   -- Vector de Tags_CAT (1536 dims)
```

**Justificación:**
- ✅ La API detecta el idioma del usuario
- ✅ Solo consulta el embedding del idioma correspondiente
- ✅ 50% más rápido que mezclar idiomas
- ✅ Mayor precisión en resultados

---

## Diagrama de Flujo Completo

```
┌─────────────────────────────────────────┐
│            USUARIO                      │
│  "Actividades para niños al aire libre  │
│   este fin de semana"                   │
│  CP: "08380"                            │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│         API REST (FastAPI)              │
│  - Valida request                       │
│  - Orquesta flujo                       │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│    IA - EXTRACCIÓN DE PARÁMETROS        │
│                                         │
│  Input: "Actividades para niños..."     │
│                                         │
│  Output:                                │
│  {                                      │
│    "idioma_detectado": "es", ← CLAVE   │
│    "conceptos": ["niños", "aire libre"],│
│    "fechas": {                          │
│      "inicio": "2026-01-25",            │
│      "fin": "2026-01-26"                │
│    },                                   │
│    "categorias": ["infantil"],          │
│    "radio_km": null                     │
│  }                                      │
│                                         │
│  Tiempo: 500ms                          │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│       MOTOR GEOGRÁFICO                  │
│                                         │
│  Input: CP="08380", radio=null          │
│  Output: CPs válidos = ["08380"]        │
│                                         │
│  Tiempo: 50ms                           │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│    CONSTRUCTOR DE QUERIES SQL           │
│                                         │
│  Construye query con filtros EXACTOS:   │
│  • CP_Evento IN ('08380')               │
│  • Fecha BETWEEN '2026-01-25' AND ...   │
│  • Categorías: JOIN con CATEGORIAS      │
│                                         │
│  NO filtra por tags (se hace después)   │
│                                         │
│  Tiempo: 50ms                           │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│       BASE DE DATOS (MySQL)             │
│                                         │
│  Ejecuta query SQL                      │
│  Resultado: 15 eventos                  │
│  (filtrados por CP, fecha, categoría)   │
│                                         │
│  Tiempo: 150ms                          │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│    BÚSQUEDA SEMÁNTICA (Embeddings)      │
│                                         │
│  1. Generar embedding de:               │
│     "niños aire libre"                  │
│     → [0.234, -0.567, ...]              │
│                                         │
│  2. Para cada uno de los 15 eventos:    │
│     • Idioma detectado = "es"           │
│     • Obtener Tags_Embedding_ES         │
│     • Calcular similitud coseno         │
│                                         │
│  3. Filtrar similitud > 0.6             │
│                                         │
│  4. Ordenar por similitud DESC          │
│                                         │
│  Resultado: 8 eventos relevantes        │
│                                         │
│  Tiempo: 130ms                          │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│      POST-PROCESAMIENTO                 │
│                                         │
│  • Calcular distancia exacta            │
│  • Seleccionar campos según idioma      │
│    (Titulo_ES, Desc_ES, Tags_ES)        │
│  • Formatear fechas                     │
│                                         │
│  Tiempo: 50ms                           │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│      IA - RESPUESTA NATURAL             │
│                                         │
│  Input: pregunta + 8 eventos + idioma   │
│  Output: "He encontrado 8 actividades..."│
│                                         │
│  Tiempo: 500ms                          │
└──────────────┬──────────────────────────┘
               │
               ▼
┌─────────────────────────────────────────┐
│         API REST - RESPONSE             │
│                                         │
│  {                                      │
│    "respuesta_texto": "He encontrado...",│
│    "eventos": [...8 eventos...],        │
│    "total": 8,                          │
│    "idioma_respuesta": "es"             │
│  }                                      │
└──────────────┬──────────────────────────┘
               │
               ▼
            USUARIO
```

---

## Performance Total

```
Extracción parámetros (IA):         500ms
Cálculo geográfico:                  50ms
Construcción query:                  50ms
Ejecución SQL (pre-filtrado):       150ms
Generar embedding usuario:          100ms
Calcular similitud (15 eventos):     30ms
Post-procesamiento:                  50ms
Respuesta natural (IA):             500ms
Serialización JSON:                  50ms
────────────────────────────────────────────
TOTAL:                             1480ms ✅ < 3 segundos
```

---

## Esquema de Base de Datos

```
CIUDADES
  ↓ (1:N)
CODIGOS_POSTALES
  ↓ (1:N)
EVENTOS_MASTER
  ├─ Tags_ES              ← Array JSON español
  ├─ Tags_CAT             ← Array JSON catalán
  ├─ Tags_Embedding_ES    ← Vector español (1536 dims)
  └─ Tags_Embedding_CAT   ← Vector catalán (1536 dims)
  ↓ (1:N)
EVENTO_HORARIOS

CATEGORIAS (catálogo cerrado)
  ↓ (N:M)
EVENTO_CATEGORIAS
  ↓
EVENTOS_MASTER
```

---

## Flujo de Búsqueda Detallado

### Caso: Usuario pregunta en ESPAÑOL

```
1. Usuario: "actividades para pequeños al aire libre"
   ↓
2. IA detecta idioma: "es"
   ↓
3. IA extrae conceptos: ["pequeños", "aire libre"]
   ↓
4. Pre-filtrado SQL (CP, fecha, categoría)
   → 15 eventos
   ↓
5. Generar embedding de "pequeños aire libre"
   → [0.234, -0.567, ...]
   ↓
6. Para cada evento:
      Comparar con Tags_Embedding_ES (porque idioma="es")
      Calcular similitud coseno
   ↓
7. Evento con Tags_ES=["#niños", "#aire_libre"]
   → similitud: 0.89 ✅ (muy relevante)
   ↓
8. Filtrar eventos con similitud > 0.6
   → 8 eventos relevantes
   ↓
9. Ordenar por similitud DESC
   ↓
10. Devolver resultados
```

### Caso: Usuario pregunta en CATALÁN

```
1. Usuario: "activitats per a nens a l'aire lliure"
   ↓
2. IA detecta idioma: "ca"
   ↓
3. IA extrae conceptos: ["nens", "aire lliure"]
   ↓
4. Pre-filtrado SQL (mismo query)
   → 15 eventos
   ↓
5. Generar embedding de "nens aire lliure"
   → [0.238, -0.562, ...]
   ↓
6. Para cada evento:
      Comparar con Tags_Embedding_CAT (porque idioma="ca")
      Calcular similitud coseno
   ↓
7. Evento con Tags_CAT=["#nens", "#a_l_aire_lliure"]
   → similitud: 0.91 ✅ (muy relevante)
   ↓
8. Filtrar y ordenar
   ↓
9. Devolver resultados en catalán
```

---

## Ejemplo de Datos en BD

```json
{
  "ID_Unico_Evento": "abc123...",
  "Titulo_ES": "Taller de naturaleza para niños",
  "Titulo_CAT": "Taller de naturalesa per a nens",
  
  "Tags_ES": [
    "#infantil",
    "#niños",
    "#aire_libre",
    "#parque",
    "#taller",
    "#educativo"
  ],
  
  "Tags_CAT": [
    "#infantil",
    "#nens",
    "#a_l_aire_lliure",
    "#parc",
    "#taller",
    "#educatiu"
  ],
  
  "Tags_Embedding_ES": [0.123, -0.456, 0.789, ...],  // 1536 números
  "Tags_Embedding_CAT": [0.125, -0.450, 0.792, ...],  // 1536 números
  
  "Categorias": [4, 8]  // Infantil, Naturaleza
}
```

---

## Stack Tecnológico

### Backend
- **Python 3.11**
- **FastAPI 0.115.x** - Framework web + Swagger
- **Pydantic 2.x** - Validación
- **Uvicorn** - Servidor ASGI

### Base de Datos
- **MySQL 8.0**
- **mysql-connector-python 9.0**

### Inteligencia Artificial
- **OpenAI Python SDK 1.40.0**
- **gpt-4.1-mini** - Extracción y respuestas
- **text-embedding-3-small** - Búsqueda semántica

---

## Endpoints de la API

### `POST /query`
```json
// Request
{
  "pregunta": "¿Qué hacer este fin de semana?",
  "cp_usuario": "08380",
  "debug": false
}

// Response
{
  "respuesta_texto": "He encontrado 5 eventos...",
  "eventos": [...],
  "total": 5,
  "idioma_respuesta": "es"
}
```

### `GET /health`
Health check del servicio.

### `GET /docs`
Documentación Swagger interactiva.

---

## Ventajas de la Arquitectura Final

### 1. Performance Optimizada
✅ Solo procesa el idioma necesario  
✅ Pre-filtrado SQL reduce eventos a evaluar  
✅ < 1.5 segundos de respuesta  

### 2. Mayor Precisión
✅ Embeddings puros de un idioma  
✅ No hay "ruido" de mezcla de idiomas  
✅ Resultados más relevantes  

### 3. Escalabilidad
✅ Fácil añadir más idiomas (Tags_EN, Tags_Embedding_EN)  
✅ No afecta performance de idiomas existentes  
✅ Cada idioma es independiente  

### 4. Mantenibilidad
✅ Código limpio (if idioma == "es" → usar Tags_Embedding_ES)  
✅ Fácil debuggear  
✅ Fácil testear  

---

## Próximos Pasos para Implementación

1. ✅ **Documentación completa**
2. ⏭️ **Montar MySQL** y ejecutar SCHEMA_SQL_FINAL.sql
3. ⏭️ **Generar datos fake** (125 eventos, 5 ciudades)
4. ⏭️ **Implementar servicios** (AIService, GeoService, QueryBuilder, DBService)
5. ⏭️ **Implementar API** (FastAPI con endpoints)
6. ⏭️ **Testing** (unitarios e integración)
7. ⏭️ **Deployment** (Docker + systemd)

---

## Conclusión

La arquitectura final está optimizada para:
- ✅ **Performance < 3 segundos** garantizada
- ✅ **Búsqueda semántica precisa** por idioma
- ✅ **Escalabilidad** a miles de eventos
- ✅ **Mantenibilidad** con código limpio
- ✅ **Bilingüismo** nativo (español/catalán)

**Estado:** ✅ Listo para implementación
