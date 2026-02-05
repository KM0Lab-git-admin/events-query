# 🏷️ Guía de Tags y Embeddings

**Versión:** 1.0  
**Fecha:** 2026-01-25  
**Audiencia:** Developers, IA de scraping, Data engineers

---

## 📋 Tabla de Contenidos

1. [¿Qué son los Tags y Embeddings?](#qué-son-los-tags-y-embeddings)
2. [¿Por qué son Críticos?](#por-qué-son-críticos)
3. [Estructura de Tags](#estructura-de-tags)
4. [Mejores Prácticas para Tags](#mejores-prácticas-para-tags)
5. [Generación de Embeddings](#generación-de-embeddings)
6. [Cómo Usar el Script de Embeddings](#cómo-usar-el-script-de-embeddings)
7. [Troubleshooting](#troubleshooting)

---

## 🎯 ¿Qué son los Tags y Embeddings?

### Tags

**Definición:** Palabras clave que describen un evento.

**Ejemplo:**
```json
{
  "Tags_ES": ["infantil", "familia", "educativo", "cuentacuentos", "Cultura"],
  "Tags_CAT": ["infantil", "família", "educatiu", "contacontes", "Cultura"]
}
```

**Propósito:**
- Facilitar búsqueda semántica
- Categorizar eventos
- Mejorar matching con consultas de usuarios

---

### Embeddings

**Definición:** Representación vectorial (1536 números) de un texto generada por OpenAI.

**Ejemplo:**
```json
{
  "Tags_Embedding_ES": [0.123, -0.456, 0.789, ..., 0.321],  // 1536 floats
  "Tags_Embedding_CAT": [0.111, -0.444, 0.777, ..., 0.333]
}
```

**Propósito:**
- Calcular similitud semántica entre pregunta y evento
- Encontrar eventos relevantes aunque no coincidan palabras exactas
- Permitir búsqueda en lenguaje natural

**Cómo se genera:**
- Se combina: **título + descripción (300 chars) + tags + categoría**
- Se envía a OpenAI API (`text-embedding-3-small`)
- OpenAI devuelve un vector de 1536 números
- Se guarda en la BD como JSON

---

## ⚠️ ¿Por qué son Críticos?

### Sin Tags Adecuados

**Problema:** Evento no se encuentra aunque sea relevante.

**Ejemplo:**
- **Evento:** "Cata de vinos y quesos"
- **Tags actuales:** `["vinos", "quesos", "cata"]`
- **Pregunta usuario:** "¿Actividades relacionadas con comida?"
- **Resultado:** ❌ **NO SE ENCUENTRA** (similitud 0.35 < umbral 0.4)

**Solución:** Añadir tags relacionados: `["gastronomía", "comida", "alimentación", "degustación"]`

---

### Sin Embeddings

**Problema:** Evento recibe score por defecto (0.3) y nunca pasa el filtro.

**Ejemplo:**
- **Evento:** "Observación de aves - Malgrat de Mar"
- **Embedding:** `NULL` (no generado)
- **Score:** 0.3 (por defecto)
- **Umbral:** 0.4
- **Resultado:** ❌ **DESCARTADO**

**Solución:** Generar embedding con el script `generate_embeddings.py`

---

## 🏗️ Estructura de Tags

### Formato

```json
{
  "Tags_ES": ["tag1", "tag2", "Categoría", "tag3"],
  "Tags_CAT": ["tag1_cat", "tag2_cat", "Categoria", "tag3_cat"]
}
```

### Tipos de Tags

| Tipo | Descripción | Ejemplos ES | Ejemplos CAT |
|------|-------------|-------------|--------------|
| **Categoría** | Tag principal (empieza con mayúscula) | Cultura, Deportes, Gastronomía | Cultura, Esports, Gastronomia |
| **Público objetivo** | A quién va dirigido | infantil, familia, adultos, seniors | infantil, família, adults, gent gran |
| **Tipo de actividad** | Qué tipo de evento es | taller, concierto, exposición, cata | taller, concert, exposició, tast |
| **Temática** | Tema específico | música, arte, naturaleza, tecnología | música, art, naturalesa, tecnologia |
| **Características** | Atributos especiales | gratuito, al aire libre, accesible | gratuït, a l'aire lliure, accessible |

---

### Ejemplos Completos

#### Evento Infantil

```json
{
  "titulo_es": "Cuentacuentos en la biblioteca",
  "Tags_ES": ["Infantil", "familia", "educativo", "cuentacuentos", "lectura", "niños", "biblioteca"],
  "Tags_CAT": ["Infantil", "família", "educatiu", "contacontes", "lectura", "nens", "biblioteca"]
}
```

#### Evento Gastronómico

```json
{
  "titulo_es": "Cata de vinos y quesos",
  "Tags_ES": ["Gastronomía", "comida", "vinos", "quesos", "degustación", "alimentación", "enología"],
  "Tags_CAT": ["Gastronomia", "menjar", "vins", "formatges", "tast", "alimentació", "enologia"]
}
```

#### Evento Deportivo

```json
{
  "titulo_es": "Torneo de fútbol local",
  "Tags_ES": ["Deportes", "fútbol", "competición", "deporte", "actividad física", "torneo"],
  "Tags_CAT": ["Esports", "futbol", "competició", "esport", "activitat física", "torneig"]
}
```

#### Evento Cultural

```json
{
  "titulo_es": "Exposición de arte contemporáneo",
  "Tags_ES": ["Cultura", "arte", "exposición", "artístico", "cultural", "museo", "contemporáneo"],
  "Tags_CAT": ["Cultura", "art", "exposició", "artístic", "cultural", "museu", "contemporani"]
}
```

---

## ✅ Mejores Prácticas para Tags

### 1. Cantidad Óptima

- **Mínimo:** 5 tags
- **Óptimo:** 7-10 tags
- **Máximo:** 15 tags

**Razón:** Más tags = más oportunidades de matching semántico.

---

### 2. Incluir Siempre

✅ **Categoría principal** (con mayúscula)  
✅ **Público objetivo** (infantil, familia, adultos)  
✅ **Tipo de actividad** (taller, concierto, exposición)  
✅ **Sinónimos y variaciones** (comida, gastronomía, alimentación)  
✅ **Conceptos relacionados** (vinos → enología, bebidas)

---

### 3. Evitar

❌ **Tags demasiado genéricos** (evento, actividad, cosa)  
❌ **Tags redundantes** (música, musical, musicales)  
❌ **Tags en otro idioma** (en Tags_ES solo español)  
❌ **Tags con errores ortográficos**  
❌ **Tags vacíos o con espacios** ("", " ")

---

### 4. Normalización

- **Minúsculas:** Todos los tags en minúsculas (excepto Categoría)
- **Sin acentos en claves:** Pero SÍ en valores (ej: "música" ✅)
- **Singular preferido:** "niño" mejor que "niños" (pero ambos OK)
- **Sin artículos:** "biblioteca" mejor que "la biblioteca"

---

### 5. Cobertura Semántica

**Objetivo:** Cubrir diferentes formas de buscar el mismo concepto.

**Ejemplo:** Evento de comida

```json
{
  "Tags_ES": [
    "Gastronomía",      // Categoría formal
    "comida",           // Término común
    "alimentación",     // Término técnico
    "culinaria",        // Variación
    "degustación",      // Tipo de actividad
    "cata",             // Sinónimo
    "vinos",            // Específico
    "enología"          // Relacionado
  ]
}
```

**Cobertura:** Ahora el evento se encontrará con cualquiera de estas preguntas:
- "¿Actividades de comida?"
- "¿Eventos gastronómicos?"
- "¿Catas de vino?"
- "¿Degustaciones?"
- "¿Algo relacionado con alimentación?"

---

## 🤖 Prompt para IA de Scraping

Si usas una IA para generar tags automáticamente durante el scraping, usa este prompt:

```
Eres un experto en categorización de eventos locales.

Dado el siguiente evento:
- Título: {titulo}
- Descripción: {descripcion}
- Categoría: {categoria}

Genera una lista de 7-10 tags en español que describan el evento.

REGLAS:
1. El primer tag DEBE ser la categoría con mayúscula (Cultura, Deportes, Gastronomía, Infantil, Ocio, Formación, Música, Naturaleza)
2. Incluye el público objetivo (infantil, familia, adultos, seniors)
3. Incluye el tipo de actividad (taller, concierto, exposición, cata, etc.)
4. Incluye sinónimos y conceptos relacionados
5. Todos los tags en minúsculas excepto el primero
6. Sin artículos, sin errores ortográficos
7. Mínimo 5 tags, máximo 15

EJEMPLOS:

Evento: "Cuentacuentos en la biblioteca"
Tags: ["Infantil", "familia", "educativo", "cuentacuentos", "lectura", "niños", "biblioteca"]

Evento: "Cata de vinos y quesos"
Tags: ["Gastronomía", "comida", "vinos", "quesos", "degustación", "alimentación", "enología"]

Evento: "Torneo de fútbol local"
Tags: ["Deportes", "fútbol", "competición", "deporte", "actividad física", "torneo"]

Ahora genera los tags para el evento proporcionado.
Devuelve SOLO un array JSON, sin explicaciones.
```

---

## 🔧 Generación de Embeddings

### ¿Cuándo se Generan?

1. **Automáticamente:** Al ejecutar `scripts/generate_fake_data.py` (datos fake)
2. **Manualmente:** Al ejecutar `scripts/generate_embeddings.py` (eventos existentes)
3. **Futuro:** Al insertar evento via API (trigger automático)

---

### ¿Qué se Incluye en el Embedding?

El embedding NO es solo de los tags, sino de un **texto combinado**:

```
TÍTULO. DESCRIPCIÓN (300 chars). TAGS. CATEGORÍA
```

**Ejemplo:**

```
Cuentacuentos en la biblioteca - Malgrat de Mar. 
Actividad infantil de lectura y cuentacuentos organizada por la biblioteca municipal. 
Ideal para niños de 3 a 8 años. Fomenta la lectura y la imaginación. 
infantil familia educativo cuentacuentos lectura niños biblioteca. 
Infantil
```

**Razón:** Esto captura TODO el contexto del evento, mejorando el matching semántico.

---

### Modelo Usado

- **Modelo:** `text-embedding-3-small`
- **Dimensiones:** 1536 floats
- **Coste:** ~$0.00002 por 1000 tokens (~$0.02 por 1000 eventos)
- **Velocidad:** ~20 eventos/segundo en batch

---

## 📖 Cómo Usar el Script de Embeddings

### Instalación

No requiere instalación adicional. Solo asegúrate de tener:

```bash
# Variables de entorno configuradas
export OPENAI_API_KEY="tu-api-key"
export DATABASE_URL="mysql://user:pass@host:port/db"
```

---

### Uso Básico

#### 1. Generar embeddings para eventos SIN embeddings

```bash
cd /ruta/a/events-query
python scripts/generate_embeddings.py
```

**Output:**
```
====================================================
GENERADOR DE EMBEDDINGS PARA EVENTOS EXISTENTES
====================================================

Configuración:
  - Modo: Solo eventos sin embeddings
  - Batch size: 20
  - Dry run: No

🔌 Conectando a la base de datos...
  ✅ Conectado

📊 Obteniendo eventos...
  ✅ 50 eventos encontrados

====================================================
GENERANDO EMBEDDINGS PARA 50 EVENTOS
Batch size: 20
Modo: PRODUCCIÓN
====================================================

📦 Procesando batch 1/3 (20 eventos)...
  ✅ 10/50 eventos procesados...
  ✅ 20/50 eventos procesados...
📦 Procesando batch 2/3 (20 eventos)...
  ✅ 30/50 eventos procesados...
  ✅ 40/50 eventos procesados...
📦 Procesando batch 3/3 (10 eventos)...
  ✅ 50/50 eventos procesados...

====================================================
RESUMEN
====================================================
  Total eventos: 50
  Procesados: 50
  Actualizados: 50
  Errores: 0

✅ Embeddings generados y guardados exitosamente
====================================================

🔌 Desconectado de la base de datos
```

---

#### 2. Regenerar embeddings para TODOS los eventos

```bash
python scripts/generate_embeddings.py --all
```

**Uso:** Cuando cambias el modelo o la lógica de construcción de texto.

---

#### 3. Simular sin guardar (Dry Run)

```bash
python scripts/generate_embeddings.py --dry-run
```

**Uso:** Para probar sin modificar la BD.

---

#### 4. Ajustar batch size

```bash
python scripts/generate_embeddings.py --batch-size 50
```

**Uso:** Para procesar más rápido (pero más coste de API).

---

### Opciones Completas

```bash
python scripts/generate_embeddings.py --help
```

**Output:**
```
usage: generate_embeddings.py [-h] [--all] [--batch-size BATCH_SIZE] [--dry-run]

Genera embeddings para eventos existentes en la base de datos

optional arguments:
  -h, --help            show this help message and exit
  --all                 Regenerar embeddings para TODOS los eventos
  --batch-size BATCH_SIZE
                        Tamaño del batch para OpenAI (default: 20)
  --dry-run             Simula la generación sin guardar en BD
```

---

## 🔍 Troubleshooting

### Problema 1: "No hay eventos para procesar"

**Causa:** Todos los eventos ya tienen embeddings.

**Solución:**
```bash
# Ver cuántos eventos tienen embeddings
mysql> SELECT COUNT(*) FROM EVENTOS_MASTER WHERE Tags_Embedding_ES IS NOT NULL;

# Si quieres regenerar todos
python scripts/generate_embeddings.py --all
```

---

### Problema 2: "Error generando embeddings en batch"

**Causa:** Problema con OpenAI API (rate limit, API key inválida, etc.)

**Solución:**
```bash
# Verificar API key
echo $OPENAI_API_KEY

# Verificar que funciona
curl https://api.openai.com/v1/models \
  -H "Authorization: Bearer $OPENAI_API_KEY"

# Reducir batch size para evitar rate limit
python scripts/generate_embeddings.py --batch-size 10
```

---

### Problema 3: "Evento tiene score 0.3 aunque tenga embedding"

**Causa:** El embedding está vacío o corrupto.

**Solución:**
```sql
-- Ver eventos con embeddings vacíos
SELECT ID_Unico_Evento, Titulo_ES
FROM EVENTOS_MASTER
WHERE Tags_Embedding_ES = '[]' OR Tags_Embedding_ES = 'null';

-- Regenerar embeddings para esos eventos
UPDATE EVENTOS_MASTER
SET Tags_Embedding_ES = NULL, Tags_Embedding_CAT = NULL
WHERE Tags_Embedding_ES = '[]';

-- Luego ejecutar
python scripts/generate_embeddings.py
```

---

### Problema 4: "Eventos no se encuentran aunque tengan embeddings"

**Causa:** Tags insuficientes o poco relevantes.

**Solución:**

1. **Revisar tags actuales:**
```sql
SELECT Titulo_ES, Tags_ES
FROM EVENTOS_MASTER
WHERE ID_Unico_Evento = 'evento_id';
```

2. **Añadir más tags:**
```sql
UPDATE EVENTOS_MASTER
SET Tags_ES = '["Gastronomía", "comida", "vinos", "quesos", "degustación", "alimentación", "enología"]'
WHERE ID_Unico_Evento = 'evento_id';
```

3. **Regenerar embedding:**
```sql
UPDATE EVENTOS_MASTER
SET Tags_Embedding_ES = NULL, Tags_Embedding_CAT = NULL
WHERE ID_Unico_Evento = 'evento_id';
```

```bash
python scripts/generate_embeddings.py
```

---

### Problema 5: "Script muy lento"

**Causa:** Batch size pequeño o muchos eventos.

**Solución:**
```bash
# Aumentar batch size (máximo recomendado: 100)
python scripts/generate_embeddings.py --batch-size 100

# Procesar en paralelo (avanzado)
# Dividir eventos en chunks y ejecutar múltiples scripts
```

---

## 📊 Métricas de Calidad

### Tags

| Métrica | Valor Óptimo | Cómo Medirlo |
|---------|--------------|--------------|
| **Cantidad promedio** | 7-10 tags | `SELECT AVG(JSON_LENGTH(Tags_ES)) FROM EVENTOS_MASTER` |
| **Eventos sin tags** | 0% | `SELECT COUNT(*) FROM EVENTOS_MASTER WHERE Tags_ES IS NULL OR Tags_ES = '[]'` |
| **Tags únicos** | 100-200 | `SELECT COUNT(DISTINCT tag) FROM (SELECT JSON_UNQUOTE(JSON_EXTRACT(Tags_ES, CONCAT('$[', n, ']'))) as tag FROM EVENTOS_MASTER)` |

---

### Embeddings

| Métrica | Valor Óptimo | Cómo Medirlo |
|---------|--------------|--------------|
| **Cobertura** | 100% | `SELECT COUNT(*) FROM EVENTOS_MASTER WHERE Tags_Embedding_ES IS NOT NULL` |
| **Embeddings vacíos** | 0% | `SELECT COUNT(*) FROM EVENTOS_MASTER WHERE Tags_Embedding_ES = '[]'` |
| **Dimensiones** | 1536 | `SELECT JSON_LENGTH(Tags_Embedding_ES) FROM EVENTOS_MASTER LIMIT 1` |

---

## 🎯 Checklist de Calidad

Antes de considerar un evento "listo para producción", verifica:

- [ ] Tiene al menos 5 tags
- [ ] El primer tag es la Categoría (con mayúscula)
- [ ] Incluye público objetivo (infantil, familia, etc.)
- [ ] Incluye tipo de actividad (taller, concierto, etc.)
- [ ] Incluye sinónimos y conceptos relacionados
- [ ] Tags en español en `Tags_ES`, en catalán en `Tags_CAT`
- [ ] Tiene embedding generado (`Tags_Embedding_ES` no es NULL)
- [ ] Embedding tiene 1536 dimensiones
- [ ] Embedding no está vacío (`[]`)

---

## 📚 Referencias

- [OpenAI Embeddings Documentation](https://platform.openai.com/docs/guides/embeddings)
- [Text Embedding 3 Small Model](https://platform.openai.com/docs/models/embeddings)
- [Cosine Similarity Explained](https://en.wikipedia.org/wiki/Cosine_similarity)

---

## 🤝 Contribuir

Si encuentras mejoras en esta guía o en los scripts, por favor:

1. Crea un issue en GitHub
2. Propón cambios via Pull Request
3. Actualiza esta documentación

---

**¡Gracias por mantener la calidad de los datos! 🚀**
