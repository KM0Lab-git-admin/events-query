# 🔬 Análisis Exhaustivo de Todos los Puntos de Fallo

**Fecha:** 25 de enero de 2026  
**Estado:** CRÍTICO - 10 eventos se pierden en la conversión  
**Debug Info:** eventos_pre_filtrado=50, eventos_post_semantica=10, eventos_finales=0

---

## 🚨 Situación Actual

A pesar de aplicar 8 fixes, el problema persiste:

```
SQL (50) → Semántica (10) → Conversión (0) ✗
```

**Conclusión:** Hay un problema MÁS PROFUNDO en la conversión a Pydantic que mis fixes anteriores no resolvieron.

---

## 🔍 Análisis de Todos los Puntos de Fallo Posibles

### Punto de Fallo #1: Validación de Pydantic (ALTA PROBABILIDAD)

**Ubicación:** `app/models/schemas.py` líneas 57-80

**Problema potencial:**
Aunque hice `fecha_inicio` opcional, puede haber OTROS campos que están causando `ValidationError`:

```python
class Evento(BaseModel):
    id_unico_evento: str          # ¿Puede ser None?
    titulo: str                    # ¿Puede ser None?
    cp_evento: str                 # ¿Puede ser None?
    poblacion_nombre: str          # ¿Puede ser None?
    es_gratuito: bool              # ¿Puede ser None? → bool(None) = False
```

**Campos sospechosos:**
1. `id_unico_evento` - Si es None, falla
2. `titulo` - Si es None, falla
3. `cp_evento` - Si es None, falla
4. `poblacion_nombre` - Si es None, falla
5. `es_gratuito` - Si es None, `bool(None)` = False (puede pasar)

**Solución:** Hacer TODOS los campos opcionales excepto `id_unico_evento`

---

### Punto de Fallo #2: Tipo de Dato Incorrecto (ALTA PROBABILIDAD)

**Ubicación:** `app/services/events_service.py` líneas 217-240

**Problema potencial:**
Los datos vienen de MySQL con tipos específicos que pueden no coincidir con Pydantic:

```python
# MySQL → Python
TINYINT(1) → int (0 o 1), NO bool
VARCHAR → str o None
DATE → date o None
DECIMAL → Decimal, NO float
```

**Ejemplo de fallo:**
```python
# Si es_gratuito viene como int (0 o 1)
es_gratuito=bool(evento_raw.get('es_gratuito', False))
# bool(0) = False ✓
# bool(1) = True ✓
# bool(None) = False ✓
# Esto debería funcionar...
```

**Pero:**
```python
# Si precio_euros viene como Decimal
precio_euros=float(evento_raw['precio_euros']) if evento_raw.get('precio_euros') else None
# float(Decimal('26.95')) = 26.95 ✓
# float(None) = ERROR ✗
```

**Solución:** Usar try-except por cada conversión de tipo

---

### Punto de Fallo #3: Logging Silencioso (ALTA PROBABILIDAD)

**Ubicación:** `app/services/events_service.py` líneas 245-249

**Problema:**
El `except Exception as e` captura TODOS los errores, pero:

1. Si el logger no está configurado correctamente, no verás los errores
2. Si el nivel de log es muy alto (WARNING, ERROR), no verás los DEBUG
3. Los errores se logean pero NO se propagan

**Solución:** Añadir print() además de logger para asegurar visibilidad

---

### Punto de Fallo #4: Problema con Tags JSON (MEDIA PROBABILIDAD)

**Ubicación:** `app/services/events_service.py` líneas 188-195

**Problema potencial:**
```python
tags_json = evento_raw.get('tags_json')
if tags_json:
    if isinstance(tags_json, str):
        tags = json.loads(tags_json)  # ¿Y si el JSON es inválido?
    else:
        tags = tags_json
else:
    tags = []
```

**Si el JSON es inválido:**
```python
tags_json = '["tag1", "tag2"'  # JSON incompleto
json.loads(tags_json)  # JSONDecodeError ✗
```

**Solución:** Try-except alrededor de json.loads()

---

### Punto de Fallo #5: Problema con Coordenadas (BAJA PROBABILIDAD)

**Ubicación:** `app/services/events_service.py` líneas 197-205

**Problema potencial:**
```python
if coords_usuario and evento_raw.get('latitud') and evento_raw.get('longitud'):
    distancia_km = self._calculate_distance(
        coords_usuario['lat'],  # ¿Y si coords_usuario no tiene 'lat'?
        coords_usuario['lng'],  # ¿Y si coords_usuario no tiene 'lng'?
        float(evento_raw['latitud']),  # ¿Y si latitud no es convertible a float?
        float(evento_raw['longitud'])
    )
```

