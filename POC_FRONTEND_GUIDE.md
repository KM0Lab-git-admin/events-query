# 🚀 Guía de Uso - PoC Frontend React

## 📋 Resumen

Este PoC (Proof of Concept) implementa una interfaz web minimalista que permite:

1. **Ver todos los eventos disponibles** en la base de datos (lista simple)
2. **Hacer consultas en lenguaje natural** y ver la respuesta JSON de la API

## 🏗️ Arquitectura

```
┌─────────────────────────────────────────────────┐
│  Frontend (React + Vite)                        │
│  http://localhost:3000                          │
│                                                  │
│  ┌─────────────────┐  ┌────────────────────┐  │
│  │ EventsList      │  │ QueryChat          │  │
│  │ (GET /api/      │  │ (POST /query)      │  │
│  │  events/simple) │  │                    │  │
│  └─────────────────┘  └────────────────────┘  │
└─────────────────────────────────────────────────┘
                    ↓ Proxy (Vite)
┌─────────────────────────────────────────────────┐
│  Backend (FastAPI)                              │
│  http://localhost:8000                          │
│                                                  │
│  ┌─────────────────┐  ┌────────────────────┐  │
│  │ GET /api/       │  │ POST /query        │  │
│  │ events/simple   │  │                    │  │
│  └─────────────────┘  └────────────────────┘  │
└─────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────┐
│  MySQL Database                                 │
│  - 125 eventos fake                             │
│  - 5 ciudades                                   │
│  - 8 categorías                                 │
└─────────────────────────────────────────────────┘
                    ↓
┌─────────────────────────────────────────────────┐
│  OpenAI API                                     │
│  - Extracción de parámetros (GPT-4.1-mini)     │
│  - Embeddings (text-embedding-3-small)         │
│  - Respuesta en lenguaje natural               │
└─────────────────────────────────────────────────┘
```

## 🚀 Cómo Ejecutar

### Prerequisitos

1. ✅ MySQL corriendo con la base de datos `events_db`
2. ✅ Datos fake generados (125 eventos)
3. ✅ OpenAI API Key configurada en `.env`
4. ✅ Node.js y pnpm instalados

### Paso 1: Iniciar el Backend

```bash
# Terminal 1: Backend
cd /home/ubuntu/events-query

# Activar entorno virtual (si usas uno)
source venv/bin/activate

# Ejecutar FastAPI
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Verifica que el backend esté corriendo:
```bash
curl http://localhost:8000/health
```

### Paso 2: Iniciar el Frontend

```bash
# Terminal 2: Frontend
cd /home/ubuntu/events-query/frontend

# Ejecutar Vite dev server
pnpm dev
```

### Paso 3: Abrir en el Navegador

Abre tu navegador en: **http://localhost:3000**

## 📊 Flujo de Uso

### 1. Ver Eventos Disponibles

Al cargar la página, verás:
- **Estadísticas**: Total de eventos, gratuitos, de pago
- **Lista de eventos**: Scroll para ver los 125 eventos con:
  - Título
  - Ubicación (ciudad + código postal)
  - Fecha y hora
  - Precio (gratis o de pago)
  - Categorías

**Objetivo:** Conocer qué eventos hay para poder hacer preguntas relevantes.

### 2. Hacer Consultas en Lenguaje Natural

**Sección inferior: Chat de Consultas**

1. **Escribe una pregunta** en el input principal
   - Ejemplo: "¿Qué hacer este fin de semana?"
   - Ejemplo: "Eventos gratuitos para niños"
   - Ejemplo: "Conciertos de música en mi zona"

2. **Ingresa tu código postal**
   - Por defecto: 08380 (Malgrat de Mar)
   - Puedes cambiarlo a: 08370 (Calella), 17300 (Blanes), etc.

3. **Click en "Buscar"**

4. **Espera la respuesta** (1-3 segundos)
   - OpenAI procesa tu pregunta
   - Extrae parámetros (fechas, categorías, conceptos)
   - Busca eventos relevantes en la BD
   - Genera respuesta en lenguaje natural

5. **Revisa el resultado:**
   - **Respuesta en lenguaje natural** (texto generado por IA)
   - **Total de eventos encontrados**
   - **JSON completo** con todos los detalles

## 🧪 Ejemplos de Prueba

### Ejemplo 1: Búsqueda Básica

**Pregunta:** "¿Qué hacer este fin de semana?"  
**CP:** 08380  

**Resultado esperado:**
- Eventos en Malgrat de Mar (08380)
- Fechas cercanas al fin de semana actual
- Respuesta en español con lista de eventos

### Ejemplo 2: Búsqueda con Filtro de Categoría

**Pregunta:** "Eventos de cultura para adultos"  
**CP:** 08370  

**Resultado esperado:**
- Eventos de categoría "Cultura"
- En Calella (08370) o cerca
- Filtrados semánticamente

### Ejemplo 3: Búsqueda con Filtro de Precio

**Pregunta:** "Actividades gratuitas para niños"  
**CP:** 17300  

**Resultado esperado:**
- Eventos gratuitos (es_gratuito = true)
- Categoría "Infantil"
- En Blanes (17300) o cerca

### Ejemplo 4: Búsqueda en Catalán

**Pregunta:** "Què fer aquest cap de setmana?"  
**CP:** 08380  

**Resultado esperado:**
- Respuesta en catalán
- Eventos con títulos en catalán
- Misma funcionalidad que en español

## 📁 Archivos Creados

### Backend (modificado)
```
app/api/routes.py
  └─ Añadido: GET /api/events/simple
