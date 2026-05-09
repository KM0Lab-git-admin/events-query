# 🚀 Deploy en Railway (con seed/embeddings) — Events Query

Esta guía unifica:
- Checklist de despliegue
- Generación de datos fake y embeddings contra MySQL en Railway desde local
- Verificación de Swagger y endpoints v1
- Consideraciones del **dual router** (Legacy + v1)

---

## 0) Qué se despliega

- **FastAPI** (backend)
- **MySQL** (Railway)
- (Opcional) Frontend PoC en local / frontend producción en Vercel

---

## 1) Variables de entorno (Railway)

En el servicio del backend, asegurate de tener:

```env
ENVIRONMENT=production
DB_HOST=${MySQL.MYSQLHOST}
DB_PORT=${MySQL.MYSQLPORT}
DB_USER=${MySQL.MYSQLUSER}
DB_PASSWORD=${MySQL.MYSQLPASSWORD}
DB_NAME=${MySQL.MYSQLDATABASE}

OPENAI_API_KEY=sk-...
```

> Nota: dentro de Railway se suele usar la **conexión interna** (host interno + puerto 3306).

---

## 2) Despliegue

1. Merge a la rama que Railway despliega (ej. `develop`).
2. Railway auto-deploy.
3. Revisar logs del servicio backend.

---

## 3) Smoke tests post-deploy

### Health
```bash
curl https://<TU_DOMINIO>/api/v1/health
```

### Swagger
- `https://<TU_DOMINIO>/docs`

### Endpoints v1 recomendados
```bash
curl https://<TU_DOMINIO>/api/v1/events/today
curl "https://<TU_DOMINIO>/api/v1/events?page=1&page_size=20"
curl https://<TU_DOMINIO>/api/v1/categories
```

---

## 4) Verificación de Swagger (cuando “no aparecen endpoints”)

Si no ves endpoints v1 en `/docs`, las causas típicas son:

- Estás viendo un deploy viejo (branch equivocado).
- El servidor no se reinició tras cambios.
- Cache del navegador.

Verificación rápida (local):
```bash
python scripts/verify_api_v1.py
```

Deberías ver un resumen confirmando que las rutas legacy y v1 están montadas.

---

## 5) Seed / Generación de datos fake en MySQL (Railway) desde local

### 5.1 Entender “interna” vs “pública”

Railway ofrece dos formas de conectar MySQL:

| Tipo | Host típico | Puerto típico | Para qué |
|---|---|---:|---|
| Interna | `mysql.railway.internal` | 3306 | Servicios dentro de Railway (tu API) |
| Pública | `*.proxy.rlwy.net` | (ej. 55339) | Conexiones desde tu PC |

**Para correr scripts desde tu máquina**, tenés que usar **host + puerto públicos**.

---

### 5.2 Crear `.env.railway` (en tu repo local)

Archivo separado para no romper tu `.env` de Docker/local. Plantilla en el repo: **`.env.railway.example`**. Cópiala a **`.env.railway`** (ignorada por Git) y rellena los valores reales.

```env
DB_HOST=caboose.proxy.rlwy.net
DB_PORT=55339
DB_USER=root
DB_PASSWORD=tu_password_railway
DB_NAME=railway
OPENAI_API_KEY=sk-...
```

Opcional: `ENVIRONMENT=production` si lo usas en otros scripts.

⚠️ Importante:
- `DB_HOST` solo el hostname, sin `:puerto` ni `/db`.
- `DB_PORT` el puerto **público** (no 3306 salvo que Railway lo indique en Connect).

---

### 5.3 Ejecutar generador fake (local → BD Railway)

PowerShell (un solo comando; carga `.env.railway` sola):
```powershell
.\run-fake-data-railway.ps1
# o sin limpiar antes
.\run-fake-data-railway.ps1 --no-clear
```

Alternativa manual (Linux/Mac):

```bash
export $(cat .env.railway | xargs)  # Linux/Mac
python scripts/generate_fake_data.py
```

### 5.4 Solo desplazar fechas en `EVENTO_HORARIOS` (local → BD Railway)

Misma `.env.railway` que arriba. Un solo comando en PowerShell (el script carga el `.env`):

```powershell
.\run-shift-railway.ps1 --dry-run
.\run-shift-railway.ps1
```

---

## 6) Embeddings (CRÍTICO)

La búsqueda semántica depende de que los eventos tengan embeddings (p. ej. `Tags_Embedding_ES` / `Tags_Embedding_CAT`).

Para (re)generarlos:
```bash
python scripts/generate_embeddings.py
```

Chequeo rápido (ejemplo SQL):
```sql
SELECT
  COUNT(*) AS total,
  SUM(CASE WHEN Tags_Embedding_ES IS NOT NULL THEN 1 ELSE 0 END) AS with_embeddings
FROM EVENTOS_MASTER
WHERE Estado='ACTIVO';
```

---

## 7) Dual router: qué validar en producción

Mientras convivan Legacy y v1:

- PoC / integraciones antiguas siguen usando:
  - `/query`, `/events/list`, etc.
- Producción debería apuntar a:
  - `/api/v1/query`, `/api/v1/events`, etc.

En Swagger deberías ver tags tipo:
- `Legacy`
- `Query`, `Events`, `Categories`, `Health`

---

## 8) Rollback rápido

Si algo rompe:

```bash
git revert <commit>
git push origin <branch_deploy>
```

Railway desplegará el revert.

---

## 9) Checklist resumida

- [ ] Variables de entorno OK en Railway
- [ ] Deploy OK (logs sin errores)
- [ ] `/api/v1/health` OK
- [ ] `/docs` OK (endpoints v1 visibles)
- [ ] Datos en BD (seed) OK
- [ ] Embeddings OK
- [ ] Frontend apunta a v1 (cuando corresponda)
- [ ] Legacy sigue funcionando (mientras se mantiene)

---

**Última actualización de esta guía:** 2026-02-07
