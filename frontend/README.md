# Events Query - Frontend PoC

Frontend React minimalista para probar el flujo completo de consultas en lenguaje natural.

## 🚀 Instalación

```bash
cd frontend
pnpm install
```

## 🏃 Ejecutar en desarrollo

**Importante:** Primero debes tener el backend corriendo en el puerto 8000.

### 1. Iniciar el backend (en otra terminal):

```bash
cd /home/ubuntu/events-query
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

### 2. Iniciar el frontend:

```bash
cd frontend
pnpm dev
```

El frontend estará disponible en: **http://localhost:3000**

## 📋 Funcionalidades

### Sección 1: Lista de Eventos
- Muestra todos los eventos disponibles en la base de datos
- Estadísticas: total de eventos, gratuitos, de pago
- Información básica: título, ubicación, fecha, precio, categorías

### Sección 2: Chat de Consultas
- Input para hacer preguntas en lenguaje natural
- Campo para código postal del usuario
- Muestra la respuesta en lenguaje natural
- Muestra el JSON completo de la respuesta
- Ejemplos de preguntas sugeridas

## 🔧 Configuración

El frontend usa un proxy configurado en `vite.config.js` para redirigir las peticiones al backend:

- `/api/*` → `http://localhost:8000/api/*`
- `/query` → `http://localhost:8000/query`
- `/health` → `http://localhost:8000/health`

## 📦 Dependencias

- **React 18**: Framework UI
- **Vite**: Build tool y dev server
- **CSS puro**: Sin frameworks de estilos (minimalista)

## 🧪 Probar el Flujo Completo

1. Abre el frontend en http://localhost:3000
2. Revisa la lista de eventos disponibles (sección superior)
3. Escribe una pregunta relevante basada en los eventos que ves
4. Ingresa un código postal (ej: 08380)
5. Click en "Buscar"
6. Verás la respuesta en lenguaje natural y el JSON completo

## 📝 Ejemplos de Preguntas

- "¿Qué hacer este fin de semana?"
- "Eventos gratuitos para niños"
- "Actividades de cultura en mi zona"
- "Conciertos de música cerca de mí"

## 🐛 Troubleshooting

### Error: "Failed to fetch"
- Verifica que el backend esté corriendo en el puerto 8000
- Verifica que la base de datos MySQL esté activa
- Verifica que tengas datos fake generados

### Error: "OpenAI API key not configured"
- Asegúrate de tener `OPENAI_API_KEY` configurada en el `.env` del backend

### No se muestran eventos
- Ejecuta el script de generación de datos fake:
  ```bash
  cd /home/ubuntu/events-query
  python scripts/generate_fake_data.py
  ```

## 📄 Estructura de Archivos

```
frontend/
├── src/
│   ├── App.jsx           # Componente principal
│   ├── EventsList.jsx    # Lista de eventos
│   ├── QueryChat.jsx     # Chat de consultas
│   ├── main.jsx          # Entry point
│   └── index.css         # Estilos globales
├── index.html            # HTML base
├── vite.config.js        # Configuración de Vite
├── package.json          # Dependencias
└── README.md             # Este archivo
```

## 🚀 Build para Producción

```bash
pnpm build
```

Los archivos estáticos se generarán en `dist/`.

---

**Versión:** 0.0.1 (PoC)  
**Fecha:** Enero 2026
