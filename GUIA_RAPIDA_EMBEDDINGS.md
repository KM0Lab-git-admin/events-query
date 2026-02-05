# 🚀 Guía Rápida: Generación de Embeddings

**Para:** Usuario que necesita generar embeddings ahora mismo  
**Tiempo de lectura:** 2 minutos

---

## ✅ ¿Qué Necesitas?

1. **Base de datos** configurada y accesible
2. **OpenAI API Key** configurada en variables de entorno
3. **Python 3.11+** con dependencias instaladas

---

## 🔧 Configuración Rápida

```bash
# 1. Configurar variables de entorno
export OPENAI_API_KEY="tu-api-key-aqui"
export DATABASE_URL="mysql://user:pass@host:port/events_query"

# 2. Ir al directorio del proyecto
cd /ruta/a/events-query

# 3. Verificar que funciona
python scripts/generate_embeddings.py --dry-run
```

---

## 🎯 Casos de Uso

### Caso 1: Generar Embeddings para Eventos Nuevos

**Situación:** Has insertado eventos desde scraping y no tienen embeddings.

```bash
python scripts/generate_embeddings.py
```

**Output esperado:**
```
📊 Obteniendo eventos...
  ✅ 50 eventos encontrados

📦 Procesando batch 1/3 (20 eventos)...
  ✅ 20/50 eventos procesados...

✅ Embeddings generados y guardados exitosamente
```

---

### Caso 2: Regenerar TODOS los Embeddings

**Situación:** Cambiaste la lógica de tags o quieres usar un nuevo modelo.

```bash
python scripts/generate_embeddings.py --all
```

---

### Caso 3: Probar Sin Modificar BD

**Situación:** Quieres ver qué pasaría sin guardar cambios.

```bash
python scripts/generate_embeddings.py --dry-run
```

---

## ⚡ Opciones Útiles

| Opción | Descripción | Ejemplo |
|--------|-------------|---------|
| `--all` | Regenera embeddings para TODOS los eventos | `python scripts/generate_embeddings.py --all` |
| `--dry-run` | Simula sin guardar en BD | `python scripts/generate_embeddings.py --dry-run` |
| `--batch-size N` | Procesa N eventos por batch (default: 20) | `python scripts/generate_embeddings.py --batch-size 50` |

---

## 📊 Verificar Resultados

```sql
-- Ver cuántos eventos tienen embeddings
SELECT COUNT(*) as con_embeddings
FROM EVENTOS_MASTER
WHERE Tags_Embedding_ES IS NOT NULL;

-- Ver cuántos NO tienen embeddings
SELECT COUNT(*) as sin_embeddings
FROM EVENTOS_MASTER
WHERE Tags_Embedding_ES IS NULL;

-- Ver un ejemplo de embedding
SELECT 
    Titulo_ES,
    JSON_LENGTH(Tags_Embedding_ES) as dimensiones
FROM EVENTOS_MASTER
WHERE Tags_Embedding_ES IS NOT NULL
LIMIT 1;
```

**Resultado esperado:**
```
+-------------------+-------------+
| Titulo_ES         | dimensiones |
+-------------------+-------------+
| Cuentacuentos...  | 1536        |
+-------------------+-------------+
```

---

## ❓ Troubleshooting Rápido

### "No hay eventos para procesar"

✅ **Solución:** Todos los eventos ya tienen embeddings. Usa `--all` si quieres regenerar.

---

### "Error generando embeddings"

❌ **Causa:** Problema con OpenAI API

✅ **Solución:**
```bash
# Verificar API key
echo $OPENAI_API_KEY

# Probar con batch size menor
python scripts/generate_embeddings.py --batch-size 10
```

---

### "Eventos no se encuentran aunque tengan embeddings"

❌ **Causa:** Tags insuficientes o poco relevantes

✅ **Solución:** Lee `docs/TAGS_Y_EMBEDDINGS.md` para mejorar los tags

---

## 📚 Documentación Completa

Para más detalles, lee:
- **`docs/TAGS_Y_EMBEDDINGS.md`** - Guía completa de tags y embeddings
- **`scripts/generate_embeddings.py --help`** - Ayuda del script

---

## 🎉 ¡Listo!

Con esto ya puedes generar embeddings para tus eventos. Si tienes dudas, revisa la documentación completa.

**¿Siguiente paso?** Mejora los tags de tus eventos para aumentar la precisión de búsqueda. 🚀