**Solución:** Try-except alrededor del cálculo de distancia

---

### Punto de Fallo #6: Problema con get_coordenadas_cp (MEDIA PROBABILIDAD)

**Ubicación:** `app/services/events_service.py` línea 185

**Problema potencial:**
```python
coords_usuario = await db_service.get_coordenadas_cp(cp_usuario)
```

**Si esta función falla:**
- Lanza una excepción
- El `except` en línea 245 la captura
- TODOS los eventos se descartan

**Solución:** Try-except separado para get_coordenadas_cp

---

### Punto de Fallo #7: OpenAI No Responde Bien (BAJA PROBABILIDAD)

**Verificación necesaria:**

1. ¿OpenAI extrae parámetros correctos?
   - `conceptos: ["cuentacuentos"]` ✓ Parece correcto
   - `radio_km: 20` ✓ Razonable
   - `categorias: []` ✓ No extrae categorías (correcto)

2. ¿OpenAI genera embeddings correctos?
   - No podemos verificar sin acceso a la BD
   - Pero si `eventos_post_semantica: 10`, significa que SÍ funcionó

3. ¿OpenAI genera respuesta final?
   - `respuesta_texto: "Lo siento, no he encontrado..."` ✓ Funciona
   - Esto se genera DESPUÉS de la conversión
   - Si eventos = [], genera esta respuesta

**Conclusión:** OpenAI funciona correctamente. El problema NO está ahí.

---

### Punto de Fallo #8: Problema con continue en Validación (ALTA PROBABILIDAD)

**Ubicación:** `app/services/events_service.py` líneas 208-214

**Problema:**
```python
if not evento_raw.get('id_unico_evento'):
    logger.warning(f"Evento sin ID, saltando")
    continue  # ← Esto está DENTRO del try

if not evento_raw.get('titulo'):
    logger.warning(f"Evento {evento_raw.get('id_unico_evento')} sin título, saltando")
    continue  # ← Esto está DENTRO del try
```

**Si estos `continue` se ejecutan:**
- El evento se salta
- NO entra al `except`
- NO se loguea como error

**Pero el problema es:**
Si `id_unico_evento` o `titulo` son `None`, el `continue` se ejecuta y el evento se descarta.

**Verificación necesaria:** ¿Los eventos tienen `id_unico_evento` y `titulo`?

---

## 🎯 Hipótesis Principal

**Creo que el problema es una combinación de #1, #2 y #8:**

1. Los eventos tienen algún campo con valor `None` o tipo incorrecto
2. La validación de Pydantic falla
3. El `except` captura el error pero el log no se muestra
4. Los eventos se descartan silenciosamente

---

## 🛠️ Soluciones Propuestas (Orden de Prioridad)

### Solución #1: Hacer TODOS los Campos Opcionales (CRÍTICO)

**Archivo:** `app/models/schemas.py`

```python
class Evento(BaseModel):
    id_unico_evento: str  # Solo este es requerido
    titulo: Optional[str] = None  # ← Hacer opcional
    descripcion_corta: Optional[str] = None
    descripcion_larga: Optional[str] = None
    cp_evento: Optional[str] = None  # ← Hacer opcional
    poblacion_nombre: Optional[str] = None  # ← Hacer opcional
    lugar_nombre: Optional[str] = None
    direccion_completa: Optional[str] = None
    fecha_inicio: Optional[date] = None
    fecha_fin: Optional[date] = None
    hora_inicio: Optional[str] = None
    hora_fin: Optional[str] = None
    es_gratuito: Optional[bool] = False  # ← Hacer opcional con default
    precio_euros: Optional[float] = None
    categorias: List[str] = Field(default_factory=list)
    tags: List[str] = Field(default_factory=list)
    url_evento: Optional[str] = None
    url_imagen: Optional[str] = None
    distancia_km: Optional[float] = None
    similitud_score: Optional[float] = None
```

---

### Solución #2: Try-Except por Campo Individual (CRÍTICO)

**Archivo:** `app/services/events_service.py`

En lugar de un try-except global, hacer try-except por cada campo:

```python
# Crear modelo Evento con try-except por campo
try:
    id_unico_evento = str(evento_raw.get('id_unico_evento', ''))
except:
    id_unico_evento = ''

try:
    titulo = str(evento_raw.get('titulo', ''))
except:
    titulo = ''

try:
    fecha_inicio = evento_raw.get('fecha_inicio')
except:
    fecha_inicio = None

# ... etc para cada campo
```