```

### Frontend (nuevo)
```
frontend/
├── src/
│   ├── App.jsx           # Componente principal
│   ├── EventsList.jsx    # Lista de eventos
│   ├── QueryChat.jsx     # Chat de consultas
│   ├── main.jsx          # Entry point
│   └── index.css         # Estilos
├── index.html
├── vite.config.js        # Proxy configurado
├── package.json
└── README.md
```

## 🔧 Configuración Técnica

### Proxy de Vite

El frontend usa un proxy para evitar problemas de CORS:

```javascript
// vite.config.js
server: {
  port: 3000,
  proxy: {
    '/api': 'http://localhost:8000',
    '/query': 'http://localhost:8000',
    '/health': 'http://localhost:8000'
  }
}
```

Esto significa que:
- `http://localhost:3000/api/events/simple` → `http://localhost:8000/api/events/simple`
- `http://localhost:3000/query` → `http://localhost:8000/query`

### CORS en Backend

El backend ya tiene CORS configurado en `app/main.py`:

```python
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # En desarrollo
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)
```

## 🐛 Troubleshooting

### Error: "Failed to fetch"

**Causa:** El backend no está corriendo o no está accesible.

**Solución:**
```bash
# Verifica que el backend esté corriendo
curl http://localhost:8000/health

# Si no responde, inicia el backend
cd /home/ubuntu/events-query
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### Error: "No hay eventos disponibles"

**Causa:** La base de datos está vacía.

**Solución:**
```bash
# Genera datos fake
cd /home/ubuntu/events-query
python scripts/generate_fake_data.py
```

### Error: "OpenAI API key not configured"

**Causa:** La variable de entorno `OPENAI_API_KEY` no está configurada.

**Solución:**
```bash
# Edita el archivo .env
cd /home/ubuntu/events-query
nano .env

# Añade:
OPENAI_API_KEY=tu_api_key_aqui

# Reinicia el backend
```

### Error: "Database pool not initialized"

**Causa:** MySQL no está corriendo o las credenciales son incorrectas.

**Solución:**
```bash
# Verifica que MySQL esté corriendo
sudo systemctl status mysql

# Verifica las credenciales en .env
cat .env | grep DB_
```

### El frontend no carga (puerto 3000)

**Causa:** El puerto 3000 está ocupado o Vite no se inició correctamente.

**Solución:**
```bash
# Verifica que no haya otro proceso en el puerto 3000
lsof -i :3000

# Si hay un proceso, mátalo
kill -9 <PID>

# Reinicia el frontend
cd /home/ubuntu/events-query/frontend
pnpm dev
```

## 📊 Datos de Prueba

Los datos fake generados incluyen:

- **5 ciudades:**
  - Malgrat de Mar (08380)
  - Calella (08370)
  - Canet de Mar (08360)
  - Pineda de Mar (08397)
  - Blanes (17300)

- **125 eventos** (25 por ciudad)

- **8 categorías:**
  - Cultura
  - Deportes
  - Ocio
  - Infantil
  - Formación
  - Gastronomía
  - Música
  - Naturaleza

- **Fechas:** Distribuidas en los próximos 30 días

- **Precios:** Mix de eventos gratuitos y de pago (0€ - 50€)

## 🎯 Próximos Pasos (Fuera del PoC)

Este PoC es minimalista. Para una versión completa, se podría añadir:

- [ ] Tabla con filtros avanzados (ordenar, paginar)
- [ ] Vista de detalle de cada evento (modal)
- [ ] Gráficos y estadísticas
- [ ] Historial de búsquedas
- [ ] Exportación de resultados (CSV, JSON)
- [ ] Modo debug en el chat
- [ ] Autenticación de usuarios
- [ ] Favoritos de eventos

## 📝 Notas Importantes

1. **Este es un PoC:** El código es minimalista y no está optimizado para producción.

2. **Sin autenticación:** No hay control de acceso, cualquiera puede usar la API.

3. **CORS abierto:** En desarrollo, CORS está configurado con `allow_origins=["*"]`. En producción, deberías restringir esto.

4. **Sin rate limiting:** No hay límite de requests. En producción, deberías añadir rate limiting.

5. **Datos fake:** Los eventos son generados automáticamente y no son reales.

## ✅ Checklist de Verificación

Antes de probar el PoC, verifica:

- [ ] MySQL está corriendo
- [ ] Base de datos `events_db` existe
- [ ] Datos fake generados (125 eventos)
- [ ] `.env` configurado con `OPENAI_API_KEY`
- [ ] Backend corriendo en puerto 8000
- [ ] Frontend corriendo en puerto 3000
- [ ] Navegador abierto en http://localhost:3000

## 📞 Soporte

Si tienes problemas:

1. Revisa los logs del backend (terminal donde corre uvicorn)
2. Revisa la consola del navegador (F12 → Console)
3. Verifica que todos los servicios estén corriendo
4. Consulta la sección de Troubleshooting

---

**Versión:** 1.0  
**Fecha:** Enero 2026  
**Estado:** PoC Funcional ✅
