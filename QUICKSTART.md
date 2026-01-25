# 🚀 Guía de Inicio Rápido - Events Query API

Esta guía te ayudará a tener la API funcionando en **menos de 10 minutos**.

---

## Opción 1: Docker Compose (Recomendado) 🐳

### Requisitos
- Docker
- Docker Compose
- OpenAI API Key

### Pasos

1. **Clonar el repositorio**
   ```bash
   git clone <repo_url>
   cd events-api
   ```

2. **Configurar OpenAI API Key**
   ```bash
   export OPENAI_API_KEY="tu_api_key_aqui"
   ```

3. **Levantar servicios**
   ```bash
   docker-compose up -d
   ```

4. **Esperar a que MySQL esté listo** (30 segundos aprox)
   ```bash
   docker-compose logs -f mysql
   # Espera a ver: "ready for connections"
   ```

5. **Generar datos fake**
   ```bash
   docker-compose exec api python scripts/generate_fake_data.py
   ```

6. **¡Listo!** La API está en: http://localhost:8000
   - Docs: http://localhost:8000/docs
   - Health: http://localhost:8000/health

### Probar la API

```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{
    "pregunta": "¿Qué hacer este fin de semana?",
    "cp_usuario": "08380"
  }'
```

---

## Opción 2: Instalación Local 💻

### Requisitos
- Python 3.11+
- MySQL 8.0+
- OpenAI API Key

### Pasos

1. **Clonar el repositorio**
   ```bash
   git clone <repo_url>
   cd events-api
   ```

2. **Crear entorno virtual**
   ```bash
   python3.11 -m venv venv
   source venv/bin/activate
   ```

3. **Instalar dependencias**
   ```bash
   pip install -r requirements.txt
   ```

4. **Configurar .env**
   ```bash
   cp .env.example .env
   # Editar .env con tus credenciales
   ```

5. **Crear base de datos**
   ```bash
   mysql -u root -p
   ```
   ```sql
   CREATE DATABASE events_db CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci;
   CREATE USER 'events_user'@'localhost' IDENTIFIED BY 'events_password';
   GRANT ALL PRIVILEGES ON events_db.* TO 'events_user'@'localhost';
   FLUSH PRIVILEGES;
   EXIT;
   ```

6. **Ejecutar esquema**
   ```bash
   mysql -u events_user -p events_db < scripts/schema.sql
   ```

7. **Generar datos fake**
   ```bash
   python scripts/generate_fake_data.py
   ```

8. **Ejecutar la API**
   ```bash
   uvicorn app.main:app --reload
   ```

9. **¡Listo!** La API está en: http://localhost:8000

---

## 🧪 Probar la API

### Swagger UI (Recomendado)
Abre en tu navegador: http://localhost:8000/docs

### cURL

**Búsqueda en español:**
```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{
    "pregunta": "Eventos gratuitos para niños",
    "cp_usuario": "08380",
    "debug": true
  }'
```

**Búsqueda en catalán:**
```bash
curl -X POST http://localhost:8000/query \
  -H "Content-Type: application/json" \
  -d '{
    "pregunta": "Què fer aquest cap de setmana?",
    "cp_usuario": "08370"
  }'
```

**Health check:**
```bash
curl http://localhost:8000/health
```

### Python

```python
import requests

response = requests.post(
    "http://localhost:8000/query",
    json={
        "pregunta": "¿Qué hacer este fin de semana?",
        "cp_usuario": "08380"
    }
)

print(response.json())
```

---

## 📊 Datos de Prueba

El script `generate_fake_data.py` genera:

- **5 poblaciones**: Malgrat de Mar (08380), Calella (08370), Canet de Mar (08360), Pineda de Mar (08397), Blanes (17300)
- **125 eventos**: 25 por población
- **8 categorías**: Cultura, Deportes, Ocio, Infantil, Formación, Gastronomía, Música, Naturaleza
- **Fechas**: Próximos 60 días
- **Bilingüe**: Todos los eventos en español y catalán

---

## 🐛 Troubleshooting

### "Database pool not initialized"
- Verifica que MySQL esté corriendo: `docker-compose ps` o `systemctl status mysql`
- Verifica credenciales en `.env`

### "OpenAI API key not configured"
- Añade `OPENAI_API_KEY` en `.env` (local) o exporta la variable (Docker)

### Puerto 8000 ya en uso
```bash
# Cambiar puerto en docker-compose.yml o .env
API_PORT=8001
```

### Ver logs
```bash
# Docker
docker-compose logs -f api

# Local
# Los logs aparecen en la terminal donde ejecutaste uvicorn
```

---

## 📚 Siguiente Paso

Lee el [README.md](README.md) completo para:
- Documentación detallada de la API
- Estructura del proyecto
- Performance y optimizaciones
- Testing
- Deployment

---

**¿Problemas?** Abre un issue en el repositorio.
