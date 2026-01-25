# 🔧 Troubleshooting - Análisis Detallado No Se Muestra

**Fecha:** 25 de enero de 2026  
**Problema:** El análisis detallado no aparece en el frontend después de hacer una búsqueda

---

## ✅ Cambios Aplicados

He añadido logs de depuración en 3 lugares:

1. **QueryChat.jsx** (líneas 49-57)
   - Log de `data.debug_info`
   - Log de `analisis_detallado`
   - Log al llamar `onAnalysisUpdate`

2. **App.jsx** (líneas 10-12)
   - Log al recibir análisis
   - Log de cantidad de eventos

3. **AnalysisView.jsx** (líneas 6-7)
   - Log al renderizar componente
   - Log de `analisis.length`

---

## 🧪 Cómo Diagnosticar

### Paso 1: Actualizar Código

```bash
cd /ruta/a/tu/events-query
git pull origin feature/frontend-poc
```

### Paso 2: Reiniciar Frontend

**IMPORTANTE:** Debes reiniciar el frontend para que los cambios se apliquen.

```bash
# En la terminal donde está corriendo el frontend
# Presiona Ctrl+C para detener

cd events-query/frontend
pnpm dev
```

### Paso 3: Abrir Consola del Navegador

1. Abre http://localhost:3000
2. Presiona **F12** (o clic derecho → Inspeccionar)
3. Ve a la pestaña **Console**

### Paso 4: Hacer una Búsqueda

1. Escribe: "Actividades relacionadas con comida?"
2. CP: 08380
3. Click "Buscar"
4. **Observa los logs en la consola**

---

## 📊 Interpretando los Logs

### Escenario 1: Todo Funciona ✅

```
DEBUG: data.debug_info = { parametros_extraidos: {...}, analisis_detallado: [...] }
DEBUG: analisis_detallado = Array(20)
DEBUG: Llamando onAnalysisUpdate con 20 eventos
DEBUG App: Recibiendo análisis con 20 eventos
DEBUG App: Datos completos = Array(20) [...]
DEBUG AnalysisView: Recibiendo analisis = Array(20)
DEBUG AnalysisView: analisis.length = 20
```

**Resultado:** Deberías ver el análisis detallado en la página.

---

### Escenario 2: No Hay Análisis (Array Vacío) ⚠️

```
DEBUG: data.debug_info = { parametros_extraidos: {...}, analisis_detallado: [] }
DEBUG: analisis_detallado = Array(0)
DEBUG: NO se llama onAnalysisUpdate
```

**Causa:** El backend no generó análisis.

**Posibles razones:**
1. No hay `conceptos` extraídos por OpenAI
2. No hay eventos en la BD con ese CP
3. El análisis se genera solo si hay `conceptos` Y eventos

**Solución:**
- Verifica que OpenAI extrajo conceptos: mira `parametros_extraidos.conceptos`
- Verifica que hay eventos: mira `eventos_pre_filtrado` en debug_info
- Si ambos existen pero `analisis_detallado` está vacío, hay un bug en el backend

---

### Escenario 3: No Hay debug_info ❌

```
DEBUG: data.debug_info = undefined
DEBUG: analisis_detallado = undefined
DEBUG: NO se llama onAnalysisUpdate
```

**Causa:** El backend no está devolviendo `debug_info`.

**Posibles razones:**
1. `debug: true` no se está enviando en el request
2. El backend tiene un error y no genera debug_info

**Solución:**
- Verifica en QueryChat.jsx línea 36: debe ser `debug: true`
- Revisa los logs del backend (terminal 1) para ver si hay errores

---

### Escenario 4: Error en el Backend 🔥

```
Error en query: Error: 500 Internal Server Error
```

**Causa:** El backend lanzó una excepción.

**Solución:**
- Ve a la terminal del backend (terminal 1)
- Busca el stack trace del error
- Probablemente es un error en `analysis_service.py`

---

## 🔍 Verificaciones Adicionales

### 1. Verificar que `debug: true` se envía

**Archivo:** `frontend/src/QueryChat.jsx` línea 36

