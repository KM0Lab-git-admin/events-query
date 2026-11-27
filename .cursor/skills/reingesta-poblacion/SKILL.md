---
name: reingesta-poblacion
description: >-
  Publica/reingesta eventos y noticias municipales en local y Railway.
  Usa cuando el usuario diga publicar Malgrat, reingestar población, datos
  incorrectos de una ciudad, actualizar agenda local+Railway, o active
  @reingesta-poblacion.
---

# Reingesta población (local + Railway)

## Default (sin parámetros extra)

**Instrucción canónica:**

> Publica la información de Malgrat de Mar; si no hay parámetros adicionales, actualiza el local y la base remota de Railway, teniendo en cuenta lo ya acordado (purga de agenda pasada + noticias ≤10 días).

Ejecutar desde la raíz del repo `events-query`:

```bash
python scripts/ingest_all.py --poblacion "Malgrat de Mar" --target both
```

Requiere `.env` con `DB_*`, `RAILWAY_DB_*`, `OPENAI_API_KEY`,
`EVENTS_API_BASE_URL=https://eventquery.uat.km0lab.com` (y secretos de upload).

La URL pública UAT es **https://eventquery.uat.km0lab.com/** (KM0Lab debe
consultar esa base). Si el dominio antiguo falla, no usar `eventquery.km0lab.com`.

Si falla TLS en un dominio mal configurado, relanzar con:

```bash
# PowerShell
$env:INGEST_SSL_VERIFY="0"; python scripts/ingest_all.py --poblacion "Malgrat de Mar" --target both
```

Si la API de imágenes responde `404 Application not found`, la ingesta
persiste en BD + `IMAGENES_BLOB` y continúa.
## Parámetros opcionales

| Usuario dice | Flag |
|--------------|------|
| Otra ciudad (ej. Blanes) | `--poblacion "Blanes"` |
| Solo local | `--target local` |
| Solo Railway | `--target railway` |
| Vaciar y rehacer todo | añadir `--hard-reset` (pedir confirmación explícita) |

## Qué hace el pipeline (ya incluido)

1. **Agenda:** borra eventos (y horarios sueltos) cuya fecha ya pasó respecto a la invocación.
2. **Noticias:** borra las con `Fecha_Publicacion` anterior a hoy − **10** días (`NEWS_VIGENCIA_DIAS` / `NEWS_TTL_DIAS`, default 10); conserva las de la ventana.
3. Extrae una vez (LLM) y persiste en el/los targets pedidos.
4. Cuerpos de noticia sin `\n` entre emojis (`flatten_news_text` al persistir; API también aplana).

No hace falta un DELETE manual aparte salvo depuración; la limpieza es el paso 0 de `ingest_all.py`.

## Tras la ejecución

1. Comprobar conteos / fechas en local y Railway (o API):
   - `GET /api/v1/events?poblacion=Malgrat%20de%20Mar`
   - `GET https://eventquery.uat.km0lab.com/api/v1/news?city=Malgrat%20de%20Mar`
2. Resumir al usuario: eventos/noticias persistidos, purgas, errores.
3. No commitear `static/images/` ni `.env`. Commits solo si el usuario lo pide; sin trailer Cursor.

## Invocación

- `@reingesta-poblacion`
- “publica Malgrat” / “actualiza Malgrat en local y Railway” / “datos malos en &lt;ciudad&gt;”
