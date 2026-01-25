# Plan de Implementación - Frontend Web para Events Query API

**Fecha:** Enero 2026  
**Versión:** 1.0  
**Estado:** 📋 Propuesta para Aprobación

---

## 📋 Resumen Ejecutivo

Este documento presenta un plan detallado para implementar una interfaz web completa que permita:

1. **Chat de Consultas en Lenguaje Natural**: Interfaz conversacional donde el usuario puede hacer preguntas y recibir respuestas con eventos relevantes en formato JSON visualizado.

2. **Visualizador de Datos de Base de Datos**: Panel administrativo para explorar, filtrar y ordenar todas las tablas de la base de datos, especialmente los 125 eventos fake generados.

---

## 🎯 Análisis de Requisitos

### Requisito 1: Chat de Consultas en Lenguaje Natural

**Descripción del Usuario:**
> "Yo pongo una pregunta en una URL dentro de un HTML, un input, pongo una pregunta y se cumple con todo el proceso. Eso sería una parte."

**Funcionalidades Requeridas:**
- ✅ Input de texto para escribir preguntas en lenguaje natural
- ✅ Botón para enviar la consulta
- ✅ Campo para ingresar código postal del usuario
- ✅ Visualización de la respuesta de la API en formato JSON legible
- ✅ Mostrar tanto el texto de respuesta como los eventos encontrados
- ✅ Soporte para español y catalán
- ✅ Indicador de carga mientras se procesa la consulta

### Requisito 2: Visualizador de Datos de Base de Datos

**Descripción del Usuario:**
> "Poder ver los datos fake que están en la base de datos, poder pintarlos y filtrarlos. Poder ver, mira, esta es la tabla, se han generado estos 150 eventos y, pues, puedo ver la tabla, ordenar, filtrar, un poco de funcionalidad sobre lo que puedo ver en esa tabla."

**Funcionalidades Requeridas:**

#### Tabla Principal: EVENTOS_MASTER
- ✅ Visualización en tabla con paginación
- ✅ Ordenamiento por columnas (título, fecha, precio, categoría, etc.)
- ✅ Filtros múltiples:
  - Por código postal
  - Por ciudad/población
  - Por categoría (Cultura, Deportes, Ocio, Infantil, etc.)
  - Por rango de fechas
  - Por precio (gratuito, rango de precios)
  - Por idioma (español/catalán)
- ✅ Búsqueda por texto en título y descripción
- ✅ Vista detallada de cada evento (modal o página)
- ✅ Contador de eventos totales y filtrados
- ✅ Exportación de datos (CSV/JSON)

#### Tablas Secundarias (Vista de Catálogos)
- ✅ **CIUDADES**: Listado de ciudades con coordenadas
- ✅ **CODIGOS_POSTALES**: Listado de CPs con su ciudad asociada
- ✅ **CATEGORIAS**: Catálogo de 8 categorías con colores e iconos
- ✅ **EVENTO_HORARIOS**: Horarios asociados a eventos
- ✅ Estadísticas básicas (contadores, gráficos simples)

---

## 🏗️ Arquitectura Propuesta

### Opción A: Frontend Separado (SPA) ⭐ RECOMENDADA

**Stack Tecnológico:**
```
Frontend:
- React 18 + TypeScript
- Vite (build tool)
- TailwindCSS (estilos)
- TanStack Table (tablas con filtros/ordenamiento)
- Axios (HTTP client)
- React Router (navegación)
- Recharts o Chart.js (gráficos estadísticos)

Backend:
- FastAPI (ya implementado)
- Nuevos endpoints para listar/filtrar datos
```