```javascript
body: JSON.stringify({
  pregunta: pregunta,
  cp_usuario: cpUsuario,
  debug: true  // ← Debe estar en true
})
```

### 2. Verificar que el backend genera análisis

**Archivo:** `app/services/events_service.py` líneas 84-107

```python
if request.debug:
    analisis_detallado = []
    if params.conceptos and eventos_raw:  # ← Debe cumplirse
        # ...
        analisis_detallado = await analysis_service.analyze_batch(...)
    
    response.debug_info = {
        ...
        "analisis_detallado": analisis_detallado  # ← Debe estar aquí
    }
```

### 3. Verificar que AnalysisView se importa

**Archivo:** `frontend/src/App.jsx` líneas 1-4

```javascript
import { useState } from 'react'
import EventsList from './EventsList'
import QueryChat from './QueryChat'
import AnalysisView from './AnalysisView'  // ← Debe estar importado
```

### 4. Verificar que AnalysisView se renderiza

**Archivo:** `frontend/src/App.jsx` línea 24

```javascript
{analysisData && <AnalysisView analisis={analysisData} />}
```

---

## 🐛 Problemas Conocidos

### Problema 1: Análisis Vacío Aunque Hay Eventos

**Síntoma:** `eventos_pre_filtrado: 50` pero `analisis_detallado: []`

**Causa:** OpenAI no extrajo `conceptos` de la pregunta.

**Ejemplo:**
```
Pregunta: "Hola"
Conceptos extraídos: []  ← No hay conceptos
Análisis: []  ← No se genera
```

**Solución:** Haz preguntas más específicas con conceptos claros.

---

### Problema 2: Solo Analiza Eventos que Pasaron el Filtro

**Síntoma:** Solo ves 5 eventos en el análisis, pero esperabas ver todos.

**Causa:** El código actual analiza `eventos_raw[:20]`, pero si hay pocos eventos que pasaron el filtro, verás menos.

**Solución:** Esto es por diseño. El análisis se hace ANTES del filtro semántico, por lo que deberías ver hasta 20 eventos (incluso los que no pasaron).

Si ves menos de 20, es porque hay menos de 20 eventos en el pre-filtrado SQL.

---

### Problema 3: Error "Cannot read property 'length' of undefined"

**Síntoma:** Error en la consola del navegador.

**Causa:** `analisis` es `undefined` en lugar de `null` o `[]`.

**Solución:** Ya está manejado en AnalysisView línea 9:
```javascript
if (!analisis || analisis.length === 0) {
  return <div>No hay análisis disponible</div>
}
```

---

## 📝 Checklist de Verificación

Antes de reportar un problema, verifica:

- [ ] He hecho `git pull origin feature/frontend-poc`
- [ ] He reiniciado el frontend (`Ctrl+C` + `pnpm dev`)
- [ ] He abierto la consola del navegador (F12)
- [ ] He hecho una búsqueda y revisado los logs
- [ ] He verificado que `debug: true` en QueryChat.jsx línea 36
- [ ] He verificado que hay eventos en la BD (`eventos_pre_filtrado > 0`)
- [ ] He verificado que OpenAI extrajo conceptos (`conceptos.length > 0`)
- [ ] He revisado los logs del backend (terminal 1) para errores

---

## 🆘 Si Nada Funciona

Si después de todo esto el análisis no se muestra:

1. **Copia TODOS los logs de la consola del navegador**
2. **Copia los logs del backend (terminal 1)**
3. **Copia el JSON completo de la respuesta** (está en QueryChat, sección "Ver JSON completo")
4. **Envíame toda esta información**

Con eso podré identificar exactamente dónde está el problema.

---

## 🔄 Próximos Pasos

Una vez que veas los logs, sabremos:

1. ✅ Si el backend genera análisis
2. ✅ Si el frontend lo recibe
3. ✅ Si AnalysisView se renderiza
4. ✅ Dónde está el problema exacto

---

**Autor:** Manus AI  
**Fecha:** 25 de enero de 2026  
**Versión:** 1.0
