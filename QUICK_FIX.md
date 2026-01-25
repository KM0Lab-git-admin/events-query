# 🚀 Quick Fix - Solución Rápida

## Problema
La query "Cuentacuentos en la biblioteca" no encuentra eventos.

## Solución en 3 Pasos (5 minutos)

### 1️⃣ Reducir Umbral de Similitud

**Archivo:** `app/services/events_service.py`

**Línea 152, cambiar:**
```python
# ANTES
eventos_filtrados = [e for e in eventos_con_score if e['similitud_score'] >= 0.6]

# DESPUÉS
eventos_filtrados = [e for e in eventos_con_score if e['similitud_score'] >= 0.4]
```

### 2️⃣ Activar Debug Mode

**Archivo:** `frontend/src/QueryChat.jsx`

**Línea 32, cambiar:**
```javascript
// ANTES
debug: false

// DESPUÉS
debug: true
```

### 3️⃣ Reiniciar Backend y Frontend

```bash
# Terminal 1: Backend
cd /home/ubuntu/events-query
# Ctrl+C para parar
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000

# Terminal 2: Frontend
cd /home/ubuntu/events-query/frontend
# Ctrl+C para parar
pnpm dev
```

---

## Probar de Nuevo

1. Abre http://localhost:3000
2. Escribe: "Cuentacuentos en la biblioteca"
3. CP: 08360
4. Click "Buscar"
5. Revisa el JSON completo para ver los parámetros extraídos

---

## Si Sigue Sin Funcionar

Ver el informe completo: `INFORME_DIAGNOSTICO_QUERY.md`

O ejecutar el script de diagnóstico:
```bash
cd /home/ubuntu/events-query
python3 test_query_debug.py
```

---

**Tiempo estimado:** 5 minutos  
**Probabilidad de éxito:** 80%