**Estructura de Directorios:**
```
events-query/
├── app/                    # Backend FastAPI (ya existe)
├── frontend/               # Nueva carpeta para frontend
│   ├── src/
│   │   ├── components/
│   │   │   ├── Chat/
│   │   │   │   ├── ChatInterface.tsx
│   │   │   │   ├── MessageList.tsx
│   │   │   │   └── QueryInput.tsx
│   │   │   ├── DataViewer/
│   │   │   │   ├── EventsTable.tsx
│   │   │   │   ├── TableFilters.tsx
│   │   │   │   ├── EventDetail.tsx
│   │   │   │   └── StatsCards.tsx
│   │   │   ├── Catalogs/
│   │   │   │   ├── CitiesTable.tsx
│   │   │   │   ├── PostalCodesTable.tsx
│   │   │   │   └── CategoriesTable.tsx
│   │   │   └── Layout/
│   │   │       ├── Header.tsx
│   │   │       ├── Sidebar.tsx
│   │   │       └── Footer.tsx
│   │   ├── pages/
│   │   │   ├── ChatPage.tsx
│   │   │   ├── EventsViewerPage.tsx
│   │   │   ├── CatalogsPage.tsx
│   │   │   └── StatsPage.tsx
│   │   ├── services/
│   │   │   └── api.ts
│   │   ├── types/
│   │   │   └── events.ts
│   │   ├── App.tsx
│   │   └── main.tsx
│   ├── package.json
│   └── vite.config.ts
├── docker-compose.yml      # Actualizar para incluir frontend
└── README.md
```

**Ventajas:**
- ✅ Separación clara de responsabilidades
- ✅ Mejor experiencia de usuario (SPA rápida)
- ✅ Fácil de escalar y mantener
- ✅ Reutilización de componentes
- ✅ TypeScript para type safety

**Desventajas:**
- ⚠️ Requiere build process
- ⚠️ Más complejo que HTML simple

---

### Opción B: HTML Estático con JavaScript Vanilla

**Stack Tecnológico:**
```
Frontend:
- HTML5 + CSS3 (o TailwindCSS CDN)
- JavaScript Vanilla (ES6+)
- Fetch API para llamadas HTTP
- DataTables.js (tablas con filtros)

Backend:
- FastAPI (ya implementado)
- Servir archivos estáticos desde FastAPI
```

**Estructura:**
```
events-query/
├── app/
│   └── static/
│       ├── index.html          # Chat de consultas
│       ├── viewer.html         # Visualizador de datos
│       ├── catalogs.html       # Catálogos
│       ├── css/
│       │   └── styles.css
│       └── js/
│           ├── chat.js
│           ├── viewer.js
│           └── api.js
```

**Ventajas:**
- ✅ Más simple, sin build process
- ✅ Fácil de entender y modificar
- ✅ Menos dependencias

**Desventajas:**
- ⚠️ Menos escalable
- ⚠️ Código más difícil de mantener a largo plazo
- ⚠️ Sin type safety

---

## 📐 Diseño de Interfaz (Wireframes Conceptuales)

### Página 1: Chat de Consultas

```
┌─────────────────────────────────────────────────────────────┐
│  Events Query API - Chat de Búsqueda                        │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  ┌────────────────────────────────────────────────────┐    │
│  │  Historial de Conversación                         │    │
│  │                                                     │    │
│  │  [Usuario] ¿Qué hacer este fin de semana?         │    │
│  │                                                     │    │
│  │  [Sistema] He encontrado 5 eventos para ti...     │    │
│  │  {                                                 │    │
│  │    "respuesta_texto": "...",                       │    │
│  │    "eventos": [...]                                │    │
│  │  }                                                 │    │
│  │                                                     │    │
│  └────────────────────────────────────────────────────┘    │
│                                                              │
│  ┌─────────────────────────┬──────────────┬──────────┐     │
│  │ Tu pregunta...          │ CP: 08380    │ [Enviar] │     │
│  └─────────────────────────┴──────────────┴──────────┘     │
│                                                              │
│  [x] Modo Debug (mostrar parámetros extraídos)             │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

**Características:**
- Input principal para la pregunta
- Campo separado para código postal
- Checkbox para activar modo debug
- Historial de preguntas y respuestas
- JSON formateado con syntax highlighting
- Tarjetas visuales para cada evento encontrado

---

### Página 2: Visualizador de Eventos

```
┌─────────────────────────────────────────────────────────────┐
│  Events Query API - Visualizador de Eventos                 │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  📊 Estadísticas: 125 eventos totales | 25 filtrados        │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ Filtros:                                             │  │
│  │ [Buscar...] [CP: Todos ▼] [Categoría: Todas ▼]     │  │
│  │ [Gratuito: Todos ▼] [Fecha desde] [Fecha hasta]    │  │
│  │ [Limpiar filtros]                                    │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ Título ↕ │ Población ↕ │ Fecha ↕ │ Precio ↕ │ ...  │  │
│  ├──────────────────────────────────────────────────────┤  │
│  │ Cineclub │ Malgrat    │ 26/01  │ 6.00€  │ [Ver]   │  │
│  │ Taller   │ Calella    │ 27/01  │ Gratis │ [Ver]   │  │
│  │ Concierto│ Blanes     │ 28/01  │ 15.00€ │ [Ver]   │  │
│  │ ...                                                  │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                              │
│  [Anterior] Página 1 de 5 [Siguiente]                      │
│  [Exportar CSV] [Exportar JSON]                            │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