---

### Solución #3: Añadir print() Además de logger (CRÍTICO)

**Archivo:** `app/services/events_service.py`

```python
except Exception as e:
    error_msg = f"Error al convertir evento {evento_raw.get('id_unico_evento')}: {e}"
    logger.error(error_msg)
    logger.error(f"Datos del evento: {evento_raw}")
    logger.exception("Stack trace completo:")
    
    # AÑADIR PRINT PARA ASEGURAR VISIBILIDAD
    print("=" * 80)
    print("ERROR EN CONVERSIÓN:")
    print(error_msg)
    print(f"Datos: {evento_raw}")
    print("=" * 80)
    
    continue
```

---

### Solución #4: Validación Más Laxa (ALTA PRIORIDAD)

**Archivo:** `app/services/events_service.py`

```python
# ANTES (estricto)
if not evento_raw.get('id_unico_evento'):
    logger.warning(f"Evento sin ID, saltando")
    continue

# DESPUÉS (laxo)
# Comentar estas validaciones temporalmente
# para ver si los eventos pasan
```

---

### Solución #5: Modo "Safe" de Conversión (ALTA PRIORIDAD)

Crear una función auxiliar que convierta cada campo de forma segura:

```python
def safe_get(evento_raw, key, tipo=str, default=None):
    """Obtiene un valor de forma segura con conversión de tipo."""
    try:
        valor = evento_raw.get(key)
        if valor is None:
            return default
        if tipo == str:
            return str(valor)
        elif tipo == float:
            return float(valor)
        elif tipo == bool:
            return bool(valor)
        else:
            return valor
    except Exception as e:
        logger.warning(f"Error al obtener {key}: {e}")
        return default

# Uso
titulo = safe_get(evento_raw, 'titulo', str, '')
precio = safe_get(evento_raw, 'precio_euros', float, None)
```

---

## 📋 Plan de Acción Inmediato

### Paso 1: Aplicar Solución #1 (Campos Opcionales)
- Hacer `titulo`, `cp_evento`, `poblacion_nombre` opcionales
- Hacer `es_gratuito` opcional con default False

### Paso 2: Aplicar Solución #3 (Print Statements)
- Añadir print() en el except para ver errores en consola

### Paso 3: Aplicar Solución #4 (Validación Laxa)
- Comentar las validaciones de `id_unico_evento` y `titulo`

### Paso 4: Reiniciar Backend y Probar
- Ver los prints en la consola
- Verificar si los eventos pasan

### Paso 5: Si Sigue Fallando, Aplicar Solución #2
- Try-except por campo individual
- Modo "ultra-safe"

---

## 🔬 Verificaciones Adicionales Necesarias

### Verificación #1: ¿Los Logs se Están Mostrando?

```bash
# En el terminal donde corre uvicorn
# ¿Ves estas líneas?
INFO: Iniciando conversión de 10 eventos raw a modelos Pydantic
INFO: Conversión completada: X eventos convertidos de 10 raw
```

**Si NO las ves:** El logging no está funcionando

### Verificación #2: ¿Qué Nivel de Log Está Configurado?

```bash
# Revisar .env
cat .env | grep LOG_LEVEL
```

**Si es WARNING o ERROR:** No verás los INFO y DEBUG

**Solución:** Cambiar a `LOG_LEVEL=DEBUG`

### Verificación #3: ¿Los Eventos Tienen Datos Válidos en la BD?

```sql
SELECT 
    ID_Unico_Evento,
    Titulo_ES,
    CP_Evento,
    Poblacion_Nombre,
    Es_Gratuito,
    Precio_Euros
FROM EVENTOS_MASTER
WHERE Estado = 'ACTIVO'
AND Titulo_ES LIKE '%Cuentacuentos%'
AND CP_Evento = '08360'
LIMIT 1;
```

**Verificar:**
- ¿`ID_Unico_Evento` es NOT NULL?
- ¿`Titulo_ES` es NOT NULL?
- ¿`CP_Evento` es NOT NULL?
- ¿`Poblacion_Nombre` es NOT NULL?

---

## 🎯 Conclusión

El problema MÁS PROBABLE es:

1. **Campos requeridos con valores NULL** → ValidationError de Pydantic
2. **Logging no visible** → No vemos los errores
3. **Validaciones estrictas** → Eventos descartados antes de intentar conversión

**Solución:** Hacer TODOS los campos opcionales y añadir prints para visibilidad.

---

**Próximo paso:** Aplicar las soluciones #1, #3 y #4 inmediatamente.
