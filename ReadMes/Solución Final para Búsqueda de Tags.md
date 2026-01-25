# Solución Final para Búsqueda de Tags

## Decisión Final: Tags y Embeddings Separados por Idioma

### Estructura en Base de Datos

```sql
CREATE TABLE EVENTOS_MASTER (
  ...
  -- Tags separados
  Tags_ES JSON NULL COMMENT 'Tags en español',
  Tags_CAT JSON NULL COMMENT 'Tags en catalán',
  
  -- Embeddings separados
  Tags_Embedding_ES JSON NULL COMMENT 'Vector de Tags_ES (1536 dims)',
  Tags_Embedding_CAT JSON NULL COMMENT 'Vector de Tags_CAT (1536 dims)',
  ...
);
```

### Ejemplo de Datos

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
  "Tags_Embedding_CAT": [0.125, -0.450, 0.792, ...]   // 1536 números
}
```

---

## Flujo de Búsqueda Optimizado

### Caso 1: Usuario Pregunta en Español

```
1. Usuario: "actividades para pequeños al aire libre"
   ↓
2. IA detecta idioma: "es"
   ↓
3. IA extrae conceptos: ["pequeños", "aire libre"]
   ↓
4. Pre-filtrado SQL (CP, fecha, categoría)
   Resultado: 15 eventos
   ↓
5. Generar embedding de "pequeños aire libre"
   embedding_usuario = [0.234, -0.567, 0.891, ...]
   ↓
6. Para cada uno de los 15 eventos:
      • Obtener Tags_Embedding_ES (porque idioma="es")
      • Calcular similitud_coseno(embedding_usuario, Tags_Embedding_ES)
   ↓
7. Filtrar eventos con similitud > 0.6
   ↓
8. Ordenar por similitud DESC
   ↓
9. Devolver resultados
```

**Ventajas:**
✅ Solo compara con embeddings en español  
✅ No procesa embeddings en catalán (ahorro de tiempo)  
✅ Más preciso (no hay "ruido" de otro idioma)  

---

### Caso 2: Usuario Pregunta en Catalán

```
1. Usuario: "activitats per a nens a l'aire lliure"
   ↓
2. IA detecta idioma: "ca"
   ↓
3. IA extrae conceptos: ["nens", "aire lliure"]
   ↓
4. Pre-filtrado SQL (mismo que antes)
   Resultado: 15 eventos
   ↓
5. Generar embedding de "nens aire lliure"
   embedding_usuario = [0.238, -0.562, 0.895, ...]
   ↓
6. Para cada uno de los 15 eventos:
      • Obtener Tags_Embedding_CAT (porque idioma="ca")
      • Calcular similitud_coseno(embedding_usuario, Tags_Embedding_CAT)
   ↓
7. Filtrar eventos con similitud > 0.6
   ↓
8. Ordenar por similitud DESC
   ↓
9. Devolver resultados
```

**Ventajas:**
✅ Solo compara con embeddings en catalán  
✅ No procesa embeddings en español  
✅ Más preciso para búsquedas en catalán  

---

## Comparación de Performance

### Opción Anterior (Tags Mezclados):
```
Tags_Array: ["#infantil", "#nens", "#niños", "#aire_libre", "#a_l_aire_lliure"]
Tags_Embedding: [0.123, -0.456, ...]  // Embedding de TODOS los tags

Búsqueda:
- Generar embedding usuario: 100ms
- Comparar con embedding mixto: 30ms
- Total: 130ms

Problema: El embedding mixto tiene "ruido" de ambos idiomas
```

### Opción Final (Tags Separados):
```
Tags_ES: ["#infantil", "#niños", "#aire_libre"]
Tags_CAT: ["#infantil", "#nens", "#a_l_aire_lliure"]
Tags_Embedding_ES: [0.123, -0.456, ...]
Tags_Embedding_CAT: [0.125, -0.450, ...]

Búsqueda:
- Generar embedding usuario: 100ms
- Comparar SOLO con embedding del idioma: 30ms
- Total: 130ms

Ventaja: Embedding puro de un idioma, más preciso
```

**Mejora:** Mismo tiempo, pero **mayor precisión** en resultados.

---

## Cómo Entiende Sinónimos

### Ejemplo: Usuario dice "nenes" (variante de "niños")

**Con Tags Separados:**
```
1. Usuario: "actividades para nenes"
   ↓
2. IA detecta idioma: "es"
   ↓