**Características:**
- Filtros múltiples en la parte superior
- Tabla con ordenamiento por columnas
- Paginación (10-25 eventos por página)
- Botón para ver detalle de cada evento
- Exportación de datos
- Contadores de estadísticas

---

### Página 3: Vista Detalle de Evento (Modal)

```
┌─────────────────────────────────────────────────────────────┐
│  Detalle del Evento                                    [X]  │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  🎭 Cineclub: Clásicos del cine                             │
│                                                              │
│  📍 Ubicación:                                              │
│     Malgrat de Mar (08380)                                  │
│     Cinema Malgrat, Carrer Principal 123                    │
│                                                              │
│  📅 Fecha y Hora:                                           │
│     26 de enero de 2026, 21:00 - 23:00                     │
│                                                              │
│  💰 Precio: 6.00€                                           │
│                                                              │
│  📝 Descripción:                                            │
│     Proyección de clásicos del cine español...             │
│                                                              │
│  🏷️ Categorías: Cultura                                    │
│                                                              │
│  #️⃣ Tags: #cine #clasicos #cultura #malgrat               │
│                                                              │
│  🔗 [Comprar entradas]                                      │
│                                                              │
│  ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━    │
│                                                              │
│  📊 Datos Técnicos (JSON):                                  │
│  {                                                           │
│    "id_unico_evento": "abc123...",                          │
│    "titulo_es": "Cineclub: Clásicos del cine",             │
│    "tags_es": ["#cine", "#clasicos"],                      │
│    ...                                                       │
│  }                                                           │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

### Página 4: Catálogos y Estadísticas

```
┌─────────────────────────────────────────────────────────────┐
│  Events Query API - Catálogos                               │
├─────────────────────────────────────────────────────────────┤
│                                                              │
│  [Ciudades] [Códigos Postales] [Categorías] [Horarios]     │
│                                                              │
│  ━━━ Ciudades (5 total) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│                                                              │
│  ┌──────────────────────────────────────────────────────┐  │
│  │ Nombre          │ Provincia  │ Eventos │ Latitud    │  │
│  ├──────────────────────────────────────────────────────┤  │
│  │ Malgrat de Mar  │ Barcelona  │ 25      │ 41.6458   │  │
│  │ Calella         │ Barcelona  │ 25      │ 41.6144   │  │
│  │ Canet de Mar    │ Barcelona  │ 25      │ 41.5897   │  │
│  │ Pineda de Mar   │ Barcelona  │ 25      │ 41.6272   │  │
│  │ Blanes          │ Girona     │ 25      │ 41.6750   │  │
│  └──────────────────────────────────────────────────────┘  │
│                                                              │
│  ━━━ Categorías (8 total) ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│                                                              │
│  🎨 Cultura (15 eventos)                                    │
│  ⚽ Deportes (18 eventos)                                   │
│  🎉 Ocio (20 eventos)                                       │
│  👶 Infantil (22 eventos)                                   │
│  📚 Formación (12 eventos)                                  │
│  🍽️ Gastronomía (16 eventos)                               │
│  🎵 Música (14 eventos)                                     │
│  🌳 Naturaleza (8 eventos)                                  │
│                                                              │
│  ━━━ Gráficos ━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━  │
│                                                              │
│  [Gráfico de barras: Eventos por categoría]                │
│  [Gráfico de pastel: Eventos gratuitos vs de pago]         │
│  [Línea temporal: Eventos por fecha]                        │
│                                                              │
└─────────────────────────────────────────────────────────────┘
```

---

## 🔌 Nuevos Endpoints de Backend Necesarios

Para soportar el visualizador de datos, necesitamos añadir estos endpoints a la API:

### 1. Listar Eventos con Filtros
```
GET /api/events
Query params:
  - page: int (default: 1)
  - page_size: int (default: 25, max: 100)
  - cp: str (opcional)
  - ciudad: str (opcional)
  - categoria: int[] (opcional, IDs de categorías)
  - fecha_desde: date (opcional)
  - fecha_hasta: date (opcional)
  - es_gratuito: bool (opcional)
  - precio_min: float (opcional)
  - precio_max: float (opcional)
  - search: str (opcional, busca en título y descripción)
  - sort_by: str (default: "fecha_inicio")
  - sort_order: str (default: "asc")
  - idioma: str (default: "es", opciones: "es", "ca")

