# AGENTS.md — events-query

Reglas para agentes de IA en este repositorio. Contexto del ecosistema:
`km0lab/docs/START-HERE-AI.md` (repo hermano `km0lab`).

## Qué es

API de **agenda y noticias municipales** de KM0 LAB, más el pipeline que las
recoge de webs externas y las enriquece con IA. La app `km0lab` solo la
consume en lectura, contra `/api/v1/*`. El repo incluye además un frontend
de operaciones (`frontend/`, React 18 sin router) que la propia API sirve
compilado.

Stack: FastAPI, aiomysql (MySQL 8) y OpenAI: `gpt-4.1-mini` por defecto
(el cron fija su modelo en `scripts/ingest_cron.json`) y
`text-embedding-3-small` para búsqueda y deduplicación.

## Lo primero que hay que saber

**El pipeline de ingesta real es `scripts/ingest_all.py`.** Es un único
script síncrono de más de 5.000 líneas, con pymysql, y es lo que corre en el
cron de Railway.

**`app/ingestion/` no se usa en producción.** Es un esqueleto sin LLM. Los
documentos `docs/INGESTION_OVERVIEW.md`, `INGESTION_PIPELINE.md`,
`INGESTION_DATA_MODEL.md` e `INGESTION_OPTIMIZATION.md` describen ese diseño,
no lo implementado: las tablas `CAPTURAS_RAW`, `AUDITORIA_SCRAPING`,
`COVERAGE_METRICS`, `EVENTO_EMBEDDINGS` y `PHASH_IMAGENES` no existen.

**`README.md` describe la fase 1 de enero de 2026.** La API actual es la
versionada en `app/api/v1/`.

Documentos que sí reflejan el funcionamiento real:
`docs/INGESTION_OPERATIONS.md` (cron, trigger manual, pulls) y
`docs/PLAN-MEJORA-SCRAPING-2026-09.md` (fugas conocidas del pipeline, con
referencias a línea).

## Dónde va cada cosa

| Qué                              | Dónde                                   |
| -------------------------------- | --------------------------------------- |
| Endpoints v1                     | `app/api/v1/` (registro en `router.py`) |
| Endpoints legacy (los usa el front de ops) | `app/api/routes.py`           |
| Búsqueda en lenguaje natural     | `app/services/`                         |
| Pipeline de ingesta              | `scripts/ingest_all.py`                 |
| Deduplicación y familias         | `scripts/dedupe_events.py`              |
| Fuentes por población (semillas) | `scripts/fuentes/<Poblacion>.json` + `scripts/import_fuentes.py` |
| Configuración del cron           | `scripts/ingest_cron.json`              |
| Esquema completo                 | `SQL/SCHEMA_SQL_FINAL.sql`              |
| Cambios de esquema               | `SQL/*_delta.sql` (idempotentes)        |
| Front de operaciones             | `frontend/src/`                         |

## Comandos

```powershell
.\start.ps1                        # MySQL en Docker + API en :8000 + front
.\stop.ps1
pytest
python scripts/ingest_all.py --poblacion "Malgrat de Mar" --dry-run
python scripts/import_fuentes.py --input scripts/fuentes/Malgrat.json
python scripts/pull_events_from_railway.py     # Railway → local, no destructivo
```

`--dry-run` no escribe en la base de datos pero **sí gasta en OpenAI**.

## Reglas

1. **Noticias: vigencia de 10 días.** Se borran físicamente al caducar, con
   sus imágenes. No reduzcas ni amplíes la ventana sin que se pida.
2. **Escribir en Railway es publicar.** `ingest_all.py --target railway` o
   `both`, `sync_events_db_to_railway.py`, `upload_images_railway.py` y los
   `run-*-railway.ps1` modifican UAT. Solo cuando el usuario lo pide.
   `--hard-reset` vacía eventos y noticias: confirmar siempre antes.
3. **No hay migraciones automáticas.** El arranque solo crea el esquema si
   no existe ninguna tabla. Un cambio de esquema es un `SQL/<nombre>_delta.sql`
   idempotente, aplicado a mano en local y en Railway, y reflejado también en
   `SQL/SCHEMA_SQL_FINAL.sql`.
4. **CORS está en código**, en la lista `allowed_origins` de `app/main.py`.
   Un origen nuevo es un commit y un redeploy.
5. **Imágenes.** El disco de Railway es efímero: los bytes viven en la tabla
   `IMAGENES_BLOB` y se rehidratan al arrancar. No guardes imágenes solo en
   disco.
6. **Contrato con la app.** Si cambias una respuesta de `/api/v1/*`, revisa
   `km0lab/packages/app/services/eventsApi.ts`, `newsApi.ts` y
   `apiSchemas.ts`.
7. **Coste.** Cada run registra su gasto en `INGESTA_RUNS` e
   `INGESTA_COSTES`. Si añades una llamada al LLM, pásala por `llm_json`
   para que se contabilice.
8. **Fuentes externas.** `ingest_all.py` hoy no consulta `robots.txt`;
   cualquier conector nuevo debe hacerlo y respetar `Crawl-delay`. Ante un
   403 no se reintenta con otra identidad: la fuente se registra como error.
9. **Commits sin el trailer `Co-authored-by: Cursor`** (regla existente en
   `.cursor/rules/no-cursor-trailer.mdc`).

## Trabajo en curso

El Viajero Animalista: módulo de noticias y eventos animalistas de ámbito
nacional que reutiliza este repo con base de datos propia. Leer primero
`docs/animalista-mockup/CAMBIOS-V2.md` y después
`docs/VIAJERO-ANIMALISTA-DISENO.md`. Su código vive en `SQL/animalista/` y
`scripts/animalista/` y no toca las tablas de KM0.

## Git

Rama de trabajo `develop` (despliega a UAT). `main` es producción y solo
recibe merges decididos por una persona. Conventional Commits con subject
de 50 caracteres como máximo. Sin `--amend` ni `--force` salvo petición.