3. Generar embedding de "nenes"
   embedding_nenes = [0.234, -0.567, ...]
   ↓
4. Evento tiene Tags_ES: ["#niños", "#infantil"]
   Tags_Embedding_ES = [0.235, -0.565, ...]
   ↓
5. Similitud coseno:
   similitud(embedding_nenes, Tags_Embedding_ES) = 0.92
   ↓
6. 0.92 > 0.6 ✅ → Evento encontrado
```

**¿Por qué funciona?**
- Los embeddings capturan el **significado semántico**
- "nenes", "niños", "pequeños", "infantil" tienen embeddings muy similares
- No necesita diccionario de sinónimos
- La IA de OpenAI ya entiende que son conceptos relacionados

---

## Flujo de Ingesta (IA Externa)

La IA que popula la base de datos debe:

```python
# Pseudocódigo (NO implementar aún, solo conceptual)

def ingestar_evento(evento_raw):
    # 1. Extraer información del evento
    titulo = evento_raw['titulo']
    descripcion = evento_raw['descripcion']
    
    # 2. Generar tags en español
    tags_es = ia.generar_tags(titulo, descripcion, idioma="es")
    # → ["#infantil", "#niños", "#aire_libre", "#parque"]
    
    # 3. Generar tags en catalán
    tags_cat = ia.generar_tags(titulo, descripcion, idioma="ca")
    # → ["#infantil", "#nens", "#a_l_aire_lliure", "#parc"]
    
    # 4. Generar embedding de tags español
    embedding_es = ia.generar_embedding(tags_es)
    # → [0.123, -0.456, 0.789, ...]
    
    # 5. Generar embedding de tags catalán
    embedding_cat = ia.generar_embedding(tags_cat)
    # → [0.125, -0.450, 0.792, ...]
    
    # 6. Insertar en BD
    db.insert({
        "Tags_ES": tags_es,
        "Tags_CAT": tags_cat,
        "Tags_Embedding_ES": embedding_es,
        "Tags_Embedding_CAT": embedding_cat,
        ...
    })
```

---

## Ventajas de la Solución Final

### 1. Performance Optimizada
✅ Solo procesa el idioma necesario  
✅ Ahorra ~50% de comparaciones  
✅ Mantiene performance < 3 segundos  

### 2. Mayor Precisión
✅ Embeddings puros de un idioma  
✅ No hay "ruido" de mezcla de idiomas  
✅ Resultados más relevantes  

### 3. Escalabilidad
✅ Fácil añadir más idiomas (Tags_EN, Tags_Embedding_EN)  
✅ No afecta performance de idiomas existentes  
✅ Cada idioma es independiente  

### 4. Mantenibilidad
✅ Código más limpio (if idioma == "es" → usar Tags_Embedding_ES)  
✅ Fácil debuggear (ves exactamente qué idioma se usa)  
✅ Fácil testear (pruebas separadas por idioma)  

---

## Casos de Uso Reales

### Caso 1: Sinónimos Directos
```
Usuario: "actividades para nenes"
Tags evento: ["#niños", "#infantil"]
Similitud: 0.92 ✅ (muy alta)
```

### Caso 2: Conceptos Relacionados
```
Usuario: "cosas para hacer con la familia"
Tags evento: ["#infantil", "#familia", "#ocio"]
Similitud: 0.78 ✅ (alta)
```

### Caso 3: No Relacionado
```
Usuario: "conciertos de rock"
Tags evento: ["#infantil", "#niños", "#taller"]
Similitud: 0.12 ❌ (muy baja, no se devuelve)
```

### Caso 4: Multilingüe (Usuario Español, Evento Catalán)
```
Usuario (ES): "actividades para niños"
Evento:
  - Tags_ES: ["#infantil", "#niños"]
  - Tags_CAT: ["#infantil", "#nens"]

Flujo:
1. IA detecta idioma: "es"
2. Compara con Tags_Embedding_ES
3. Similitud: 0.95 ✅
4. Devuelve evento con campos en español:
   - Titulo_ES
   - Desc_Larga_ES
   - Tags_ES
```

---

## Conclusión

**Decisión Final:** Tags y embeddings separados por idioma

**Justificación:**
- ✅ Mayor precisión en búsquedas
- ✅ Performance optimizada
- ✅ Escalable a más idiomas
- ✅ Código más limpio y mantenible
- ✅ No requiere una sola consulta adicional (ya sabemos el idioma)

**Estado:** ✅ Listo para implementación
