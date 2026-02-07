# 🚀 Quick Start - Events Query API

**Guía de inicio rápido para poner el proyecto en marcha en 10 minutos**

---

> 📌 **Docs relacionados (documentación unificada)**  
> - [API (Legacy + v1)](./API.md)  
> - [Deploy en Railway](./DEPLOYMENT.md)  
> - [Arquitectura](./ARCHITECTURE.md)  
> - [Modelo de datos + Ingesta IA](./DATA_MODEL.md)  
> - [Desarrollo](./DEVELOPMENT.md)  
> - [Troubleshooting](./TROUBLESHOOTING.md)


## 📋 Requisitos Previos

Antes de empezar, asegúrate de tener instalado:

- **Python 3.11+** ([Descargar](https://www.python.org/downloads/))
- **MySQL 8.0+** ([Descargar](https://dev.mysql.com/downloads/mysql/))
- **Node.js 22+** ([Descargar](https://nodejs.org/)) - Para frontend
- **pnpm** ([Instalar](https://pnpm.io/installation)) - Package manager
- **OpenAI API Key** ([Obtener](https://platform.openai.com/api-keys))

### Verificar Instalación

```bash
python3.11 --version  # Python 3.11.0 o superior
mysql --version       # mysql  Ver 8.0.x
node --version        # v22.x.x
pnpm --version        # 9.x.x
```

---

## ⚡ Instalación Rápida (3 Pasos)

### Paso 1: Backend (5 minutos)

```bash
# 1. Clonar repositorio
git clone https://github.com/KM0Lab-git-admin/events-query.git
cd events-query

# 2. Crear entorno virtual
python3.11 -m venv venv
source venv/bin/activate  # En Windows: venv\Scripts\activate

# 3. Instalar dependencias
pip install -r requirements.txt

# 4. Configurar variables de entorno
cp .env.example .env
nano .env  # O tu editor favorito
```

**Edita `.env` con tus credenciales:**

```env
# Base de Datos
DB_HOST=localhost
DB_PORT=3306
DB_USER=events_user
DB_PASSWORD=events_password
DB_NAME=events_db

# OpenAI
OPENAI_API_KEY=sk-...tu-api-key-aqui...

# Opcional
LOG_LEVEL=INFO
```

```bash
# 5. Crear base de datos
mysql -u root -p

# En MySQL:
CREATE DATABASE events_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
CREATE USER 'events_user'@'localhost' IDENTIFIED BY 'events_password';
GRANT ALL PRIVILEGES ON events_db.* TO 'events_user'@'localhost';
FLUSH PRIVILEGES;
EXIT;

# 6. Ejecutar esquema
mysql -u events_user -p events_db < SQL/SCHEMA_SQL_FINAL.sql

# 7. Generar datos fake (125 eventos)
python scripts/generate_fake_data.py

# 8. Iniciar backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

**✅ Backend corriendo en:** http://localhost:8000

---

### Paso 2: Frontend (3 minutos)

**Abre una nueva terminal:**

```bash
cd events-query/frontend

# 1. Instalar dependencias
pnpm install

# 2. Iniciar frontend
pnpm dev
```

**✅ Frontend corriendo en:** http://localhost:3000

---

### Paso 3: Probar (2 minutos)

1. **Abrir navegador:** http://localhost:3000

2. **Ver eventos disponibles** (sección superior):
   - Lista de 122 eventos fake
   - Estadísticas (total, gratuitos)

3. **Hacer una consulta** (sección inferior):
   - **Pregunta:** "¿Qué hacer este fin de semana?"
   - **Código Postal:** 08380
   - Click **"Buscar"**

4. **Ver resultado:**
   - Respuesta en lenguaje natural
   - Lista de eventos relevantes
   - JSON completo expandible

**🎉 ¡Listo! El sistema está funcionando.**

---

## 🔍 Verificación

### Health Check

```bash
curl http://localhost:8000/api/v1/health
# (legacy) curl http://localhost:8000/health
```

**Respuesta esperada:**

```json
{
  "status": "healthy",
  "version": "1.0.0",
  "timestamp": "2026-01-25T10:30:00",
  "checks": {
    "database": "healthy",
    "openai": "configured",
    "api": "healthy"
  }
}
```

### API Docs

- **Swagger UI:** http://localhost:8000/docs
- **ReDoc:** http://localhost:8000/redoc

---

## 💡 Primer Uso

### Ejemplos de Preguntas

**Español:**
- "¿Qué hacer este fin de semana?"
- "Eventos gratuitos para niños"
- "Actividades al aire libre cerca de mi"
- "Conciertos de música en un radio de 20 kilómetros"
- "Actividades relacionadas con comida"

**Catalán:**
- "Què fer aquest cap de setmana?"
- "Esdeveniments gratuïts per a nens"
- "Activitats a l'aire lliure prop meu"

### Códigos Postales Disponibles

Los datos fake incluyen 5 poblaciones:

| Población | Código Postal | Eventos |
|-----------|---------------|---------|
| Malgrat de Mar | 08380 | 25 |
| Calella | 08370 | 25 |
| Canet de Mar | 08360 | 25 |
| Pineda de Mar | 08397 | 25 |
| Blanes | 17300 | 25 |

---

## 🔧 Troubleshooting Básico

### Error: "Database pool not initialized"

**Causa:** MySQL no está corriendo o credenciales incorrectas.

**Solución:**

```bash
# Verificar que MySQL está corriendo
sudo systemctl status mysql  # Linux
brew services list           # macOS

# Verificar credenciales en .env
cat .env | grep DB_

# Probar conexión manual
mysql -u events_user -p events_db
```

---

### Error: "OpenAI API key not configured"

**Causa:** Falta `OPENAI_API_KEY` en `.env`.

**Solución:**

```bash
# Verificar que existe
cat .env | grep OPENAI_API_KEY

# Si no existe, añadirlo
echo "OPENAI_API_KEY=sk-tu-api-key-aqui" >> .env

# Reiniciar backend
# Ctrl+C en la terminal del backend
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

---

### Error: Frontend no se conecta al backend

**Causa:** Proxy no configurado o backend no corriendo.

**Solución:**

```bash
# 1. Verificar que backend está corriendo
curl http://localhost:8000/api/v1/health
# (legacy) curl http://localhost:8000/health

# 2. Verificar proxy en vite.config.js
cat frontend/vite.config.js

# Debería tener:
# proxy: {
#   '/query': 'http://localhost:8000',
#   '/events': 'http://localhost:8000',
#   '/health': 'http://localhost:8000'
# }

# 3. Reiniciar frontend
cd frontend
pnpm dev
```

---

### Performance Lenta

**Causa:** Primera llamada a OpenAI es siempre más lenta.

**Solución:**

- ✅ **Normal:** Primera query ~3s, siguientes ~1.5s
- ✅ Activa modo debug: `"debug": true` en el request
- ✅ Revisa logs del backend para identificar cuello de botella

---

### No Encuentra Eventos

**Causa:** Umbral de similitud muy alto o tags insuficientes.

**Solución:**

1. **Activa debug mode** en el frontend (ya está activado)
2. **Revisa el JSON completo** → `debug_info`
3. **Mira `analisis_detallado`** para ver por qué no pasó el filtro
4. **Ajusta umbral** si es necesario (ver [`DEVELOPMENT.md`](DEVELOPMENT.md))

---

## 📊 Análisis Detallado

El sistema incluye un **análisis paso a paso** para entender cómo la IA toma decisiones.

### Activar Análisis

Ya está activado por defecto en el PoC. Si no lo ves:

1. **Abre la consola del navegador** (F12)
2. **Busca logs:**
   ```
   DEBUG: analisis_detallado = Array(20)
   ```
3. **Si no aparece:** Ver [`TROUBLESHOOTING.md`](TROUBLESHOOTING.md)

### Qué Muestra

Para cada evento:
- ✅ Score de similitud
- ✅ Similitud por tag individual
- ✅ Similitud por categoría
- ✅ Problemas detectados
- ✅ Soluciones propuestas
- ✅ Score estimado con mejoras

---

## 🎯 Próximos Pasos

### Para Desarrolladores

1. **Lee la arquitectura:** [`ARCHITECTURE.md`](ARCHITECTURE.md)
2. **Guía de desarrollo:** [`DEVELOPMENT.md`](DEVELOPMENT.md)
3. **Modifica el código** y experimenta

### Para Testing

1. **Prueba diferentes preguntas** (español y catalán)
2. **Prueba diferentes CPs** (08380, 08370, 08360, etc.)
3. **Revisa el análisis detallado** para entender decisiones
4. **Reporta problemas** encontrados

### Para Mejora

1. **Identifica eventos que no se encuentran**
2. **Revisa el análisis** para ver por qué
3. **Aplica mejoras sugeridas** (añadir tags, cambiar categoría)
4. **Valida que funciona**

---

## 📚 Documentación Completa

- **[🏗️ Arquitectura](ARCHITECTURE.md)** - Cómo funciona el sistema
- **[👨‍💻 Desarrollo](DEVELOPMENT.md)** - Guía para desarrolladores
- **[🔧 Troubleshooting](TROUBLESHOOTING.md)** - Solución de problemas

---

## 🆘 Ayuda

Si tienes problemas:

1. **Revisa [`TROUBLESHOOTING.md`](TROUBLESHOOTING.md)**
2. **Busca en los logs del backend** (terminal 1)
3. **Busca en la consola del frontend** (F12)
4. **Abre un issue** en GitHub

---

## 🎉 ¡Listo!

Ahora tienes Events Query API funcionando localmente. Experimenta con diferentes preguntas y explora el análisis detallado para entender cómo funciona la IA.

**Happy coding! 🚀**