Response:
{
  "eventos": [...],
  "total": 125,
  "page": 1,
  "page_size": 25,
  "total_pages": 5
}
```

### 2. Obtener Detalle de Evento
```
GET /api/events/{id_unico_evento}
Query params:
  - idioma: str (default: "es")

Response:
{
  "evento": {...},
  "horarios": [...],
  "categorias": [...]
}
```

### 3. Listar Ciudades
```
GET /api/ciudades

Response:
{
  "ciudades": [
    {
      "id_ciudad": 1,
      "nombre": "Malgrat de Mar",
      "provincia": "Barcelona",
      "latitud": 41.6458,
      "longitud": 2.7436,
      "total_eventos": 25
    },
    ...
  ]
}
```

### 4. Listar Códigos Postales
```
GET /api/codigos-postales
Query params:
  - id_ciudad: int (opcional)

Response:
{
  "codigos_postales": [
    {
      "cp": "08380",
      "ciudad": "Malgrat de Mar",
      "latitud": 41.6458,
      "longitud": 2.7436,
      "total_eventos": 25
    },
    ...
  ]
}
```

### 5. Listar Categorías
```
GET /api/categorias
Query params:
  - idioma: str (default: "es")

Response:
{
  "categorias": [
    {
      "id_categoria": 1,
      "nombre": "Cultura",
      "slug": "cultura",
      "icono": "palette",
      "color_hex": "#9C27B0",
      "total_eventos": 15
    },
    ...
  ]
}
```

### 6. Estadísticas Generales
```
GET /api/stats

