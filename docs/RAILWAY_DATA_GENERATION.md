# Generar datos en la base de datos de Railway desde local

Esta guía explica cómo ejecutar el script de generación de datos fake (`scripts/generate_fake_data.py`) contra la base de datos MySQL alojada en Railway, **desde tu máquina local**, sin modificar la configuración que usas con Docker en local.

---

## 1. Contexto: qué hace el script y dónde se ejecuta

- **Qué hace el script:** `scripts/generate_fake_data.py` crea eventos de prueba, genera embeddings con OpenAI y los inserta en la base de datos (tablas de eventos, categorías, etc.).
- **Dónde se ejecuta:** El script se ejecuta **siempre en tu PC**. Railway no ofrece un comando tipo "ejecutar este script una vez en el servidor". El CLI de Railway (`railway run`) solo inyecta variables de entorno en un proceso que corre **en local**; no lanza código en los servidores de Railway.
- **A qué se conecta:** Cuando usas la configuración descrita aquí, el script se conecta a la **base de datos MySQL de Railway** usando la **conexión pública** (proxy), para que tu máquina pueda alcanzarla por internet.

Por tanto: **Python y dependencias = local; base de datos = Railway.**

---

## 2. Por qué no usar el mismo `.env` que Docker

- El **`.env`** del proyecto está pensado para **Docker en local**: `DB_HOST=localhost`, puerto 3306, usuario/contraseña de tu MySQL local.
- Si lo sobreescribes con las credenciales de Railway, tu entorno Docker dejaría de conectar a tu BD local.
- Solución: usar un **fichero aparte** (`.env.railway`) solo para ejecutar el script contra Railway, y un script de PowerShell que cargue esas variables y lance el generador. Tu `.env` sigue intacto para Docker.

---

## 3. Requisitos previos

- **Python** en tu máquina local con las dependencias del proyecto instaladas (el mismo que usarás para el script).
- **Variables de conexión públicas** de MySQL en Railway (host y puerto del proxy público, no los internos).
- **OPENAI_API_KEY** disponible (en `.env.railway` o en el entorno) para que el script genere embeddings.

Comprobar que el Python de la terminal tiene `openai`:

```powershell
python -c "import openai; print('OK')"
```

Si falla, instala dependencias:

```powershell
pip install -r requirements.txt
```

---

## 4. Conexión interna vs pública en Railway (MySQL)

En Railway hay **dos formas** de conectar a MySQL:

| Tipo        | Host ejemplo                 | Puerto ejemplo | Uso |
|------------|------------------------------|----------------|-----|
| **Interna** | `mysql.railway.internal`     | `3306`         | Servicios desplegados en Railway (p. ej. tu API). Solo accesible desde dentro de Railway. |
| **Pública** | `caboose.proxy.rlwy.net` (o similar) | Ej. `55339`    | Conexiones desde fuera (tu PC, scripts locales). Es la que debes usar para el script. |

- **MYSQLPORT = 3306** en el dashboard es el puerto **interno**. No uses ese puerto para conectarte desde tu ordenador.
- Para el script en local debes usar el **host y el puerto** que Railway muestra en la **conexión pública** (pestaña Connect / variables de conexión pública del servicio MySQL). Ese host y puerto suelen ser distintos a `mysql.railway.internal` y `3306`.

---

## 5. Configuración paso a paso

### 5.1 Crear `.env.railway`

En la raíz del proyecto, crea un fichero **`.env.railway`** (no lo subas a git; ya está en `.gitignore`). Usa como plantilla `.env.railway.example` si existe.

Las variables deben ser **separadas**; **no** pongas la URL completa en `DB_HOST`:

```env
DB_HOST=caboose.proxy.rlwy.net
DB_PORT=55339
DB_USER=root
DB_PASSWORD=tu_password_railway
DB_NAME=railway
OPENAI_API_KEY=sk-proj-...
ENVIRONMENT=production
```

- **DB_HOST:** solo el hostname público (ej. `caboose.proxy.rlwy.net`), **sin** `:puerto` ni `/railway`.
- **DB_PORT:** el puerto que Railway asigne a la **conexión pública** (puede ser 55339 u otro; no uses 3306 para conexión desde tu PC salvo que la URL pública lo indique).
- **DB_USER**, **DB_PASSWORD**, **DB_NAME:** los mismos que en Railway (ej. `root`, contraseña del MySQL, `railway`).

Obtén host y puerto públicos en el dashboard de Railway → servicio MySQL → pestaña **Connect** o variables de **conexión pública**.

### 5.2 Script de ejecución (`run-fake-data-railway.ps1`)

El proyecto incluye un script de PowerShell que:

1. Carga las variables de `.env.railway` en el proceso actual.
2. Ejecuta `python scripts/generate_fake_data.py` con esos valores.

Así no se modifica `.env` y no hace falta usar `railway run` para las variables de BD (porque la conexión pública no es la que Railway inyecta por defecto con `railway link`).

**Uso (PowerShell, desde la raíz del repo):**

```powershell
.\run-fake-data-railway.ps1
```

Por defecto el script **borra** los datos existentes y vuelve a generar. Para **añadir** datos sin borrar:

```powershell
.\run-fake-data-railway.ps1 --no-clear
```

---

## 6. Errores frecuentes y soluciones

| Síntoma | Causa | Solución |
|--------|--------|----------|
| `Can't connect to MySQL server on 'localhost'` | No se están usando las variables de Railway (o no existen). | Asegúrate de ejecutar `.\run-fake-data-railway.ps1` (que carga `.env.railway`) y de que `.env.railway` existe y tiene DB_HOST, DB_PORT, etc. |
| `Can't connect to MySQL server on 'mysql://user:pass@host:port/db'` | La URL completa está en `DB_HOST`. | En `.env.railway`, pon solo el host en `DB_HOST`, el puerto en `DB_PORT` y el nombre de la base en `DB_NAME`. |
| `getaddrinfo failed` o conexión rechazada con host público | Puerto incorrecto (p. ej. 3306 en vez del puerto público). | Usa en `DB_PORT` el puerto que aparece en la **conexión pública** de Railway (p. ej. 55339), no el MYSQLPORT interno 3306. |
| `ModuleNotFoundError: No module named 'openai'` | El Python que usa la terminal no tiene las dependencias. | Instala con `pip install -r requirements.txt` en el mismo Python con el que ejecutas el script (o usa un venv y activa ese venv antes de ejecutar). |

---

## 7. Resumen del flujo

1. **Docker en local:** sigue usando `.env` (localhost, tu MySQL local).
2. **Generar datos en Railway:**  
   - Crea/edita `.env.railway` con host/puerto **públicos** y credenciales de Railway.  
   - Ejecuta `.\run-fake-data-railway.ps1` (o `--no-clear` si no quieres borrar datos).  
   - El script corre en tu PC y escribe en la BD de Railway.

---

## 8. Alternativa: ejecutar la lógica en Railway (sin script local)

Si prefieres no ejecutar nada en tu máquina, se puede exponer la misma lógica como **endpoint de administración** en la API (por ejemplo `POST /admin/generate-fake-data`). Al llamar a ese endpoint, el código corre **en el servidor de Railway** y usa la conexión interna a MySQL (`mysql.railway.internal:3306`), sin necesidad de `.env.railway` ni de conexión pública desde tu PC. Esta opción no está descrita en detalle aquí pero es la alternativa "todo en Railway" al flujo anterior.
