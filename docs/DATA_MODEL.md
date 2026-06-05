# 🗄️ Modelo de Datos + Ingesta IA (VAC 360) — Events Query

Este documento unifica:
- Esquema MySQL usado por la API (consulta + ranking)
- Convenciones de tags y embeddings (calidad y generación)
- Especificación del protocolo de ingesta IA (VAC 360)

---

## 1) Modelo MySQL usado por la API (MVP en esta repo)

La API de consultas se apoya en un esquema relacional orientado a:

- **Filtrado temporal** (rangos de fechas / “hoy” / próximos días)
- **Filtrado geográfico** por CP + cálculo de distancia (Haversine)
- **Búsqueda semántica** vía embeddings de tags
- **Bilingüe** (ES/CAT)

### Tablas (núcleo)

**EVENTOS_MASTER** (tabla principal)
- Identidad: `ID_Unico_Evento`
- Idiomas: `Titulo_ES`, `Titulo_CAT`, `Desc_*_ES`, `Desc_*_CAT`
- Geografía: `CP_Evento`, `Poblacion_Nombre`, `Lugar_Nombre`, `Direccion_Fisica`
- Economía: `Es_Gratuito`, `Precio_Euros`
- Tags: `Tags_ES` (JSON), `Tags_CAT` (JSON)
- Embeddings: `Tags_Embedding_ES`, `Tags_Embedding_CAT` (JSON, dims del modelo)
- Multimedia y enlaces: `Imagen_Principal_URL`, `Link_Entradas_Inscripcion`
- Control: `Estado`, `Fecha_Creacion`

**EVENTO_HORARIOS**
- Normaliza fechas/horas (`Fecha_Inicio`, `Fecha_Fin`, `Hora_Inicio`, `Hora_Fin`)

**CATEGORIAS** y **EVENTO_CATEGORIAS**
- Categorías + relación N:M con eventos

**CODIGOS_POSTALES**
- `CP` + lat/long para distancia

**POBLACIONES**
- Maestro de poblaciones

**ORGANIZADORES** y **EVENTO_ORGANIZADORES**
- Organizadores + relación N:M

> Nota: este esquema “MVP” es el que aparece documentado en `docs/ARCHITECTURE.md`. Si tu base tiene más tablas (por el módulo VAC 360), ver sección 3.

---

## 2) Tags y Embeddings (búsqueda semántica)

### 2.1 Qué son
- **Tags**: lista de conceptos normalizados (JSON) que describen el evento.
- **Embeddings**: vector numérico (por idioma) que permite comparar semánticamente pregunta ↔ evento.

### 2.2 Buenas prácticas para tags
- 8–15 tags suele funcionar bien (evitar listas enormes).
- Incluir siempre: tipo de plan, público, contexto (“familia”, “infantil”, “aire libre”), categoría semántica (“cultura”, “deporte”), localidad si aporta.
- Evitar: tags redundantes (“evento”, “actividad”), emojis, spam o call-to-actions.

### 2.3 Generación de embeddings
Normalmente:
- Al crear datos fake (`scripts/generate_fake_data.py`)
- O al backfillear (`scripts/generate_embeddings.py`)

**Qué entra al embedding**: tags + campos cortos relevantes (según implementación).

---

## 3) Especificación VAC 360 (ingesta y gobierno del dato)

Esta capa define cómo una IA/scraper debe **insertar y mantener** eventos con trazabilidad y reglas de calidad.

### 3.1 Arquitectura jerárquica (visión)

1) Geografía central  
- `CIUDADES` (centroides)  
- `CODIGOS_POSTALES` (precisión para distancia)

2) Usuario y proximidad  
- `PERFIL_USUARIO` (CP origen, radio)

3) Captura / fuentes  
- `MAPEO_REDES_POBLACION`  
- `BIBLIOTECA_FUENTES`, `SCRAPING_TARGETS`, `EVENTO_FUENTES`

4) Evento maestro (7 dimensiones)  
- `EVENTOS_MASTER` como tabla principal

5) Tablas hijas  
- `EVENTO_HORARIOS`  
- `BINARIOS_STORAGE`

> Importante: la presencia real de estas tablas depende de tu instancia de BD. Si hoy tu API solo usa el MVP (8 tablas), esta sección funciona como **blueprint** para el módulo de ingesta.

---

## 4) Protocolo de Ingesta IA: `Fuente_ID`

Cada extracción debe etiquetarse con un `Fuente_ID` (tecnología + confianza):

| Fuente_ID | Tecnología | Método |
|---|---|---|
| `URL_ESTRUCTURAL` | Web scraping DOM | parseo HTML (alta precisión numérica) |
| `SOCIAL_VISUAL` | Computer Vision / OCR | extracción desde cartel/imagen |
| `SOCIAL_SEMANTICA` | NLP | interpretación (“mañana”, “gratis”, “en el centro”) |

---

## 5) Temporalidad y recurrencia

Para evitar duplicados:
- Recurrencias complejas se guardan como JSON (y/o se expanden a `EVENTO_HORARIOS`).

Ejemplo de `Recurrencia_JSON`:

```json
{
  "tipo": "semanal",
  "intervalo": 1,
  "regla": {
    "dias_semana": ["martes", "jueves"],
    "meses_activos": [8, 9, 10],
    "finalizacion": { "tipo": "fecha", "valor": "2026-10-31" }
  },
  "horarios": [{ "inicio": "08:00", "fin": "10:00" }]
}
```

---

## 6) Reglas de calidad (Data Quality) para IA

- **Integridad geográfica**: si falta dirección/coordenadas, asignar centroide de ciudad y CP probable.
- **Bilingüe obligatorio**: si la fuente viene en un idioma, completar el otro (traducción de alta calidad).  
  Excepción: nombres propios.
- **Temporalidad relativa**: “este viernes”, “próximo finde” → fecha absoluta (YYYY-MM-DD).
- **Veracidad multimedia**: si OCR contradice texto del post, marcar `PENDIENTE_REVISION` y auditar.
- **Sanitización**: limpiar emojis, spam y “link en bio” de descripciones largas.

---

**Última actualización de esta guía:** 2026-02-07