Response:
{
  "total_eventos": 125,
  "total_ciudades": 5,
  "total_categorias": 8,
  "eventos_gratuitos": 45,
  "eventos_de_pago": 80,
  "precio_promedio": 12.50,
  "eventos_por_categoria": {
    "Cultura": 15,
    "Deportes": 18,
    ...
  },
  "eventos_por_ciudad": {
    "Malgrat de Mar": 25,
    "Calella": 25,
    ...
  }
}
```

---

## 📝 Plan de Implementación Detallado

### Fase 1: Setup y Estructura Base (2-3 horas)

**Backend:**
1. ✅ Crear nuevos endpoints en `app/api/routes.py`
2. ✅ Crear servicios de datos en `app/services/data_service.py`
3. ✅ Añadir modelos Pydantic para responses en `app/models/schemas.py`
4. ✅ Configurar CORS para permitir requests desde frontend
5. ✅ Añadir endpoint para servir archivos estáticos (si Opción B)

**Frontend (Opción A - React):**
1. ✅ Crear carpeta `frontend/` con Vite + React + TypeScript
2. ✅ Instalar dependencias (TailwindCSS, TanStack Table, Axios, etc.)
3. ✅ Configurar estructura de carpetas
4. ✅ Crear servicio de API (`services/api.ts`)
5. ✅ Definir tipos TypeScript (`types/events.ts`)

**Frontend (Opción B - HTML):**
1. ✅ Crear carpeta `app/static/`
2. ✅ Crear archivos HTML base (index.html, viewer.html, catalogs.html)
3. ✅ Configurar TailwindCSS (CDN o build)
4. ✅ Crear módulo de API en JavaScript (`js/api.js`)

---

### Fase 2: Chat de Consultas (3-4 horas)

**Frontend:**
1. ✅ Crear componente de input para pregunta y CP
2. ✅ Implementar llamada al endpoint POST /query
3. ✅ Crear componente para mostrar historial de conversación
4. ✅ Implementar visualización de JSON con syntax highlighting
5. ✅ Añadir indicador de carga
6. ✅ Implementar modo debug (mostrar parámetros extraídos)
7. ✅ Crear tarjetas visuales para eventos encontrados
8. ✅ Añadir manejo de errores

**Testing:**
- ✅ Probar con preguntas en español
- ✅ Probar con preguntas en catalán
- ✅ Verificar modo debug
- ✅ Probar con diferentes códigos postales

---

### Fase 3: Visualizador de Eventos (4-5 horas)

**Backend:**
1. ✅ Implementar endpoint GET /api/events con filtros
2. ✅ Implementar endpoint GET /api/events/{id}
3. ✅ Añadir queries SQL con filtros dinámicos
4. ✅ Implementar paginación
5. ✅ Implementar ordenamiento

**Frontend:**
1. ✅ Crear tabla de eventos con TanStack Table (o DataTables.js)
2. ✅ Implementar filtros múltiples (CP, categoría, fecha, precio)
3. ✅ Implementar ordenamiento por columnas
4. ✅ Implementar paginación
5. ✅ Crear modal/página de detalle de evento
6. ✅ Añadir búsqueda por texto
7. ✅ Implementar exportación CSV/JSON
8. ✅ Añadir contadores de estadísticas

**Testing:**
- ✅ Probar todos los filtros
- ✅ Verificar ordenamiento
- ✅ Probar paginación
- ✅ Verificar vista de detalle

---

### Fase 4: Catálogos y Estadísticas (2-3 horas)

**Backend:**
1. ✅ Implementar endpoint GET /api/ciudades
2. ✅ Implementar endpoint GET /api/codigos-postales
3. ✅ Implementar endpoint GET /api/categorias
4. ✅ Implementar endpoint GET /api/stats

**Frontend:**
1. ✅ Crear tabla de ciudades
2. ✅ Crear tabla de códigos postales
3. ✅ Crear vista de categorías con iconos y colores
4. ✅ Crear dashboard de estadísticas
5. ✅ Añadir gráficos (Recharts o Chart.js):
   - Eventos por categoría (barras)
   - Eventos gratuitos vs de pago (pastel)
   - Eventos por ciudad (barras)
   - Timeline de eventos (línea)

**Testing:**
- ✅ Verificar datos de catálogos
- ✅ Probar gráficos con datos reales

---

### Fase 5: Navegación y Layout (1-2 horas)

**Frontend:**
1. ✅ Crear header con navegación
2. ✅ Crear sidebar (opcional)
3. ✅ Implementar routing entre páginas
4. ✅ Añadir breadcrumbs
5. ✅ Diseño responsive (mobile-friendly)
6. ✅ Añadir tema oscuro/claro (opcional)

---

### Fase 6: Pulido y Deployment (1-2 horas)

1. ✅ Revisar estilos y UX
2. ✅ Optimizar performance
3. ✅ Añadir loading skeletons
4. ✅ Mejorar manejo de errores
5. ✅ Actualizar docker-compose.yml para incluir frontend
6. ✅ Documentar en README.md
7. ✅ Testing end-to-end

---

## ⏱️ Estimación de Tiempo Total

| Fase | Tiempo Estimado |
|------|----------------|
| Fase 1: Setup | 2-3 horas |
| Fase 2: Chat | 3-4 horas |
| Fase 3: Visualizador | 4-5 horas |
| Fase 4: Catálogos | 2-3 horas |
| Fase 5: Layout | 1-2 horas |
| Fase 6: Pulido | 1-2 horas |
| **TOTAL** | **13-19 horas** |

---

## 🎨 Stack Tecnológico Recomendado

### Opción A: React + TypeScript (RECOMENDADA) ⭐

**Ventajas:**
- ✅ Mejor experiencia de desarrollo
- ✅ Componentes reutilizables
- ✅ Type safety con TypeScript
- ✅ Ecosistema maduro de librerías
- ✅ Fácil de mantener y escalar

**Stack:**
```json
{
  "dependencies": {
    "react": "^18.2.0",
    "react-dom": "^18.2.0",
    "react-router-dom": "^6.20.0",
    "axios": "^1.6.0",
    "@tanstack/react-table": "^8.10.0",
    "recharts": "^2.10.0",
    "react-json-view": "^1.21.3"
  },
  "devDependencies": {
    "@vitejs/plugin-react": "^4.2.0",
    "typescript": "^5.3.0",
    "tailwindcss": "^3.4.0",
    "vite": "^5.0.0"
  }
}
```

### Opción B: HTML + JavaScript Vanilla

**Ventajas:**
- ✅ Más simple
- ✅ Sin build process
- ✅ Fácil de entender para principiantes

**Stack:**
```html
<!-- CDN Dependencies -->
<script src="https://cdn.tailwindcss.com"></script>
<script src="https://cdn.datatables.net/1.13.7/js/jquery.dataTables.min.js"></script>
<script src="https://cdn.jsdelivr.net/npm/chart.js"></script>
```

---

## 🔒 Consideraciones de Seguridad

1. ✅ **CORS**: Configurar correctamente en FastAPI
2. ✅ **Validación**: Validar todos los inputs en backend
3. ✅ **Rate Limiting**: Limitar requests por IP (Fase 2)
4. ✅ **Sanitización**: Sanitizar outputs para prevenir XSS
5. ✅ **HTTPS**: Usar HTTPS en producción

---

## 📊 Métricas de Éxito

### Funcionales:
- ✅ Usuario puede hacer preguntas y recibir respuestas
- ✅ Usuario puede ver todos los eventos en tabla
- ✅ Usuario puede filtrar y ordenar eventos
- ✅ Usuario puede ver detalles de cada evento
- ✅ Usuario puede ver catálogos de ciudades, CPs y categorías

### No Funcionales:
- ✅ Tiempo de carga < 2 segundos
- ✅ Interfaz responsive (mobile, tablet, desktop)
- ✅ Accesibilidad básica (WCAG 2.0 AA)
- ✅ Compatibilidad con navegadores modernos

---

## 🚀 Próximos Pasos Sugeridos

### Después de Implementación Básica:

**Mejoras de UX:**
- [ ] Autocompletado en búsqueda
- [ ] Sugerencias de preguntas frecuentes
- [ ] Favoritos de eventos
- [ ] Compartir eventos en redes sociales
- [ ] Vista de mapa con eventos geolocalizados

**Mejoras Técnicas:**
- [ ] Cache en frontend (React Query o SWR)
- [ ] Optimistic updates
- [ ] Infinite scroll en lugar de paginación
- [ ] PWA (Progressive Web App)
- [ ] Modo offline

**Analytics:**
- [ ] Google Analytics o similar
- [ ] Tracking de búsquedas populares
- [ ] Heatmaps de interacción

---

## 📋 Checklist de Aprobación

Antes de comenzar la implementación, necesito tu aprobación en:

### Decisiones Arquitectónicas:
- [ ] **Opción de Frontend**: ¿Opción A (React) o Opción B (HTML)?
- [ ] **Librerías de UI**: ¿TailwindCSS está bien? ¿Alguna preferencia?
- [ ] **Gráficos**: ¿Recharts o Chart.js?

### Funcionalidades:
- [ ] **Chat**: ¿El diseño propuesto cumple tus expectativas?
- [ ] **Visualizador**: ¿Los filtros propuestos son suficientes?
- [ ] **Catálogos**: ¿Necesitas ver más tablas además de las mencionadas?
- [ ] **Exportación**: ¿CSV y JSON son suficientes?

### Prioridades:
- [ ] ¿Qué página es más prioritaria? (Chat o Visualizador)
- [ ] ¿Necesitas alguna funcionalidad adicional no mencionada?
- [ ] ¿Hay algún plazo o deadline?

---

## 💡 Recomendación Final

**Mi recomendación es:**

1. **Opción A (React + TypeScript)** para el frontend
2. **Priorizar en este orden:**
   - Fase 1: Setup
   - Fase 2: Chat de Consultas (es lo más visual y funcional)
   - Fase 3: Visualizador de Eventos
   - Fase 4: Catálogos (si hay tiempo)

3. **Implementación incremental**: Empezar con funcionalidad básica y luego iterar

---

## ❓ Preguntas para el Usuario

Antes de comenzar, necesito que me confirmes:

1. **¿Prefieres Opción A (React) u Opción B (HTML simple)?**
2. **¿Qué página quieres implementar primero: Chat o Visualizador?**
3. **¿Hay algún diseño visual específico que quieras seguir?** (colores, estilo, etc.)
4. **¿Necesitas autenticación de usuarios o es público?**
5. **¿Alguna funcionalidad adicional que no haya mencionado?**

---

**Una vez tengas respuestas a estas preguntas, puedo comenzar la implementación inmediatamente.**

---

*Documento creado: Enero 2026*  
*Versión: 1.0*  
*Estado: Esperando aprobación del usuario*
