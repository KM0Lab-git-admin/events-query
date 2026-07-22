"""
ingest_all.py — Pipeline completo de ingesta de eventos y noticias municipales
(un solo proceso).

MODO PRINCIPAL (sin --input, pensado para el cron diario): lee las fuentes de
la BD (BIBLIOTECA_FUENTES + SCRAPING_TARGETS, cargadas con
scripts/import_fuentes.py) y en UNA sola ejecución deja la base de datos al
día: eventos nuevos extraídos/fusionados/enriquecidos, noticias clasificadas y
traducidas, contenido caducado limpiado, e imágenes sincronizadas.

MODO LEGACY (--input fuentes.json): flujo original solo-eventos desde JSON plano.

QUÉ HACE, EN ORDEN (modo BD)
----------------------------
  0. Limpieza inicial: borra eventos cuya última fecha ya pasó (con sus
     imágenes locales o remotas según --target), horarios sueltos caducados,
     y BORRA las noticias caducadas con sus binarios (vigencia =
     NEWS_VIGENCIA_DIAS desde publicación, default 10).
     Con --hard-reset, antes de todo se vacían los datos de ingesta (eventos,
     noticias, binarios, recintos y estado de targets; las tablas maestras
     como CATEGORIAS/CIUDADES/BIBLIOTECA_FUENTES se conservan).
  1. Carga targets activos de la BD, agrupados por población y prioridad.
  2. Por cada target, DETECCIÓN DE CAMBIOS por URL: GET condicional
     (ETag/Last-Modified -> 304) + fingerprint sha256 del HTML limpio. Si la
     URL no cambió desde el último run -> skip total (coste 0 LLM). Telegram
     usa el id del último mensaje como fingerprint.
  3. Según el tipo de fuente:
       - EVENTOS  -> extractor de listado clásico (sin clasificador).
       - MIXTO/NOTICIAS -> clasificador LLM por item: EVENTO | NOTICIA | DESCARTAR.
       - WEB_DETALLE -> extracción directa de la página del evento (agregadores);
         se auto-pausa tras 3 capturas vacías (página caducada).
       - Telegram (t.me/s/handle) -> mensajes recientes clasificados en lote.
     INGESTA INCREMENTAL: lo que ya existe en BD (título similar en la misma
     población) se omite sin gastar detalle/cartel/enriquecimiento; la fuente
     queda registrada igualmente en EVENTO_FUENTES (Aporto_Extraccion=0).
  4. EVENTOS nuevos: detalle + cartel-OCR condicional -> FUSIÓN (título similar,
     o fechas solapadas + mismo lugar) -> filtro temporal -> enriquecimiento
     (traducción, tags, categorías, recinto) -> persistencia transaccional.
  5. NOTICIAS nuevas: solo las publicadas dentro de la ventana de vigencia ->
     detalle -> dedupe cross-fuente (título similar ±7 días) -> traducción
     CA/ES + tags -> NOTICIAS_MASTER + NOTICIA_BINARIOS
     (Fecha_Caducidad = publicación + NEWS_VIGENCIA_DIAS).
  6. Limpieza de carpetas de imágenes huérfanas + sync de binarios remotos.
  7. Estado por target en SCRAPING_TARGETS (OK/ERROR/PAUSADO, ETag,
     fingerprint, contadores) + resumen de targets + informe de gasto LLM.

Un lock-file (scripts/.ingest.lock) evita ejecuciones simultáneas del cron.
Redes sociales IG/FB/X/YouTube: registradas en BD inactivas; conector Apify en
fase 2. NO hace: embeddings (se generan aparte).

USO
---
    python ingest_all.py                            # fuentes desde BD (modo cron)
    python ingest_all.py --target railway           # ídem contra Railway
    python ingest_all.py --target both              # extrae 1 vez, persiste en AMBAS BDs
    python ingest_all.py --hard-reset --target both # vacía datos de ingesta y reingesta todo
    python ingest_all.py --poblacion "Malgrat de Mar"   # solo esa población
    # Tras parsear cada población se ejecuta automáticamente la deduplicación/
    # agrupación en familias (dedupe_events). Desactivable con --sin-dedupe.
    python ingest_all.py --dry-run                  # no escribe BD/imágenes (SÍ gasta LLM)
    python ingest_all.py --refresh                  # ignora incremental y fingerprints
    python ingest_all.py --input fuentes.json       # modo legacy JSON plano
    python ingest_all.py --sync-images-only --target railway

FORMATO DEL JSON DE ENTRADA (legacy)
------------------------------------
    [
      {"poblacion": "Malgrat de Mar", "codigos_postales": ["08380"],
       "links": ["https://www.ajmalgrat.cat/comunicacio/agenda"]},
      {"poblacion": "Blanes", "codigos_postales": ["17300"],
       "links": ["https://www.blanescostabrava.cat/es/agenda-eventos/",
                 "https://www.blanes.cat/agenda"]}
    ]

DEPENDENCIAS
------------
    pip install httpx beautifulsoup4 lxml openai pymysql Pillow python-dotenv

VARIABLES DE ENTORNO (.env)
---------------------------
    OPENAI_API_KEY, OPENAI_TIMEOUT (o INGEST_OPENAI_TIMEOUT), OPENAI_MAX_RETRIES
    --target local  -> DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME
    --target railway -> RAILWAY_DB_HOST, RAILWAY_DB_PORT, RAILWAY_DB_USER,
                        RAILWAY_DB_PASSWORD, RAILWAY_DB_NAME
                        (+ EVENTS_API_BASE_URL, INGEST_UPLOAD_SECRET o RAILWAY_DB_PASSWORD)
"""

import argparse
import csv
import difflib
import hashlib
import io
import json
import logging
import os
import re
import shutil
import sys
import time
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin, urlparse

import httpx
import pymysql
import pymysql.cursors
from bs4 import BeautifulSoup, Comment
from openai import OpenAI
from PIL import Image

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


# ============================================================================
# CONFIGURACIÓN
# ============================================================================

# Modelo LLM del run. Seleccionable con --modelo (o env LLM_MODEL) para poder
# comparar calidad/coste entre gpt-4.1-mini y gpt-4.1-nano sobre el mismo contenido.
LLM_MODEL = os.getenv("LLM_MODEL", "gpt-4.1-mini")


def set_llm_model(modelo: str):
    global LLM_MODEL
    LLM_MODEL = modelo


# Tope de caracteres de texto enviados por llamada LLM (tras convertir el HTML
# a texto+enlaces). Protege de páginas monstruosas; configurable por env.
LLM_MAX_INPUT_CHARS = int(os.getenv("LLM_MAX_INPUT_CHARS", "20000"))

DEFAULT_EVENTS_API_BASE_URL = "https://eventquery.km0lab.com"

IMAGES_DIR = Path("static") / "images"

# Orientación de imágenes (ratio = ancho / alto)
RATIO_HORIZONTAL_MIN = 1.20
RATIO_VERTICAL_MAX = 0.80

HTTP_TIMEOUT = 30
HTTP_USER_AGENT = "KM0EventsIngestion/0.2"
MAX_IMAGE_SIZE_BYTES = 20 * 1024 * 1024
MAX_DETAIL_PAGES_PER_SOURCE = 60  # tope de seguridad de coste por link

# Noticias: días de vigencia desde su publicación. Solo se ingieren noticias
# publicadas dentro de la ventana, y al caducar se BORRAN físicamente de la BD
# junto con sus binarios (imágenes en disco/remoto).
NEWS_VIGENCIA_DIAS = int(os.getenv("NEWS_VIGENCIA_DIAS")
                         or os.getenv("NEWS_TTL_DIAS", "10"))

# Telegram público (t.me/s/handle): paginación y ventana temporal.
TELEGRAM_MAX_PAGINAS = 3
TELEGRAM_MAX_DIAS = 14  # no interesa histórico más antiguo

# Lock para el cron: si el fichero existe y es más joven que esto, hay otra
# ejecución en marcha y se aborta. Más viejo = lock huérfano, se ignora.
LOCK_FILE = Path(__file__).resolve().parent / ".ingest.lock"
LOCK_MAX_AGE_HORAS = 6

# Targets WEB_DETALLE (página de un solo evento, suele caducar): tras N
# capturas vacías/rotas consecutivas se pausan automáticamente.
TARGET_MAX_VACIAS = 3
OPENAI_TIMEOUT = float(os.getenv("INGEST_OPENAI_TIMEOUT") or os.getenv("OPENAI_TIMEOUT", "120"))
OPENAI_MAX_RETRIES = int(os.getenv("OPENAI_MAX_RETRIES", "3"))

# Umbral de similitud de títulos para fusionar eventos de la misma población
# que vienen de webs distintas (p.ej. el mismo evento en catalán y castellano).
# Configurable por env var o por el flag CLI --umbral. 0.75 = bastante tolerante.
SIMILARITY_THRESHOLD = float(os.getenv("FUSION_SIMILARITY_THRESHOLD", "0.75"))

# Catálogo cerrado de categorías (debe coincidir con la tabla CATEGORIAS).
# (slug, nombre_es, nombre_ca, padre_slug|None)
CATEGORIES_FLAT = [
    ("cultura",         "Cultura",     "Cultura",     None),
    ("deportes",        "Deportes",    "Esports",     None),
    ("ocio",            "Ocio",        "Oci",         None),
    ("infantil",        "Infantil",    "Infantil",    None),
    ("formacion",       "Formación",   "Formació",    None),
    ("gastronomia",     "Gastronomía", "Gastronomia", None),
    ("musica",          "Música",      "Música",      None),
    ("naturaleza",      "Naturaleza",  "Naturalesa",  None),
    ("cine",            "Cine",            "Cinema",        "cultura"),
    ("teatro",          "Teatro",          "Teatre",        "cultura"),
    ("exposiciones",    "Exposiciones",    "Exposicions",   "cultura"),
    ("charlas",         "Charlas",         "Xerrades",      "cultura"),
    ("lectura",         "Lectura",         "Lectura",       "cultura"),
    ("fiestas-mayores", "Fiestas mayores", "Festes majors", "ocio"),
    ("ferias",          "Ferias",          "Fires",         "ocio"),
]
ALL_CATEGORY_SLUGS = [c[0] for c in CATEGORIES_FLAT]
SUBCATEGORY_TO_PARENT = {c[0]: c[3] for c in CATEGORIES_FLAT if c[3] is not None}

RECINTO_TIPOS = ["BIBLIOTECA", "CENTRO_CULTURAL", "TEATRO", "PARQUE", "OTRO"]


# ============================================================================
# DESTINO DE INGESTA (local Docker vs Railway remoto)
# ============================================================================

@dataclass
class IngestTarget:
    """Configuración de BD e imágenes según --target."""
    name: str
    db_host: str
    db_port: int
    db_user: str
    db_password: str
    db_name: str
    api_base_url: Optional[str] = None
    upload_secret: Optional[str] = None

    @property
    def store_images_locally(self) -> bool:
        return self.name == "local"


def _normalize_env(val: Optional[str]) -> str:
    if not val:
        return ""
    v = val.strip()
    if (v.startswith('"') and v.endswith('"')) or (v.startswith("'") and v.endswith("'")):
        v = v[1:-1].strip()
    return v


def resolve_ingest_target(target: str, api_base_url: Optional[str] = None) -> IngestTarget:
    """Resuelve credenciales de BD e imágenes según --target local|railway."""
    if target == "local":
        host = _normalize_env(os.getenv("DB_HOST", "localhost"))
        port = int(_normalize_env(os.getenv("DB_PORT", "3306")) or "3306")
        user = _normalize_env(os.getenv("DB_USER"))
        password = _normalize_env(os.getenv("DB_PASSWORD"))
        name = _normalize_env(os.getenv("DB_NAME"))
        if not all([host, user, password, name]):
            sys.exit("Faltan DB_HOST/DB_USER/DB_PASSWORD/DB_NAME en .env para --target local")
        return IngestTarget("local", host, port, user, password, name)

    if target == "railway":
        host = _normalize_env(os.getenv("RAILWAY_DB_HOST"))
        port = int(_normalize_env(os.getenv("RAILWAY_DB_PORT", "3306")) or "3306")
        user = _normalize_env(os.getenv("RAILWAY_DB_USER"))
        password = _normalize_env(os.getenv("RAILWAY_DB_PASSWORD"))
        name = _normalize_env(os.getenv("RAILWAY_DB_NAME"))
        if not all([host, user, password, name]):
            sys.exit("Faltan RAILWAY_DB_HOST/USER/PASSWORD/NAME en .env para --target railway")
        if host.endswith(".railway.internal") or host in ("mysql", "mysql.railway.internal"):
            sys.exit("RAILWAY_DB_HOST debe ser el host PUBLICO (MYSQL_PUBLIC_URL), no mysql.railway.internal")
        if host.startswith("mysql://"):
            sys.exit("RAILWAY_DB_HOST debe ser solo el hostname, no mysql://...")
        secret = _normalize_env(os.getenv("INGEST_UPLOAD_SECRET")) or password
        base = (api_base_url or _normalize_env(os.getenv("EVENTS_API_BASE_URL"))
                or DEFAULT_EVENTS_API_BASE_URL).rstrip("/")
        return IngestTarget("railway", host, port, user, password, name, base, secret)

    sys.exit(f"--target inválido: {target!r}. Usa 'local' o 'railway'.")


def _ingest_api_url(target: IngestTarget, path: str) -> str:
    return f"{target.api_base_url}{path}"


def _upload_image_remote(http: httpx.Client, target: IngestTarget,
                         event_id: str, filename: str, content: bytes) -> None:
    url = _ingest_api_url(target, f"/api/v1/ingest/images/{event_id}/{filename}")
    headers = {
        "X-Ingest-Secret": target.upload_secret,
        "Content-Type": "application/octet-stream",
    }
    r = http.put(url, content=content, headers=headers, timeout=120.0)
    if r.status_code == 200:
        log.info(f"    Imagen en Railway: {event_id[:12]}…/{filename} ({len(content):,} bytes)")
    elif r.status_code == 409:
        log.debug(f"    Imagen ya en Railway: {filename}")
    else:
        r.raise_for_status()


def _remote_image_exists(http: httpx.Client, target: IngestTarget, storage_url: str) -> bool:
    """True si el fichero responde 200 en la API de producción."""
    if not storage_url:
        return False
    path = storage_url if storage_url.startswith("/") else f"/{storage_url}"
    try:
        r = http.head(_ingest_api_url(target, path), follow_redirects=True, timeout=30.0)
        if r.status_code == 200:
            return True
        if r.status_code == 405:
            r = http.get(_ingest_api_url(target, path), follow_redirects=True, timeout=30.0)
            return r.status_code == 200
        return False
    except httpx.HTTPError:
        return False


def verify_railway_upload_access(http: httpx.Client, target: IngestTarget) -> None:
    """Falla pronto si el secret o la API de subida no están operativos."""
    probe_id = "0" * 64
    probe_fn = "00_000000000000.jpg"
    url = _ingest_api_url(target, f"/api/v1/ingest/images/{probe_id}/{probe_fn}")
    headers = {
        "X-Ingest-Secret": target.upload_secret,
        "Content-Type": "application/octet-stream",
    }
    try:
        r = http.put(url, content=b"", headers=headers, timeout=30.0)
    except httpx.HTTPError as exc:
        sys.exit(f"No se puede contactar la API de imágenes ({target.api_base_url}): {exc}")
    if r.status_code == 401:
        sys.exit("Secret de ingesta rechazado (401). Define INGEST_UPLOAD_SECRET en .env "
                 "igual que en Railway, o usa RAILWAY_DB_PASSWORD si coincide con DB_PASSWORD del servidor.")
    if r.status_code == 503:
        sys.exit("La API remota no tiene configurado el upload de imágenes (503).")
    if r.status_code not in (200, 400, 409, 413):
        sys.exit(f"API de imágenes respondió HTTP {r.status_code}: {r.text[:200]}")


def _delete_event_images_remote(http: httpx.Client, target: IngestTarget, event_id: str) -> None:
    url = _ingest_api_url(target, f"/api/v1/ingest/images/{event_id}")
    headers = {"X-Ingest-Secret": target.upload_secret}
    r = http.delete(url, headers=headers, timeout=60.0)
    if r.status_code not in (200, 404):
        r.raise_for_status()


# ============================================================================
# LOGGING
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("ingest_all")


# ============================================================================
# CONTABILIDAD DE COSTES (gasto REAL, no estimado)
# ============================================================================
#
# El coste se calcula a partir del uso EXACTO de tokens que devuelve la API en
# cada respuesta (campo `usage`), incluyendo los tokens de entrada CACHEADOS, que
# OpenAI factura a una tarifa reducida. No es una aproximación: es la misma
# fórmula que aplica la facturación de OpenAI sobre los tokens consumidos.
#
# Precios oficiales en USD por 1.000.000 de tokens. Si en el futuro cambian las
# tarifas o se usa otro modelo, basta con actualizar esta tabla.
MODEL_PRICES = {
    "gpt-4.1-mini": {"input": 0.40, "cached_input": 0.10, "output": 1.60},
    "gpt-4.1-nano": {"input": 0.10, "cached_input": 0.025, "output": 0.40},
}

# Embeddings (deduplicación semántica): se contabilizan con su propia tarifa
# en el campo coste_extra de los buckets (no con la tarifa del modelo de chat).
EMBED_PRICE_PER_M = 0.02  # text-embedding-3-small, USD/1M tokens


def _prices_for(model: str) -> dict:
    if model not in MODEL_PRICES:
        log.warning(f"Sin tarifa conocida para el modelo '{model}'; el coste "
                    f"calculado puede no ser exacto.")
        return {"input": 0.0, "cached_input": 0.0, "output": 0.0}
    return MODEL_PRICES[model]


class CostTracker:
    """Acumula el uso REAL de la API (tokens exactos por respuesta) y descargas,
    desglosado por población y por tipo de operación, además del total global."""

    def __init__(self):
        self.by_pob = {}
        self.by_op = {}
        self.by_pob_op = {}   # clave (poblacion, operacion): desglose persistible
        self.global_stats = self._new_bucket()

    def _new_bucket(self):
        return {
            "llm_calls": 0,
            "tokens_in": 0,        # tokens de entrada NO cacheados
            "tokens_cached": 0,    # tokens de entrada cacheados (tarifa reducida)
            "tokens_out": 0,       # tokens de salida
            "coste_extra": 0.0,    # coste con tarifa propia (embeddings)
            "imagenes": 0, "eventos": 0, "noticias": 0,
        }

    def _bucket(self, store, key):
        if key not in store:
            store[key] = self._new_bucket()
        return store[key]

    def add_llm(self, pob, response, op="otros"):
        """Suma el uso exacto de una llamada al LLM. Lee prompt_tokens,
        completion_tokens y, si está, prompt_tokens_details.cached_tokens."""
        usage = getattr(response, "usage", None)
        if not usage:
            return
        prompt = getattr(usage, "prompt_tokens", 0) or 0
        out = getattr(usage, "completion_tokens", 0) or 0
        cached = 0
        details = getattr(usage, "prompt_tokens_details", None)
        if details is not None:
            cached = getattr(details, "cached_tokens", 0) or 0
        no_cacheados = max(prompt - cached, 0)
        for b in (self._bucket(self.by_pob, pob),
                  self._bucket(self.by_op, op),
                  self._bucket(self.by_pob_op, (pob, op)),
                  self.global_stats):
            b["llm_calls"] += 1
            b["tokens_in"] += no_cacheados
            b["tokens_cached"] += cached
            b["tokens_out"] += out

    def add_embedding(self, pob, tokens: int):
        """Una llamada batch de embeddings (deduplicación). El coste va en
        coste_extra con su tarifa propia, no con la del modelo de chat."""
        coste = tokens / 1_000_000 * EMBED_PRICE_PER_M
        for b in (self._bucket(self.by_pob, pob),
                  self._bucket(self.by_op, "embeddings"),
                  self._bucket(self.by_pob_op, (pob, "embeddings")),
                  self.global_stats):
            b["llm_calls"] += 1
            b["coste_extra"] += coste

    def add_imagen(self, pob, n=1):
        self._bucket(self.by_pob, pob)["imagenes"] += n
        self.global_stats["imagenes"] += n

    def add_evento(self, pob, n=1):
        self._bucket(self.by_pob, pob)["eventos"] += n
        self.global_stats["eventos"] += n

    def add_noticia(self, pob, n=1):
        self._bucket(self.by_pob, pob)["noticias"] += n
        self.global_stats["noticias"] += n

    @staticmethod
    def _coste(b, prices):
        return (b["tokens_in"] / 1_000_000 * prices["input"] +
                b["tokens_cached"] / 1_000_000 * prices["cached_input"] +
                b["tokens_out"] / 1_000_000 * prices["output"] +
                b.get("coste_extra", 0.0))

    def report(self):
        prices = _prices_for(LLM_MODEL)
        g = self.global_stats
        W = 86

        def fila(nombre, b):
            log.info(f"{nombre[:24]:<24}{b['llm_calls']:>6}{b['tokens_in']:>12,}"
                     f"{b['tokens_cached']:>12,}{b['tokens_out']:>12,}"
                     f"{self._coste(b, prices):>12.4f}")

        log.info("=" * W)
        log.info(f"INFORME DE GASTO REAL DE OPENAI — modelo {LLM_MODEL}")
        log.info(f"Tarifas USD/1M tokens: entrada {prices['input']:.2f} · "
                 f"cacheada {prices['cached_input']:.2f} · salida {prices['output']:.2f}")
        log.info("=" * W)

        # --- Desglose por tipo de operación ---
        log.info("POR OPERACIÓN")
        log.info(f"{'Operación':<24}{'Llam.':>6}{'Tok.in':>12}{'Cacheados':>12}"
                 f"{'Tok.out':>12}{'Coste $':>12}")
        log.info("-" * W)
        for op in sorted(self.by_op):
            fila(op, self.by_op[op])
        log.info("-" * W)

        # --- Desglose por población ---
        log.info("POR POBLACIÓN")
        log.info(f"{'Población':<24}{'Llam.':>6}{'Tok.in':>12}{'Cacheados':>12}"
                 f"{'Tok.out':>12}{'Coste $':>12}")
        log.info("-" * W)
        for pob in self.by_pob:
            fila(pob, self.by_pob[pob])
        log.info("-" * W)

        # --- Totales ---
        fila("TOTAL", g)
        log.info("=" * W)
        log.info(f"Llamadas al LLM : {g['llm_calls']:,}")
        log.info(f"Tokens entrada  : {g['tokens_in']:,} (no cacheados) + "
                 f"{g['tokens_cached']:,} (cacheados) = "
                 f"{g['tokens_in'] + g['tokens_cached']:,}")
        log.info(f"Tokens salida   : {g['tokens_out']:,}")
        log.info(f"Imágenes descargadas: {g['imagenes']:,}")
        log.info(f"Eventos persistidos : {g['eventos']:,}")
        log.info(f"Noticias persistidas: {g['noticias']:,}")
        log.info("-" * W)
        log.info(f">>> GASTO TOTAL OPENAI: ${self._coste(g, prices):.4f} USD")
        log.info("=" * W)

    def persistir_run(self, conn, inicio: datetime, target_name: str,
                      parametros: str, resumen_targets: dict):
        """Guarda el run en INGESTA_RUNS + desglose población×operación en
        INGESTA_COSTES. Permite consultar el gasto histórico desde la API/front."""
        prices = _prices_for(LLM_MODEL)
        g = self.global_stats
        with conn.cursor() as cur:
            cur.execute("""
                INSERT INTO INGESTA_RUNS
                    (Inicio, Fin, Target, Modelo, Parametros, Llamadas,
                     Tokens_In, Tokens_Cached, Tokens_Out, Coste_USD,
                     Imagenes, Eventos_Persistidos, Noticias_Persistidas,
                     Targets_OK, Targets_Skip, Targets_Error)
                VALUES (%s, NOW(), %s, %s, %s, %s, %s, %s, %s, %s,
                        %s, %s, %s, %s, %s, %s)
            """, (inicio, target_name, LLM_MODEL, parametros[:255],
                  g["llm_calls"], g["tokens_in"], g["tokens_cached"],
                  g["tokens_out"], round(self._coste(g, prices), 4),
                  g["imagenes"], g["eventos"], g["noticias"],
                  resumen_targets.get("OK", 0), resumen_targets.get("SKIP", 0),
                  resumen_targets.get("ERROR", 0)))
            id_run = cur.lastrowid
            for (pob, op), b in self.by_pob_op.items():
                cur.execute("""
                    INSERT INTO INGESTA_COSTES
                        (ID_Run, Poblacion, Operacion, Llamadas,
                         Tokens_In, Tokens_Cached, Tokens_Out, Coste_USD)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s)
                """, (id_run, pob, op, b["llm_calls"], b["tokens_in"],
                      b["tokens_cached"], b["tokens_out"],
                      round(self._coste(b, prices), 4)))
        conn.commit()
        return id_run


COST = CostTracker()


# ============================================================================
# NORMALIZACIÓN DE TEXTO (para identidad y fusión)
# ============================================================================

def strip_accents(s: str) -> str:
    return "".join(c for c in unicodedata.normalize("NFKD", s)
                   if not unicodedata.combining(c))


# Prefijos de "tipo de evento" que una web pone y otra no. Se quitan antes de
# comparar para que "Exposición: X" y "X" no cuenten como títulos distintos.
TITLE_PREFIXES = [
    "exposicion", "exposicio", "exposition",
    "concierto", "concert",
    "taller", "xerrada", "charla", "conferencia", "conferencia",
    "teatre", "teatro", "cinema", "cine",
    "fira", "feria", "festa", "fiesta", "festival",
    "visita guiada", "ruta", "presentacio", "presentacion",
]


def normalize_title(s: str) -> str:
    """Normaliza un título para identidad/comparación de evento: minúsculas, sin
    acentos, sin puntuación, sin años, sin prefijos de tipo, espacios colapsados."""
    s = strip_accents((s or "").lower())
    s = re.sub(r"\b20\d{2}\b", "", s)            # quitar años tipo 2026
    s = re.sub(r"[^\w\s]", " ", s)               # quitar puntuación
    s = re.sub(r"\s+", " ", s).strip()
    # quitar un prefijo de tipo de evento al principio (p.ej. "exposicion ...")
    for pref in TITLE_PREFIXES:
        if s.startswith(pref + " "):
            s = s[len(pref) + 1:]
            break
    return s.strip()


def normalize_place(s: str) -> str:
    """Normaliza un lugar para identidad: corta detalles tras el primer punto
    o coma ('Ciutat Esportiva Blanes. Pista vermella...' -> 'ciutat esportiva
    blanes'), minúsculas, sin acentos."""
    s = (s or "").strip()
    # quitar prefijos comunes
    s = re.sub(r"^(lloc|lugar|loc)\s*:\s*", "", s, flags=re.IGNORECASE)
    # cortar en el primer separador de detalle
    for sep in [".", ",", " - ", " – ", "("]:
        idx = s.find(sep)
        if idx > 3:  # no cortar demasiado pronto
            s = s[:idx]
            break
    s = strip_accents(s.lower())
    # quitar puntuación: "platja de l''astillero'" y "platja de l'astillero"
    # deben comparar iguales (caso real de duplicado por comillas)
    s = re.sub(r"[^\w\s]", " ", s)
    s = re.sub(r"\s+", " ", s).strip()
    return s


def titulos_similares(t1: str, t2: str, umbral: float) -> bool:
    """True si dos títulos normalizados son iguales o suficientemente cercanos
    (ratio de SequenceMatcher >= umbral). Usa difflib de la stdlib, sin
    dependencias externas."""
    n1, n2 = normalize_title(t1), normalize_title(t2)
    if not n1 or not n2:
        return False
    if n1 == n2:
        return True
    return difflib.SequenceMatcher(None, n1, n2).ratio() >= umbral


def fechas_solapan(c1, c2) -> bool:
    """True si los rangos [inicio, fin] de dos candidatos se solapan. Si alguna
    fecha viene malformada, no bloqueamos la fusión (devuelve True)."""
    try:
        s1 = date.fromisoformat(c1.fecha_inicio)
        e1 = date.fromisoformat(c1.fecha_fin) if c1.fecha_fin else s1
        s2 = date.fromisoformat(c2.fecha_inicio)
        e2 = date.fromisoformat(c2.fecha_fin) if c2.fecha_fin else s2
        return s1 <= e2 and s2 <= e1
    except (ValueError, TypeError):
        return True


def event_id_from_title(poblacion: str, titulo: str) -> str:
    """ID determinista derivado de población + título normalizado del
    representante del grupo."""
    basis = f"{strip_accents(poblacion.lower()).strip()}|{normalize_title(titulo)}"
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()


# ============================================================================
# MODELOS INTERMEDIOS
# ============================================================================

@dataclass
class Horario:
    fecha_inicio: str
    fecha_fin: Optional[str]
    hora_inicio: Optional[str]
    hora_fin: Optional[str]

    def key(self):
        return (self.fecha_inicio, self.fecha_fin, self.hora_inicio, self.hora_fin)


@dataclass
class Candidate:
    """Un evento tal como sale de una fuente, antes de fusionar."""
    poblacion: str
    cp: str
    titulo: str
    lugar: str
    fuente_url: str          # URL de detalle (o de listado si no hay detalle)
    fuente_listado: str      # URL del listado de donde salió
    fecha_inicio: str
    fecha_fin: Optional[str] = None
    hora_inicio: Optional[str] = None
    hora_fin: Optional[str] = None
    descripcion_larga: str = ""
    direccion_fisica: str = ""
    organizador_nombre: str = ""
    es_gratuito: int = 1
    precio_euros: Optional[float] = None
    link_inscripcion: str = ""
    imagenes: list = field(default_factory=list)
    # Fechas discretas adicionales (ej: "conciertos el 8, 15, 22 y 29 de mayo")
    # Si no vacío, contiene todos los horarios incluido el principal.
    horarios_extra: list = field(default_factory=list)  # [Horario]


@dataclass
class MergedEvent:
    """Evento tras fusión: una identidad, varios horarios/fuentes/imágenes."""
    id_unico: str
    poblacion: str
    cp: str
    titulo: str
    lugar: str
    descripcion_larga: str
    direccion_fisica: str
    organizador_nombre: str
    es_gratuito: int
    precio_euros: Optional[float]
    link_inscripcion: str
    horarios: list = field(default_factory=list)     # [Horario]
    fuentes: list = field(default_factory=list)       # [(url_origen, url_listado)]
    imagenes: list = field(default_factory=list)      # [url]
    # rellenado en enriquecimiento:
    titulo_es: str = ""
    desc_larga_es: str = ""
    tags_ca: list = field(default_factory=list)
    tags_es: list = field(default_factory=list)
    categorias: list = field(default_factory=list)
    categoria_principal: str = ""
    recinto_canonico: str = ""
    recinto_tipo: str = "OTRO"
    evento_paraguas: str = ""   # nombre canónico del festival/ciclo al que pertenece
    desc_corta: str = ""        # resumen 2-3 frases (CA) para tarjetas
    desc_corta_es: str = ""     # resumen 2-3 frases (ES) para tarjetas


def familia_id(poblacion: str, paraguas: str) -> str:
    """ID determinista de familia de eventos, derivado del nombre canónico del
    evento paraguas (festival/fira/ciclo). Estable entre runs y fusiones."""
    basis = f"familia|{strip_accents(poblacion.lower()).strip()}|{normalize_title(paraguas)}"
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()


def deducir_paraguas_por_titulo(titulo: str) -> str:
    """Heurística determinista de respaldo: títulos tipo
    'Festival Libèl·lula: Tallers circ' -> 'Festival Libèl·lula'.
    Solo si el prefijo parece un nombre de evento (>= 2 palabras)."""
    if ":" in titulo:
        prefijo = titulo.split(":", 1)[0].strip()
        if len(prefijo.split()) >= 2 and len(prefijo) >= 8:
            return prefijo
    return ""


@dataclass
class Noticia:
    """Una noticia tal como sale de una fuente, antes de enriquecer/persistir."""
    poblacion: str
    titulo: str
    fecha_publicacion: str          # YYYY-MM-DD
    fuente_url: str
    cuerpo: str = ""
    idioma: str = "ca"
    imagen_url: str = ""            # URL externa de la imagen, si hay
    id_fuente: Optional[int] = None  # FK BIBLIOTECA_FUENTES si se conoce
    # rellenado en enriquecimiento:
    titulo_es: str = ""
    cuerpo_es: str = ""
    resumen: str = ""      # resumen 2-3 frases (CA) para tarjetas
    resumen_es: str = ""   # resumen 2-3 frases (ES) para tarjetas
    tags_ca: list = field(default_factory=list)
    tags_es: list = field(default_factory=list)


def noticia_id(poblacion: str, titulo: str) -> str:
    """ID determinista de noticia: mismo patrón que event_id_from_title."""
    basis = f"noticia|{strip_accents(poblacion.lower()).strip()}|{normalize_title(titulo)}"
    return hashlib.sha256(basis.encode("utf-8")).hexdigest()


# ============================================================================
# CONEXIÓN BD
# ============================================================================

def get_connection(target: IngestTarget):
    return pymysql.connect(
        host=target.db_host, port=target.db_port, user=target.db_user,
        password=target.db_password, database=target.db_name, charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor, autocommit=False,
    )


def load_categorias_map(conn) -> dict:
    with conn.cursor() as cur:
        cur.execute("SELECT ID_Categoria, Slug FROM CATEGORIAS WHERE Activo=1")
        return {r["Slug"]: r["ID_Categoria"] for r in cur.fetchall()}


# ============================================================================
# LIMPIEZA INICIAL: borrar eventos pasados + sus imágenes en disco
# ============================================================================

def purge_past_events(conn, http: httpx.Client, target: IngestTarget, dry_run: bool) -> int:
    """Borra eventos cuya última fecha (Fecha_Fin o Fecha_Inicio) < hoy.
    Borra también sus imágenes (disco local o servidor remoto). CASCADE limpia tablas hijas."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT em.ID_Unico_Evento
            FROM EVENTOS_MASTER em
            JOIN (
                SELECT ID_Unico_Evento,
                       MAX(COALESCE(Fecha_Fin, Fecha_Inicio)) AS ultima
                FROM EVENTO_HORARIOS GROUP BY ID_Unico_Evento
            ) h ON h.ID_Unico_Evento = em.ID_Unico_Evento
            WHERE h.ultima < CURDATE()
        """)
        ids = [r["ID_Unico_Evento"] for r in cur.fetchall()]

    if not ids:
        log.info("Limpieza inicial: no hay eventos pasados que borrar")
        return 0

    log.info(f"Limpieza inicial: {len(ids)} eventos pasados a borrar")
    if dry_run:
        return len(ids)

    for eid in ids:
        if target.store_images_locally:
            event_dir = IMAGES_DIR / eid
            if event_dir.exists():
                shutil.rmtree(event_dir, ignore_errors=True)
        else:
            try:
                _delete_event_images_remote(http, target, eid)
            except httpx.HTTPError as exc:
                log.warning(f"  No se pudieron borrar imágenes remotas de {eid}: {exc}")
        with conn.cursor() as cur:
            cur.execute("DELETE FROM EVENTOS_MASTER WHERE ID_Unico_Evento=%s", (eid,))
    conn.commit()
    return len(ids)


def purge_past_horarios(conn, dry_run: bool) -> int:
    """Borra horarios individuales cuya fecha ya pasó, de eventos que por lo
    demás siguen vigentes (conservan al menos un horario futuro).

    Es necesario porque con la ingesta incremental los eventos ya existentes NO
    se reprocesan; sin esta limpieza, sus horarios caducados (p.ej. las primeras
    sesiones de un ciclo) se quedarían para siempre en EVENTO_HORARIOS.
    purge_past_events ya borra el evento entero cuando TODOS sus horarios pasaron;
    esto cubre el caso parcial (unos pasados, otros futuros)."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT COUNT(*) AS n FROM EVENTO_HORARIOS
            WHERE COALESCE(Fecha_Fin, Fecha_Inicio) < CURDATE()
        """)
        n = cur.fetchone()["n"]

    if not n:
        log.info("Limpieza inicial: no hay horarios pasados sueltos que borrar")
        return 0

    log.info(f"Limpieza inicial: {n} horarios pasados sueltos a borrar")
    if dry_run:
        return n

    with conn.cursor() as cur:
        cur.execute("""
            DELETE FROM EVENTO_HORARIOS
            WHERE COALESCE(Fecha_Fin, Fecha_Inicio) < CURDATE()
        """)
    conn.commit()
    return n


def load_existing_events(conn) -> dict:
    """Mapa poblacion -> [{id, titulo, lugar, fmin, fmax}] ya en EVENTOS_MASTER.

    Se usa para la ingesta incremental: si un evento del listado ya existe en la
    BD (título similar, o mismo lugar con fechas solapadas, en la misma
    población), se omite por completo y no se gasta ni una llamada de
    detalle/cartel/enriquecimiento. El id permite registrar la confirmación
    multi-fuente en EVENTO_FUENTES."""
    out = {}
    with conn.cursor() as cur:
        cur.execute("""
            SELECT em.ID_Unico_Evento, em.Poblacion_Nombre, em.Titulo_CAT,
                   em.Lugar_Nombre,
                   MIN(h.Fecha_Inicio) AS fmin,
                   MAX(COALESCE(h.Fecha_Fin, h.Fecha_Inicio)) AS fmax
            FROM EVENTOS_MASTER em
            LEFT JOIN EVENTO_HORARIOS h ON h.ID_Unico_Evento = em.ID_Unico_Evento
            GROUP BY em.ID_Unico_Evento, em.Poblacion_Nombre, em.Titulo_CAT,
                     em.Lugar_Nombre
        """)
        for r in cur.fetchall():
            pob = r["Poblacion_Nombre"] or ""
            out.setdefault(pob, []).append({
                "id": r["ID_Unico_Evento"],
                "titulo": r["Titulo_CAT"] or "",
                "lugar": r["Lugar_Nombre"] or "",
                "fmin": r["fmin"], "fmax": r["fmax"],
            })
    return out


def buscar_evento_existente(titulo: str, existentes: list, umbral: float,
                            lugar: str = "", fecha: str = ""):
    """Devuelve el {id, ...} del evento ya en BD que casa con el candidato, o
    None si es nuevo. Dos criterios (los mismos que la fusión intra-run):
      1. Título similar (>= umbral).
      2. Mismo lugar normalizado + fecha dentro del rango del evento (±1 día).
         Cubre el mismo evento titulado distinto en otra fuente/otro run
         (caso real: 'Campionat de volei' vs 'La Platja de l'Astillero acull
         el circuit de vòlei platja')."""
    lugar_norm = normalize_place(lugar) if lugar else ""
    fecha_d = None
    if fecha:
        try:
            fecha_d = date.fromisoformat(str(fecha)[:10])
        except (ValueError, TypeError):
            pass
    for e in existentes:
        if titulos_similares(titulo, e["titulo"], umbral):
            return e
        if lugar_norm and fecha_d and e.get("lugar") and e.get("fmin"):
            if normalize_place(e["lugar"]) == lugar_norm:
                fmin, fmax = e["fmin"], e["fmax"] or e["fmin"]
                if (fmin - timedelta(days=1)) <= fecha_d <= (fmax + timedelta(days=1)):
                    return e
    return None


def load_existing_noticias(conn) -> dict:
    """Mapa poblacion -> [{id, titulo, fecha}] de noticias ACTIVAS en BD.
    Omisión incremental + dedupe cross-fuente (ayuntamiento vs radio local)."""
    out = {}
    with conn.cursor() as cur:
        cur.execute("""
            SELECT n.ID_Unico_Noticia, c.Nombre AS Poblacion, n.Titulo_CAT,
                   n.Fecha_Publicacion
            FROM NOTICIAS_MASTER n JOIN CIUDADES c ON c.ID_Ciudad = n.ID_Ciudad
            WHERE n.Estado = 'ACTIVA'
        """)
        for r in cur.fetchall():
            out.setdefault(r["Poblacion"] or "", []).append({
                "id": r["ID_Unico_Noticia"],
                "titulo": r["Titulo_CAT"] or "",
                "fecha": r["Fecha_Publicacion"],
            })
    return out


def purge_noticias_caducadas(conn, http: httpx.Client, target: IngestTarget,
                             dry_run: bool) -> int:
    """Borra FÍSICAMENTE las noticias caducadas (publicadas hace más de
    NEWS_VIGENCIA_DIAS) junto con sus binarios: filas de NOTICIA_BINARIOS
    (CASCADE) e imágenes en disco local o servidor remoto. Las noticias no
    se archivan: pasada la ventana de vigencia, fuera."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT ID_Unico_Noticia FROM NOTICIAS_MASTER
            WHERE COALESCE(Fecha_Caducidad,
                           DATE_ADD(Fecha_Publicacion, INTERVAL %s DAY)) < CURDATE()
        """, (NEWS_VIGENCIA_DIAS,))
        a_borrar = [r["ID_Unico_Noticia"] for r in cur.fetchall()]

    if not a_borrar:
        log.info("Limpieza inicial: no hay noticias caducadas que borrar")
        return 0

    log.info(f"Limpieza inicial: {len(a_borrar)} noticias caducadas a borrar "
             f"(vigencia {NEWS_VIGENCIA_DIAS} días)")
    if dry_run:
        return len(a_borrar)

    for nid in a_borrar:
        if target.store_images_locally:
            ndir = IMAGES_DIR / nid
            if ndir.exists():
                shutil.rmtree(ndir, ignore_errors=True)
        else:
            try:
                _delete_event_images_remote(http, target, nid)
            except httpx.HTTPError as exc:
                log.warning(f"  No se pudieron borrar imágenes remotas de noticia {nid}: {exc}")
        with conn.cursor() as cur:
            # CASCADE limpia NOTICIA_BINARIOS
            cur.execute("DELETE FROM NOTICIAS_MASTER WHERE ID_Unico_Noticia=%s", (nid,))
    conn.commit()
    return len(a_borrar)


def hard_reset_datos(conn, http: httpx.Client, target: IngestTarget,
                     dry_run: bool) -> None:
    """Vacía TODOS los datos generados por la ingesta para empezar de cero:
    eventos, noticias, sus binarios (BD + imágenes en disco/remoto), recintos
    y el estado de los targets (fingerprints/contadores a cero para que todo
    se reprocese). NO toca las tablas maestras/estructurales: CATEGORIAS,
    CIUDADES, CODIGOS_POSTALES, BIBLIOTECA_FUENTES ni las filas de
    SCRAPING_TARGETS (solo se resetea su estado)."""
    with conn.cursor() as cur:
        cur.execute("SELECT COUNT(*) AS n FROM EVENTOS_MASTER")
        n_ev = cur.fetchone()["n"]
        cur.execute("SELECT COUNT(*) AS n FROM NOTICIAS_MASTER")
        n_not = cur.fetchone()["n"]
        # ids con binarios, para el borrado remoto de imágenes
        cur.execute("SELECT DISTINCT ID_Unico_Evento AS id FROM BINARIOS_STORAGE")
        ids_img = [r["id"] for r in cur.fetchall()]
        cur.execute("SELECT DISTINCT ID_Unico_Noticia AS id FROM NOTICIA_BINARIOS")
        ids_img += [r["id"] for r in cur.fetchall()]

    log.warning(f"HARD RESET [{target.name}]: se borrarán {n_ev} eventos, "
                f"{n_not} noticias y {len(ids_img)} carpetas de imágenes")
    if dry_run:
        return

    # Imágenes
    if target.store_images_locally:
        if IMAGES_DIR.exists():
            shutil.rmtree(IMAGES_DIR, ignore_errors=True)
        IMAGES_DIR.mkdir(parents=True, exist_ok=True)
    else:
        for iid in ids_img:
            try:
                _delete_event_images_remote(http, target, iid)
            except httpx.HTTPError as exc:
                log.warning(f"  No se pudieron borrar imágenes remotas de {iid}: {exc}")

    with conn.cursor() as cur:
        # CASCADE limpia horarios, categorías, fuentes y binarios de cada evento
        cur.execute("DELETE FROM EVENTOS_MASTER")
        # CASCADE limpia NOTICIA_BINARIOS
        cur.execute("DELETE FROM NOTICIAS_MASTER")
        # Recintos: generados por la ingesta (ya sin eventos que los referencien)
        cur.execute("DELETE FROM RECINTOS")
        # Targets: misma configuración, estado a cero -> todo se reprocesa
        cur.execute("""
            UPDATE SCRAPING_TARGETS SET
                Estado='PENDIENTE', Http_ETag=NULL, Http_LastModified=NULL,
                Content_Fingerprint=NULL, Last_Changed_At=NULL,
                Last_Run_At=NULL, Next_Run_At=NULL, Intentos=0, Last_Error=NULL,
                Capturas_Utiles_Consecutivas=0, Capturas_Vacias_Consecutivas=0
        """)
    conn.commit()
    log.warning(f"HARD RESET [{target.name}]: completado")


def purge_binarios_huerfanos(conn, target: IngestTarget, dry_run: bool) -> int:
    """Borra del disco local las carpetas de imágenes cuyo id no corresponde a
    ningún evento ni noticia vivos. En Railway no hay listado remoto: allí el
    borrado va siempre guiado por BD (purge_past_events / purge_noticias)."""
    if not target.store_images_locally or not IMAGES_DIR.exists():
        return 0
    with conn.cursor() as cur:
        cur.execute("SELECT ID_Unico_Evento AS id FROM EVENTOS_MASTER")
        vivos = {r["id"] for r in cur.fetchall()}
        cur.execute("SELECT ID_Unico_Noticia AS id FROM NOTICIAS_MASTER WHERE Estado='ACTIVA'")
        vivos |= {r["id"] for r in cur.fetchall()}
    borrados = 0
    for d in IMAGES_DIR.iterdir():
        if d.is_dir() and re.fullmatch(r"[a-f0-9]{64}", d.name) and d.name not in vivos:
            log.info(f"  Carpeta huérfana: {d.name[:16]}…")
            if not dry_run:
                shutil.rmtree(d, ignore_errors=True)
            borrados += 1
    if borrados:
        log.info(f"Limpieza: {borrados} carpetas de imágenes huérfanas borradas")
    return borrados


# ============================================================================
# HTTP + LIMPIEZA HTML
# ============================================================================

def make_http_client():
    return httpx.Client(timeout=HTTP_TIMEOUT, headers={"User-Agent": HTTP_USER_AGENT})


def make_openai_client():
    log.info(f"OpenAI: modelo={LLM_MODEL}, timeout={OPENAI_TIMEOUT}s, "
             f"max_retries={OPENAI_MAX_RETRIES}")
    return OpenAI(timeout=OPENAI_TIMEOUT, max_retries=OPENAI_MAX_RETRIES)


def download_html(url: str, client: httpx.Client) -> str:
    r = client.get(url, follow_redirects=True)
    r.raise_for_status()
    return r.text


def clean_html(html: str) -> str:
    soup = BeautifulSoup(html, "lxml")
    for tag in soup(["script", "style", "head", "nav", "footer",
                     "aside", "noscript", "iframe", "form", "header"]):
        tag.decompose()
    for c in soup.find_all(string=lambda s: isinstance(s, Comment)):
        c.extract()
    main = soup.find("main") or soup.find("article") or soup.body or soup
    text = str(main)
    text = re.sub(r"\n\s*\n", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text


def url_ok(url: str, client: httpx.Client) -> bool:
    """Comprueba que una URL responde 200 (defensa contra links inventados/rotos)."""
    try:
        r = client.get(url, follow_redirects=True)
        return r.status_code == 200 and len(r.text) > 200
    except httpx.HTTPError:
        return False


def descargar_si_ok(url: str, client: httpx.Client) -> Optional[str]:
    """Descarga la URL una sola vez y devuelve el HTML, o None si está rota.
    Sustituye al patrón url_ok()+download_html() que descargaba la página DOS
    veces (una para validar y otra para extraer)."""
    try:
        r = client.get(url, follow_redirects=True)
        if r.status_code == 200 and len(r.text) > 200:
            return r.text
        return None
    except httpx.HTTPError:
        return None


def html_a_texto_enlaces(html: str) -> str:
    """Convierte el HTML limpio en TEXTO VISIBLE con enlaces e imágenes inline
    (estilo markdown: 'ancla (href)' y '[imagen: src]').

    Es la entrada de todas las llamadas LLM de texto: el modelo necesita el
    contenido, las URLs de detalle y las URLs de imagen — NO los divs, clases y
    atributos, que eran ~60-70%% de los tokens pagados. Ahorro directo de input.
    El tope LLM_MAX_INPUT_CHARS protege de páginas monstruosas."""
    soup = BeautifulSoup(clean_html(html), "lxml")
    for a in soup.find_all("a"):
        href = (a.get("href") or "").strip()
        ancla = a.get_text(" ", strip=True)
        if href and not href.startswith(("#", "javascript:")):
            a.replace_with(f" [{ancla}]({href}) ")
        else:
            a.replace_with(f" {ancla} ")
    for img in soup.find_all("img"):
        src = (img.get("src") or img.get("data-src") or "").strip()
        if src:
            img.replace_with(f" [imagen: {src}] ")
        else:
            img.decompose()
    texto = soup.get_text("\n", strip=True)
    texto = re.sub(r"[ \t]+", " ", texto)
    texto = re.sub(r"\n\s*\n+", "\n", texto)
    if len(texto) > LLM_MAX_INPUT_CHARS:
        log.info(f"    Entrada LLM truncada: {len(texto):,} -> "
                 f"{LLM_MAX_INPUT_CHARS:,} chars")
        texto = texto[:LLM_MAX_INPUT_CHARS]
    return texto


def same_or_sub_domain(url: str, base_url: str) -> bool:
    try:
        n1 = urlparse(url).netloc.lower()
        n2 = urlparse(base_url).netloc.lower()
        # comparar dominio registrable de forma laxa
        return n1.endswith(n2.split("www.")[-1]) or n2.endswith(n1.split("www.")[-1])
    except Exception:
        return False


# ============================================================================
# LLM: SCHEMAS
# ============================================================================

LISTING_SCHEMA = {
    "name": "events_from_listing", "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "eventos": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "titulo": {"type": "string", "description": "Título limpio, sin fechas ni horas mezcladas."},
                        "fecha_inicio": {"type": "string", "description": "YYYY-MM-DD. Convierte fechas relativas ('avui','demà') y catalanas ('5 maig') usando la fecha de hoy dada."},
                        "hora_inicio": {"type": ["string", "null"], "description": "HH:MM 24h o null."},
                        "hora_fin": {"type": ["string", "null"], "description": "HH:MM o null. SOLO si aparece explícitamente un rango/hora fin. NO la inventes."},
                        "url_detalle": {"type": ["string", "null"], "description": "URL ABSOLUTA y REAL a la página de detalle. Si no encuentras una URL clara y completa, devuelve null. NUNCA inventes ni completes URLs parciales."},
                        "lugar_corto": {"type": ["string", "null"], "description": "Lugar tal como aparece en el listado."},
                        "imagen_url": {"type": ["string", "null"], "description": "URL absoluta de imagen si aparece."},
                    },
                    "required": ["titulo", "fecha_inicio", "hora_inicio", "hora_fin", "url_detalle", "lugar_corto", "imagen_url"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["eventos"], "additionalProperties": False,
    },
}

DETAIL_SCHEMA = {
    "name": "event_detail", "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "titulo": {"type": ["string", "null"], "description": "Título del evento tal como aparece en la página. null si no se distingue."},
            "fecha_inicio": {"type": ["string", "null"], "description": "YYYY-MM-DD de inicio del evento si aparece en la página. null si no."},
            "descripcion_larga": {"type": ["string", "null"], "description": "Solo texto descriptivo del evento, sin menús ni breadcrumbs."},
            "fecha_fin": {"type": ["string", "null"], "description": "YYYY-MM-DD solo si el evento es un rango CONTINUO de varios días (ej: 'del 2 al 30 de mayo'). null si es un solo día o si las fechas son discretas."},
            "hora_inicio": {"type": ["string", "null"]},
            "hora_fin": {"type": ["string", "null"], "description": "Solo si aparece explícito. No inventar."},
            "lugar_nombre": {"type": ["string", "null"]},
            "direccion_fisica": {"type": ["string", "null"]},
            "organizador_nombre": {"type": ["string", "null"]},
            "es_gratuito": {"type": ["boolean", "null"]},
            "precio_euros": {"type": ["number", "null"]},
            "link_inscripcion": {"type": ["string", "null"]},
            "imagenes_urls": {"type": "array", "items": {"type": "string"},
                              "description": "URLs absolutas de TODAS las imágenes del evento, primera = principal. [] si ninguna. NO iconos ni logos."},
            "horarios_discretos": {
                "type": "array",
                "description": (
                    "Si el evento ocurre en fechas DISCRETAS no consecutivas "
                    "(ej: '8, 15, 22 y 29 de mayo', 'los jueves 14, 21 y 28'), "
                    "devuelve cada fecha como objeto separado. "
                    "Si es un rango continuo ('del 2 al 30') o un solo día, "
                    "devuelve [] y usa fecha_fin en su lugar. "
                    "Prioridad: si hay fechas discretas, siempre usar este campo."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "fecha": {"type": "string", "description": "YYYY-MM-DD"},
                        "hora_inicio": {"type": ["string", "null"], "description": "HH:MM o null"},
                        "hora_fin": {"type": ["string", "null"], "description": "HH:MM o null. No inventar."},
                    },
                    "required": ["fecha", "hora_inicio", "hora_fin"],
                    "additionalProperties": False,
                },
            },
        },
        "required": ["titulo", "fecha_inicio", "descripcion_larga", "fecha_fin",
                     "hora_inicio", "hora_fin",
                     "lugar_nombre", "direccion_fisica", "organizador_nombre",
                     "es_gratuito", "precio_euros", "link_inscripcion",
                     "imagenes_urls", "horarios_discretos"],
        "additionalProperties": False,
    },
}

ENRICHMENT_SCHEMA = {
    "name": "event_enrichment", "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "titulo_ca": {
                "type": "string",
                "description": ("Título en catalán. Si el original ya es catalán, "
                                "límpialo/normalízalo; si está en castellano, tradúcelo. "
                                "Mantén nombres propios."),
            },
            "titulo_es": {
                "type": "string",
                "description": ("Título en castellano. Si el original ya es castellano, "
                                "límpialo/normalízalo; si está en catalán, tradúcelo. "
                                "Mantén nombres propios."),
            },
            "desc_larga_ca": {
                "type": "string",
                "description": ("Descripción larga en catalán. '' si no hay descripción. "
                                "Si el original es castellano, tradúcelo; si ya es catalán, "
                                "conserva el sentido limpiando basura de UI."),
            },
            "desc_larga_es": {
                "type": "string",
                "description": ("Descripción larga en castellano. '' si vacía. "
                                "Traduce o limpia según el idioma del original."),
            },
            "desc_corta_ca": {
                "type": "string",
                "description": ("Resumen en catalán para LECTURA RÁPIDA en una tarjeta: "
                                "2-3 frases, máximo ~300 caracteres. Qué es, qué se hará y "
                                "para quién. NO repitas el título, NO repitas fecha/hora/lugar "
                                "(la tarjeta ya los muestra), sin relleno institucional."),
            },
            "desc_corta_es": {
                "type": "string",
                "description": "El mismo resumen en castellano.",
            },
            "tags_ca": {
                "type": "array", "items": {"type": "string"}, "minItems": 5, "maxItems": 10,
                "description": ("5-10 tags GENÉRICOS en catalán para búsqueda. Conceptos amplios "
                                "(tipo de actividad, público, ámbito). PROHIBIDO nombres propios "
                                "(personas, obras, grupos, lugares concretos) y palabras-acción del "
                                "título. EJEMPLO: para teatro 'Pijames' de Marc Camoletti en Centre "
                                "Cultural -> ['teatre','comèdia','arts escèniques','espectacle','cultura']; "
                                "NO 'Marc Camoletti' ni 'Centre Cultural'. "
                                "IMPORTANTE: si el evento es DEPORTIVO, NO uses 'oci'/'ocio' como tag.")
            },
            "tags_es": {"type": "array", "items": {"type": "string"}, "minItems": 5, "maxItems": 10,
                        "description": "Mismos tags en castellano, mismo orden. Si es deportivo, NO incluyas 'ocio'."},
            "categorias_codigos": {
                "type": "array", "items": {"type": "string", "enum": ALL_CATEGORY_SLUGS},
                "minItems": 1, "maxItems": 3,
                "description": ("Categorías del catálogo. Si una subcategoría encaja, úsala (más "
                                "específica); si no, el padre. NO mezcles padre y subcategoría del "
                                "mismo árbol. Un evento DEPORTIVO va en 'deportes', NUNCA en 'ocio'.")
            },
            "categoria_principal": {"type": "string", "enum": ALL_CATEGORY_SLUGS,
                                    "description": "La más representativa. Debe estar en categorias_codigos."},
            "recinto_canonico": {
                "type": "string",
                "description": ("Nombre canónico LIMPIO del recinto, sin detalles de pista/sala. "
                                "Ej: 'Ciutat Esportiva Blanes. Pista vermella i pistes verdes Q3 i Q4' "
                                "-> 'Ciutat Esportiva Blanes'. Si no hay lugar claro, devuelve ''.")
            },
            "recinto_tipo": {"type": "string", "enum": RECINTO_TIPOS,
                             "description": "Tipo de recinto. OTRO si no encaja en biblioteca/centro cultural/teatro/parque."},
            "evento_paraguas": {
                "type": ["string", "null"],
                "description": ("Si el evento FORMA PARTE de un festival, fira, ciclo o "
                                "programa mayor, el NOMBRE CANÓNICO de ese evento paraguas, "
                                "limpio y corto (ej: para 'Festival Libèl·lula: taller de "
                                "xapes' -> 'Festival Libèl·lula'; para una nota del "
                                "festival entero -> 'Festival Libèl·lula' también). "
                                "null si es un evento independiente que no cuelga de nada."),
            },
        },
        "required": ["titulo_ca", "titulo_es", "desc_larga_ca", "desc_larga_es",
                     "desc_corta_ca", "desc_corta_es",
                     "tags_ca", "tags_es",
                     "categorias_codigos", "categoria_principal",
                     "recinto_canonico", "recinto_tipo", "evento_paraguas"],
        "additionalProperties": False,
    },
}


# Cartel-OCR: schema para extraer datos faltantes desde la imagen del cartel.
# Se invoca solo cuando el HTML deja datos clave sin rellenar.
CARTEL_SCHEMA = {
    "name": "cartel_ocr", "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "tiene_texto_util": {
                "type": "boolean",
                "description": (
                    "true SOLO si el cartel contiene texto legible con información "
                    "de evento (fechas, horas, lugar, programa). false si es una "
                    "imagen decorativa, foto sin texto, o texto irrelevante."
                ),
            },
            "horarios_discretos": {
                "type": "array",
                "description": (
                    "Si el cartel menciona varias fechas/sesiones discretas (un "
                    "concurso con varias jornadas, un ciclo con varios días, "
                    "talleres en días concretos), devuelve cada una como objeto. "
                    "Si es un único día/rango, devuelve []. NO inventes fechas: "
                    "si el año no aparece, asume el año actual."
                ),
                "items": {
                    "type": "object",
                    "properties": {
                        "fecha": {"type": "string", "description": "YYYY-MM-DD"},
                        "hora_inicio": {"type": ["string", "null"], "description": "HH:MM o null"},
                        "hora_fin": {"type": ["string", "null"], "description": "HH:MM o null. No inventar."},
                    },
                    "required": ["fecha", "hora_inicio", "hora_fin"],
                    "additionalProperties": False,
                },
            },
            "hora_inicio": {
                "type": ["string", "null"],
                "description": "HH:MM si el cartel indica hora única para todo el evento.",
            },
            "hora_fin": {
                "type": ["string", "null"],
                "description": "HH:MM si el cartel indica hora de fin. No inventar.",
            },
            "lugar_nombre": {
                "type": ["string", "null"],
                "description": "Nombre del lugar/recinto si aparece (ej: 'Centre Cultural').",
            },
            "direccion_fisica": {
                "type": ["string", "null"],
                "description": "Dirección postal completa si aparece.",
            },
            "organizador_nombre": {
                "type": ["string", "null"],
                "description": "Quién organiza (ej: 'Ajuntament de Blanes', 'Consell Esportiu La Selva').",
            },
            "es_gratuito": {
                "type": ["boolean", "null"],
                "description": "true/false si el cartel lo indica claramente. null si no se sabe.",
            },
            "precio_euros": {
                "type": ["number", "null"],
                "description": "Precio en euros si aparece. null si gratuito o no aparece.",
            },
            "info_adicional": {
                "type": ["string", "null"],
                "description": (
                    "Información relevante del cartel que NO encaje en otros campos, "
                    "redactada como prosa corta (ej: 'Actividad para jóvenes de 1º a 4º "
                    "de ESO; 4 barrios participan: Valldolig, Mas Cremat, La Plantera, "
                    "4 Vents'). null si nada relevante."
                ),
            },
        },
        "required": ["tiene_texto_util", "horarios_discretos", "hora_inicio",
                     "hora_fin", "lugar_nombre", "direccion_fisica",
                     "organizador_nombre", "es_gratuito", "precio_euros",
                     "info_adicional"],
        "additionalProperties": False,
    },
}


# Clasificación de listados MIXTOS/NOTICIAS: separa eventos de noticias en una
# sola llamada. Las fuentes con Tipo_Contenido=EVENTOS no pasan por aquí
# (van directas a LISTING_SCHEMA, sin coste extra).
CLASIFICACION_SCHEMA = {
    "name": "items_clasificados", "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "tipo": {
                            "type": "string", "enum": ["EVENTO", "NOTICIA", "DESCARTAR"],
                            "description": ("EVENTO: actividad con fecha/hora futura a la que se puede "
                                            "asistir (concierto, taller, fiesta, exposición...). "
                                            "NOTICIA: información/comunicado sin asistencia (obras, "
                                            "subvenciones, resultados, avisos de servicio). "
                                            "DESCARTAR: menús, banners, contenido sin valor."),
                        },
                        "titulo": {"type": "string", "description": "Título limpio del item."},
                        "url_detalle": {"type": ["string", "null"], "description": "URL ABSOLUTA y REAL a la página del item. null si no hay. NUNCA inventes."},
                        "fecha": {"type": ["string", "null"], "description": "YYYY-MM-DD. Para EVENTO: fecha de celebración. Para NOTICIA: fecha de publicación. null si no aparece."},
                        "hora_inicio": {"type": ["string", "null"], "description": "HH:MM solo para EVENTO si aparece."},
                        "lugar_corto": {"type": ["string", "null"], "description": "Lugar solo para EVENTO si aparece."},
                        "imagen_url": {"type": ["string", "null"], "description": "URL absoluta de imagen si aparece."},
                    },
                    "required": ["tipo", "titulo", "url_detalle", "fecha",
                                 "hora_inicio", "lugar_corto", "imagen_url"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["items"], "additionalProperties": False,
    },
}

# Detalle de una noticia: cuerpo, fecha de publicación e imagen.
NOTICIA_DETAIL_SCHEMA = {
    "name": "noticia_detail", "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "titulo": {"type": ["string", "null"], "description": "Título de la noticia. null si no se distingue."},
            "cuerpo": {"type": ["string", "null"], "description": "Texto completo de la noticia, sin menús ni pies de página. Conserva párrafos."},
            "fecha_publicacion": {"type": ["string", "null"], "description": "YYYY-MM-DD de publicación si aparece. null si no."},
            "idioma": {"type": "string", "enum": ["ca", "es"], "description": "Idioma principal del texto."},
            "imagen_url": {"type": ["string", "null"], "description": "URL absoluta de la imagen principal. null si no hay. NO iconos ni logos."},
        },
        "required": ["titulo", "cuerpo", "fecha_publicacion", "idioma", "imagen_url"],
        "additionalProperties": False,
    },
}

# Enriquecimiento de noticia: traducción bilingüe + tags. Sin categorías,
# sin recinto, sin cartel-OCR (mucho más barato que el de eventos).
NOTICIA_ENRICH_SCHEMA = {
    "name": "noticia_enrichment", "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "titulo_ca": {"type": "string", "description": "Título en catalán (traduce si el original es castellano)."},
            "titulo_es": {"type": "string", "description": "Título en castellano (traduce si el original es catalán)."},
            "cuerpo_ca": {"type": "string", "description": "Cuerpo en catalán. '' si vacío."},
            "cuerpo_es": {"type": "string", "description": "Cuerpo en castellano. '' si vacío."},
            "resumen_ca": {
                "type": "string",
                "description": ("Resumen en catalán para LECTURA RÁPIDA: 2-3 frases, "
                                "máximo ~300 caracteres, con el dato esencial de la "
                                "noticia. NO repitas el título, sin relleno institucional."),
            },
            "resumen_es": {"type": "string", "description": "El mismo resumen en castellano."},
            "tags_ca": {"type": "array", "items": {"type": "string"}, "minItems": 3, "maxItems": 8,
                        "description": "3-8 tags GENÉRICOS en catalán (temática, ámbito, público). PROHIBIDO nombres propios."},
            "tags_es": {"type": "array", "items": {"type": "string"}, "minItems": 3, "maxItems": 8,
                        "description": "Mismos tags en castellano, mismo orden."},
        },
        "required": ["titulo_ca", "titulo_es", "cuerpo_ca", "cuerpo_es",
                     "resumen_ca", "resumen_es", "tags_ca", "tags_es"],
        "additionalProperties": False,
    },
}

# Clasificación en lote de mensajes de Telegram: cada mensaje es EVENTO (con
# datos extraídos del propio texto), NOTICIA o DESCARTAR.
TELEGRAM_BATCH_SCHEMA = {
    "name": "telegram_mensajes", "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "mensajes": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "indice": {"type": "integer", "description": "Índice del mensaje tal como se ha numerado en la entrada."},
                        "tipo": {
                            "type": "string", "enum": ["EVENTO", "NOTICIA", "DESCARTAR"],
                            "description": ("EVENTO: anuncia una actividad con fecha a la que asistir. "
                                            "NOTICIA: información municipal (avisos, obras, comunicados, "
                                            "resultados). DESCARTAR: saludos, reenvíos sin contenido, "
                                            "encuestas, mensajes sin valor informativo."),
                        },
                        "titulo": {"type": ["string", "null"], "description": "Título corto y descriptivo deducido del mensaje (máx ~100 chars). null si DESCARTAR."},
                        "fecha": {"type": ["string", "null"], "description": "Para EVENTO: YYYY-MM-DD de celebración. Resuelve relativas ('aquest dissabte','demà') respecto a la fecha de publicación del mensaje, NO respecto a hoy. null si no aparece o no es evento."},
                        "hora_inicio": {"type": ["string", "null"], "description": "HH:MM del evento si aparece."},
                        "lugar": {"type": ["string", "null"], "description": "Lugar del evento si aparece."},
                    },
                    "required": ["indice", "tipo", "titulo", "fecha", "hora_inicio", "lugar"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["mensajes"], "additionalProperties": False,
    },
}


# ============================================================================
# LLM: LLAMADAS
# ============================================================================

def llm_json(oai, pob, system, user, schema, op="otros", context: str = ""):
    ctx = f" — {context}" if context else ""
    log.info(f"    LLM [{op}]{ctx}: enviando ~{len(user):,} chars...")
    t0 = time.monotonic()
    try:
        resp = oai.chat.completions.create(
            model=LLM_MODEL,
            messages=[{"role": "system", "content": system},
                      {"role": "user", "content": user}],
            response_format={"type": "json_schema", "json_schema": schema},
            temperature=0,
        )
    except Exception as exc:
        log.error(f"    LLM [{op}] falló tras {time.monotonic() - t0:.1f}s: {exc}")
        raise
    elapsed = time.monotonic() - t0
    COST.add_llm(pob, resp, op)
    log.info(f"    LLM [{op}] OK en {elapsed:.1f}s")
    return json.loads(resp.choices[0].message.content)


def extract_listing(oai, pob, html_clean, listado_url):
    today = date.today().isoformat()
    system = (
        "Eres un extractor de eventos de agendas municipales catalanas/españolas. "
        f"Hoy es {today}. Devuelve los eventos del listado en JSON. "
        "Reglas estrictas:\n"
        "(1) Fechas absolutas YYYY-MM-DD. Convierte relativas ('avui','demà') y catalanas.\n"
        "(2) DEDUPLICACIÓN solo por URL: si el mismo título aparece N veces con la "
        "MISMA url_detalle (o sin url_detalle), devuélvelo UNA sola vez con la primera "
        "fecha. Esto es para exposiciones que el listado repite un día por fila.\n"
        "(3) Si el mismo título aparece N veces con URLs DE DETALLE DISTINTAS, "
        "devuélvelos TODOS como entradas separadas: son sesiones o funciones distintas "
        "del mismo evento (p.ej. tres funciones de teatro, un ciclo de conciertos).\n"
        "(4) URLs absolutas y reales. Si no encuentras URL clara, null. NUNCA inventes.\n"
        "(5) Solo eventos futuros o en curso."
    )
    user = f"URL listado: {listado_url}\n\nHTML:\n{html_clean}"
    data = llm_json(oai, pob, system, user, LISTING_SCHEMA,
                    op="listado", context=listado_url)
    items = data.get("eventos", [])
    for it in items:
        if it.get("url_detalle"):
            it["url_detalle"] = urljoin(listado_url, it["url_detalle"])
        if it.get("imagen_url"):
            it["imagen_url"] = urljoin(listado_url, it["imagen_url"])
    return items


def extract_detail(oai, pob, html_clean, url):
    system = ("Extractor de detalles de eventos municipales. Devuelve JSON con los "
              "campos pedidos. No inventes datos (null si no aparecen). URLs absolutas. "
              "Descripción: solo el texto del evento.")
    user = f"URL: {url}\n\nHTML:\n{html_clean}"
    data = llm_json(oai, pob, system, user, DETAIL_SCHEMA, op="detalle", context=url)
    imgs = [urljoin(url, u) for u in (data.get("imagenes_urls") or []) if u]
    data["imagenes_urls"] = imgs
    if data.get("link_inscripcion"):
        data["link_inscripcion"] = urljoin(url, data["link_inscripcion"])
    return data


# ============================================================================
# CARTEL-OCR: extracción multimodal cuando el HTML deja huecos críticos
# ============================================================================

def cartel_ocr_es_necesario(detail: dict) -> bool:
    """Decide si vale la pena leer el cartel. Solo si tiene imagen Y le falta
    info crítica (hora, lugar) o la descripción es muy pobre."""
    if not (detail.get("imagenes_urls") or []):
        return False  # sin imagen no hay nada que leer
    falta_hora = not detail.get("hora_inicio")
    falta_lugar = not detail.get("lugar_nombre")
    falta_horarios = not (detail.get("horarios_discretos") or [])
    desc_corta = len((detail.get("descripcion_larga") or "")) < 200
    # disparar si hay falta de tiempo/lugar Y poca descripción
    return (falta_hora or falta_lugar or falta_horarios) and desc_corta


def extract_cartel(oai, pob, http, image_url: str, today_iso: str) -> Optional[dict]:
    """Llama al modelo multimodal con la imagen del cartel para extraer datos
    estructurados. Devuelve None si la imagen no se puede descargar o el
    modelo dice que no tiene texto útil."""
    try:
        # Descargar la imagen y convertirla a base64 para la API multimodal
        r = http.get(image_url, follow_redirects=True)
        r.raise_for_status()
        import base64
        img_b64 = base64.b64encode(r.content).decode("ascii")
        # detectar mime básico
        ct = r.headers.get("content-type", "image/jpeg").split(";")[0].strip()
        if not ct.startswith("image/"):
            ct = "image/jpeg"
        data_url = f"data:{ct};base64,{img_b64}"
    except Exception as e:
        log.warning(f"    Cartel-OCR: no se pudo descargar imagen ({e})")
        return None

    system = (
        "Eres un extractor de datos de carteles de eventos municipales catalanes. "
        f"La fecha actual es {today_iso}. Lees la imagen y devuelves JSON con los "
        "datos que aparezcan EXPLÍCITAMENTE en el cartel. "
        "REGLAS: (1) no inventes datos, si algo no se ve devuelve null; "
        "(2) si el cartel es decorativo o no tiene texto útil, marca "
        "tiene_texto_util=false y deja todo lo demás vacío/null; "
        "(3) para fechas usa YYYY-MM-DD; (4) si aparece un calendario de varias "
        "sesiones, devuélvelas en horarios_discretos."
    )

    log.info(f"    LLM [cartel] — {image_url}: leyendo cartel...")
    t0 = time.monotonic()
    try:
        resp = oai.chat.completions.create(
            model=LLM_MODEL,
            messages=[
                {"role": "system", "content": system},
                {"role": "user", "content": [
                    {"type": "text", "text": "Extrae los datos del cartel."},
                    {"type": "image_url", "image_url": {"url": data_url}},
                ]},
            ],
            response_format={"type": "json_schema", "json_schema": CARTEL_SCHEMA},
            temperature=0,
        )
        COST.add_llm(pob, resp, op="cartel")
        log.info(f"    LLM [cartel] OK en {time.monotonic() - t0:.1f}s")
        data = json.loads(resp.choices[0].message.content)
        if not data.get("tiene_texto_util"):
            log.info(f"    Cartel-OCR: imagen sin texto útil, descartada")
            return None
        return data
    except Exception as e:
        log.warning(f"    Cartel-OCR falló tras {time.monotonic() - t0:.1f}s: {e}")
        return None


def aplicar_cartel_al_detalle(detail: dict, cartel: dict):
    """Mezcla los datos del cartel sobre el detalle del HTML. Regla: el cartel
    RELLENA huecos, no pisa datos del HTML que ya estaban presentes."""
    if not cartel:
        return
    # campos simples: solo se rellenan si están vacíos en el detalle
    for campo in ["hora_inicio", "hora_fin", "lugar_nombre", "direccion_fisica",
                  "organizador_nombre"]:
        if not detail.get(campo) and cartel.get(campo):
            detail[campo] = cartel[campo]
    # gratuito/precio: solo si el HTML no dijo nada
    if detail.get("es_gratuito") is None and cartel.get("es_gratuito") is not None:
        detail["es_gratuito"] = cartel["es_gratuito"]
    if detail.get("precio_euros") is None and cartel.get("precio_euros") is not None:
        detail["precio_euros"] = cartel["precio_euros"]
    # horarios discretos: el cartel manda si el HTML no traía ninguno
    if not detail.get("horarios_discretos") and cartel.get("horarios_discretos"):
        detail["horarios_discretos"] = cartel["horarios_discretos"]
    # info adicional del cartel se concatena a la descripción si aporta
    info = (cartel.get("info_adicional") or "").strip()
    if info:
        desc = (detail.get("descripcion_larga") or "").strip()
        detail["descripcion_larga"] = (desc + "\n\n" + info).strip() if desc else info


ENRICH_SYSTEM = (
    "Enriqueces eventos municipales catalanes. El título y la descripción de "
    "entrada pueden estar en catalán o en castellano (a veces mezclados). "
    "Devuelve SIEMPRE título y descripción larga en ambos idiomas (CA y ES), "
    "más resumen corto bilingüe, tags genéricos bilingües, categorías del "
    "catálogo cerrado, y el recinto canónico limpio con su tipo. Traduce con "
    "naturalidad manteniendo nombres propios. Tags = conceptos de búsqueda, "
    "nunca nombres propios ni el lugar. Un evento DEPORTIVO va en 'deportes' "
    "y no lleva tag 'ocio'."
)


def enrich(oai, pob, ev: MergedEvent):
    user = (f"TÍTULO (idioma desconocido):\n{ev.titulo}\n\n"
            f"DESCRIPCIÓN (idioma desconocido):\n{ev.descripcion_larga}\n\n"
            f"LUGAR (crudo): {ev.lugar}\n"
            f"ORGANIZADOR: {ev.organizador_nombre}")
    d = llm_json(oai, pob, ENRICH_SYSTEM, user, ENRICHMENT_SCHEMA,
                 op="enriquecimiento", context=ev.titulo[:60])
    # Canonical CA fields (persistidos como Titulo_CAT / Desc_Larga_CAT)
    ev.titulo = (d.get("titulo_ca") or "").strip() or ev.titulo
    ev.descripcion_larga = (d.get("desc_larga_ca") or "").strip() or ev.descripcion_larga
    ev.titulo_es = (d.get("titulo_es") or "").strip() or ev.titulo
    ev.desc_larga_es = (d.get("desc_larga_es") or "").strip()
    ev.desc_corta = (d.get("desc_corta_ca") or "").strip()[:500]
    ev.desc_corta_es = (d.get("desc_corta_es") or "").strip()[:500]
    ev.tags_ca = d["tags_ca"]
    ev.tags_es = d["tags_es"]
    cats = list(d["categorias_codigos"])
    # limpiar mezcla padre+subcategoría
    subs = {c for c in cats if c in SUBCATEGORY_TO_PARENT}
    parents_rm = {SUBCATEGORY_TO_PARENT[s] for s in subs}
    cats = [c for c in cats if c not in parents_rm] or cats
    ev.categorias = cats
    ev.categoria_principal = d["categoria_principal"]
    if ev.categoria_principal in parents_rm:
        for s in subs:
            if SUBCATEGORY_TO_PARENT[s] == ev.categoria_principal:
                ev.categoria_principal = s
                break
    if ev.categoria_principal not in ev.categorias:
        ev.categorias.insert(0, ev.categoria_principal)
    ev.recinto_canonico = (d.get("recinto_canonico") or "").strip()
    ev.recinto_tipo = d.get("recinto_tipo") or "OTRO"
    # Evento paraguas (festival/ciclo): LLM primero, heurística "X: Y" de respaldo
    ev.evento_paraguas = (d.get("evento_paraguas") or "").strip() \
        or deducir_paraguas_por_titulo(ev.titulo)


# ============================================================================
# EXTRACCIÓN DE UNA FUENTE (un link) -> lista de Candidate
# ============================================================================

def procesar_item_evento(oai, http, pob, cp, it, listado_url, detail_cache, ctx) -> Candidate:
    """Convierte un item de listado (titulo, fecha, url_detalle...) en Candidate,
    bajando la página de detalle y aplicando cartel-OCR si procede. Compartido
    por la ruta de eventos clásica, el clasificador mixto y Telegram.
    ctx = {"details_done": int} (contador mutable compartido por fuente)."""
    titulo = (it.get("titulo") or "").strip()
    cand = Candidate(
        poblacion=pob, cp=cp, titulo=titulo,
        lugar=(it.get("lugar_corto") or "").strip(),
        fuente_url=it.get("url_detalle") or listado_url,
        fuente_listado=listado_url,
        fecha_inicio=(it.get("fecha_inicio") or "").strip(),
        hora_inicio=it.get("hora_inicio"),
        hora_fin=it.get("hora_fin"),
        imagenes=[it["imagen_url"]] if it.get("imagen_url") else [],
    )

    url_det = it.get("url_detalle")
    if url_det and same_or_sub_domain(url_det, listado_url):
        if url_det in detail_cache:
            detail = detail_cache[url_det]
        elif ctx["details_done"] >= MAX_DETAIL_PAGES_PER_SOURCE:
            log.warning(f"    Tope de detalles ({MAX_DETAIL_PAGES_PER_SOURCE}) alcanzado")
            detail = None
        else:
            # una sola descarga: valida y extrae con el mismo GET
            html_det = descargar_si_ok(url_det, http)
            if html_det is None:
                log.warning(f"    URL de detalle rota, descartada: {url_det}")
                detail = None
            else:
                try:
                    log.info(f"    Detalle [{ctx['details_done'] + 1}]: {titulo[:60]}")
                    detail = extract_detail(oai, pob, html_a_texto_enlaces(html_det), url_det)
                    detail_cache[url_det] = detail
                    ctx["details_done"] += 1
                except Exception as e:
                    log.error(f"    Error en detalle {url_det}: {e}")
                    detail = None

        if detail:
            aplicar_detalle_a_candidato(oai, http, pob, cand, detail)

    return cand


def aplicar_detalle_a_candidato(oai, http, pob, cand: Candidate, detail: dict):
    """Vuelca un dict de DETAIL_SCHEMA sobre el Candidate, con gate de
    cartel-OCR si el detalle quedó incompleto."""
    # Gate de cartel-OCR: si faltan datos clave Y hay imagen, intentar
    # leer el cartel para rellenar huecos antes de aplicar al candidato.
    if cartel_ocr_es_necesario(detail):
        img_principal = detail["imagenes_urls"][0]
        log.info(f"    Cartel-OCR: detalle incompleto, leyendo cartel...")
        cartel = extract_cartel(oai, pob, http, img_principal,
                                date.today().isoformat())
        if cartel:
            aplicar_cartel_al_detalle(detail, cartel)
            log.info(f"    Cartel-OCR: datos del cartel aplicados")

    cand.descripcion_larga = detail.get("descripcion_larga") or ""
    cand.fecha_fin = detail.get("fecha_fin")
    cand.hora_inicio = cand.hora_inicio or detail.get("hora_inicio")
    cand.hora_fin = cand.hora_fin or detail.get("hora_fin")
    if detail.get("lugar_nombre"):
        cand.lugar = detail["lugar_nombre"]
    cand.direccion_fisica = detail.get("direccion_fisica") or ""
    cand.organizador_nombre = detail.get("organizador_nombre") or ""
    # De pago SOLO con precio concreto > 0; sin precio (o 0) ⇒ gratuito
    precio = detail.get("precio_euros")
    if precio is not None and float(precio) > 0:
        cand.precio_euros = float(precio)
        cand.es_gratuito = 0
    else:
        cand.precio_euros = None
        cand.es_gratuito = 1
    cand.link_inscripcion = detail.get("link_inscripcion") or ""
    if detail.get("imagenes_urls"):
        cand.imagenes = detail["imagenes_urls"]
    # Fechas discretas: si el LLM las detectó (HTML o cartel), construir Horario
    disc = detail.get("horarios_discretos") or []
    if disc:
        cand.horarios_extra = [
            Horario(
                fecha_inicio=h["fecha"],
                fecha_fin=None,
                hora_inicio=h.get("hora_inicio"),
                hora_fin=h.get("hora_fin"),
            )
            for h in disc if h.get("fecha")
        ]
        # Sincronizar: la primera fecha discreta pisa fecha_inicio del candidato
        if cand.horarios_extra:
            cand.fecha_inicio = cand.horarios_extra[0].fecha_inicio
            cand.fecha_fin = None  # ya no es un rango continuo


def scrape_source(oai, http, pob, cp, listado_url, dry_run,
                  existing_events=None, umbral=SIMILARITY_THRESHOLD,
                  refresh=False, confirmaciones=None, listing_html=None,
                  max_nuevos=None) -> list:
    """Extrae candidatos de un listado de eventos. Si listing_html viene dado
    (ruta de targets en BD, ya descargado por fetch_si_cambiado) no se vuelve a
    descargar. confirmaciones: lista mutable donde se anotan (id_evento, url)
    de los omitidos por ya existir, para registrar la fuente en EVENTO_FUENTES."""
    existing_events = existing_events or []
    log.info(f"  Link: {listado_url}")
    if listing_html is None:
        try:
            listing_html = download_html(listado_url, http)
        except httpx.HTTPError as e:
            log.error(f"    No se pudo descargar el listado: {e}")
            return []

    html_clean = html_a_texto_enlaces(listing_html)
    log.info(f"    Extrayendo listado con LLM ({len(html_clean):,} chars texto+enlaces)...")
    items = extract_listing(oai, pob, html_clean, listado_url)
    log.info(f"    {len(items)} eventos en el listado")

    candidates = []
    detail_cache = {}
    ctx = {"details_done": 0}
    omitidos = 0  # ya existentes en BD: no se reprocesan (ahorro de coste)

    for it in items:
        if max_nuevos is not None and len(candidates) >= max_nuevos:
            log.info(f"    Límite de prueba alcanzado ({max_nuevos} items nuevos): "
                     f"resto del listado omitido")
            break
        titulo = (it.get("titulo") or "").strip()
        fecha_inicio = (it.get("fecha_inicio") or "").strip()
        if not titulo or not fecha_inicio:
            continue

        # Ingesta incremental: si el evento ya está en la BD (mismo título o
        # suficientemente similar en esta población), se omite por completo: no
        # se baja el detalle, no se lee el cartel, no se enriquece ni se
        # descargan imágenes. Es el grueso del ahorro de coste por ejecución.
        if not refresh:
            existente = buscar_evento_existente(titulo, existing_events, umbral,
                                                it.get("lugar_corto") or "",
                                                fecha_inicio)
            if existente:
                omitidos += 1
                if confirmaciones is not None:
                    confirmaciones.append(
                        (existente["id"], it.get("url_detalle") or listado_url))
                continue

        candidates.append(
            procesar_item_evento(oai, http, pob, cp, it, listado_url, detail_cache, ctx))

    if omitidos:
        log.info(f"    Omitidos por ya existir en BD: {omitidos} · "
                 f"nuevos a procesar: {len(candidates)}")
    return candidates


# ============================================================================
# FUSIÓN: candidatos -> MergedEvent (por cercanía de título + solape de fechas)
# ============================================================================

def _build_merged_from_cluster(cluster: list, poblacion: str) -> MergedEvent:
    """Construye un MergedEvent a partir de un grupo de candidatos que son el
    mismo evento. El ID se deriva del representante (título alfabéticamente
    menor) para ser determinista. Los datos base salen del candidato más rico
    (descripción más larga). Lugar/dirección/organizador: primer no vacío."""
    # representante determinista: título normalizado alfabéticamente menor
    representante = min(cluster, key=lambda c: normalize_title(c.titulo))
    eid = event_id_from_title(poblacion, representante.titulo)

    # datos descriptivos: el candidato con descripción más larga
    base = max(cluster, key=lambda c: len(c.descripcion_larga or ""))

    def primer_no_vacio(attr):
        for c in cluster:
            v = (getattr(c, attr) or "").strip()
            if v:
                return v
        return ""

    horarios, seen_h = [], set()
    fuentes, seen_f = [], set()
    imagenes, seen_i = [], set()
    # De pago SOLO si hay un precio concreto > 0. precio=0/null = gratuito.
    es_gratuito = 1
    precio = None

    for c in cluster:
        # Si el candidato tiene fechas discretas, usarlas en lugar del horario simple
        horarios_candidato = c.horarios_extra if c.horarios_extra else [
            Horario(c.fecha_inicio, c.fecha_fin, c.hora_inicio, c.hora_fin)
        ]
        for h in horarios_candidato:
            if h.key() not in seen_h:
                seen_h.add(h.key()); horarios.append(h)
        if c.fuente_url not in seen_f:
            seen_f.add(c.fuente_url); fuentes.append((c.fuente_url, c.fuente_listado))
        for u in c.imagenes:
            if u not in seen_i:
                seen_i.add(u); imagenes.append(u)
        if c.precio_euros is not None and float(c.precio_euros) > 0:
            precio = float(c.precio_euros)
            es_gratuito = 0

    return MergedEvent(
        id_unico=eid, poblacion=poblacion, cp=base.cp,
        titulo=base.titulo, lugar=primer_no_vacio("lugar"),
        descripcion_larga=base.descripcion_larga,
        direccion_fisica=primer_no_vacio("direccion_fisica"),
        organizador_nombre=primer_no_vacio("organizador_nombre"),
        es_gratuito=es_gratuito, precio_euros=precio,
        link_inscripcion=primer_no_vacio("link_inscripcion"),
        horarios=horarios, fuentes=fuentes, imagenes=imagenes,
    )


def _mismo_evento(rep: Candidate, c: Candidate, umbral: float) -> bool:
    """Criterio de fusión de dos candidatos de la misma población:
      1. Títulos similares (>= umbral), o
      2. Fechas solapadas + mismo lugar normalizado (no vacío). Cubre el caso
         de fuentes que titulan distinto el mismo evento ('Concert FM' vs
         'Gran concert de Festa Major') pero coinciden en cuándo y dónde."""
    if titulos_similares(rep.titulo, c.titulo, umbral):
        return True
    lugar_rep = normalize_place(rep.lugar)
    lugar_c = normalize_place(c.lugar)
    if lugar_rep and lugar_c and lugar_rep == lugar_c and fechas_solapan(rep, c):
        return True
    return False


def fusionar(candidates: list, umbral: float = SIMILARITY_THRESHOLD) -> list:
    """Agrupa candidatos que son el mismo evento. Criterio principal: misma
    población + títulos similares (>= umbral); secundario: fechas solapadas +
    mismo lugar (ver _mismo_evento). Las fechas por sí solas NO condicionan la
    fusión: si es el mismo evento en distintos horarios, se fusiona y se generan
    N entradas en EVENTO_HORARIOS. Horarios idénticos se deduplican vía seen_h.

    Clustering incremental determinista: ordenado por título normalizado antes de
    agrupar, sin necesidad de marcar prioridad de fuentes."""
    by_pob = {}
    for c in candidates:
        by_pob.setdefault(c.poblacion, []).append(c)

    merged = []
    for poblacion, cands in by_pob.items():
        cands_ordenados = sorted(
            cands, key=lambda c: (normalize_title(c.titulo), c.fecha_inicio or "", c.fuente_url or "")
        )
        clusters = []
        for c in cands_ordenados:
            colocado = False
            for cluster in clusters:
                rep = cluster[0]
                if _mismo_evento(rep, c, umbral):
                    cluster.append(c)
                    colocado = True
                    break
            if not colocado:
                clusters.append([c])

        for cluster in clusters:
            merged.append(_build_merged_from_cluster(cluster, poblacion))

    return merged


def filtrar_futuro(ev: MergedEvent) -> bool:
    """Conserva solo horarios de hoy o futuros. Devuelve False si no queda ninguno."""
    today = date.today()
    vivos = []
    for h in ev.horarios:
        try:
            fin = date.fromisoformat(h.fecha_fin) if h.fecha_fin else date.fromisoformat(h.fecha_inicio)
        except (ValueError, TypeError):
            vivos.append(h)  # fecha rara: conservar para no perder
            continue
        if fin >= today:
            vivos.append(h)
    ev.horarios = vivos
    return len(vivos) > 0


# ============================================================================
# PERSISTENCIA: geografía, recintos, fuentes, evento, imágenes
# ============================================================================

def geocode_poblacion(oai, pob) -> dict:
    """Pide al LLM coordenadas aproximadas del centro de la población."""
    schema = {"name": "coords", "strict": True, "schema": {
        "type": "object",
        "properties": {"lat": {"type": "number"}, "lng": {"type": "number"}},
        "required": ["lat", "lng"], "additionalProperties": False}}
    d = llm_json(oai, pob, "Devuelve coordenadas geográficas aproximadas.",
                 f"Centro del municipio de {pob} (Cataluña, España). Lat/Lng.", schema,
                 op="geocoding")
    return {"lat": round(d["lat"], 6), "lng": round(d["lng"], 6)}


def ensure_ciudad(conn, oai, pob, coords_cache) -> int:
    with conn.cursor() as cur:
        cur.execute("SELECT ID_Ciudad FROM CIUDADES WHERE Nombre=%s", (pob,))
        r = cur.fetchone()
        if r:
            return r["ID_Ciudad"]
    coords = coords_cache.get(pob) or geocode_poblacion(oai, pob)
    coords_cache[pob] = coords
    with conn.cursor() as cur:
        cur.execute("INSERT INTO CIUDADES (Nombre, Provincia, Latitud, Longitud) VALUES (%s,%s,%s,%s)",
                    (pob, "Girona", coords["lat"], coords["lng"]))
        return cur.lastrowid


def ensure_cp(conn, cp, id_ciudad, coords):
    with conn.cursor() as cur:
        cur.execute("SELECT CP FROM CODIGOS_POSTALES WHERE CP=%s", (cp,))
        if cur.fetchone():
            return
        cur.execute("INSERT INTO CODIGOS_POSTALES (CP, ID_Ciudad, Latitud, Longitud) VALUES (%s,%s,%s,%s)",
                    (cp, id_ciudad, coords["lat"], coords["lng"]))


def resolve_recinto(conn, ev: MergedEvent, id_ciudad, coords) -> Optional[int]:
    nombre = ev.recinto_canonico or ev.lugar
    if not nombre:
        return None
    with conn.cursor() as cur:
        cur.execute("SELECT ID_Recinto FROM RECINTOS WHERE ID_Ciudad=%s AND Nombre_Canonico=%s",
                    (id_ciudad, nombre))
        r = cur.fetchone()
        if r:
            return r["ID_Recinto"]
        tipo = ev.recinto_tipo if ev.recinto_tipo in RECINTO_TIPOS else "OTRO"
        try:
            cur.execute("""INSERT INTO RECINTOS
                (ID_Ciudad, CP, Nombre_Canonico, Tipo, Direccion_Fisica, Coordenadas_JSON, Fuente_Datos)
                VALUES (%s,%s,%s,%s,%s,%s,%s)""",
                (id_ciudad, ev.cp, nombre, tipo,
                 ev.direccion_fisica or None, json.dumps(coords), "ingest_all"))
            return cur.lastrowid
        except pymysql.err.IntegrityError:
            # colisión por UNIQUE de dirección: reusar el existente
            cur.execute("SELECT ID_Recinto FROM RECINTOS WHERE ID_Ciudad=%s AND Direccion_Fisica=%s",
                        (id_ciudad, ev.direccion_fisica))
            r = cur.fetchone()
            return r["ID_Recinto"] if r else None


def ensure_fuente(conn, id_ciudad, url_listado, fuente_cache) -> int:
    if url_listado in fuente_cache:
        return fuente_cache[url_listado]
    with conn.cursor() as cur:
        cur.execute("SELECT ID_Fuente FROM BIBLIOTECA_FUENTES WHERE URL_Base=%s", (url_listado,))
        r = cur.fetchone()
        if r:
            fuente_cache[url_listado] = r["ID_Fuente"]; return r["ID_Fuente"]
        cur.execute("""INSERT INTO BIBLIOTECA_FUENTES (ID_Ciudad, Tipo_Fuente, URL_Base, Activa)
                       VALUES (%s,'FUENTE_OFICIAL',%s,1)""", (id_ciudad, url_listado))
        fuente_cache[url_listado] = cur.lastrowid
        return cur.lastrowid


def determinar_orientacion(w, h):
    if h == 0: return "horizontal"
    ratio = w / h
    return "horizontal" if ratio > RATIO_HORIZONTAL_MIN else "vertical" if ratio < RATIO_VERTICAL_MAX else "cuadrada"


def _imagen_ya_disponible(target: IngestTarget, http: httpx.Client, eid: str,
                          fname: str, storage_url: str) -> bool:
    if target.store_images_locally:
        return (IMAGES_DIR / eid / fname).is_file()
    return _remote_image_exists(http, target, storage_url)


def descargar_imagenes(conn, http, ev: MergedEvent, pob, target: IngestTarget):
    for orden, url in enumerate(ev.imagenes):
        with conn.cursor() as cur:
            cur.execute("""
                SELECT Nombre_Archivo, URL_Almacenamiento_Nube
                FROM BINARIOS_STORAGE
                WHERE ID_Unico_Evento=%s AND URL_Original_Externa=%s
            """, (ev.id_unico, url))
            existing = cur.fetchone()
        if existing and _imagen_ya_disponible(
            target, http, ev.id_unico,
            existing["Nombre_Archivo"], existing["URL_Almacenamiento_Nube"],
        ):
            continue
        try:
            r = http.get(url, follow_redirects=True); r.raise_for_status()
            content = r.content
            if not (100 < len(content) <= MAX_IMAGE_SIZE_BYTES):
                raise ValueError(f"tamaño sospechoso ({len(content)} bytes)")
            img = Image.open(io.BytesIO(content)); img.verify()
            img = Image.open(io.BytesIO(content))
            w, h = img.size
            fmt = (img.format or "JPEG").upper()
            ext = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}.get(fmt, "jpg")
            tipo = {"JPEG": "JPG", "PNG": "PNG", "WEBP": "WEBP"}.get(fmt, "JPG")
            checksum = hashlib.sha256(content).hexdigest()
            fname = existing["Nombre_Archivo"] if existing else f"{orden:02d}_{checksum[:12]}.{ext}"
            if target.store_images_locally:
                event_dir = IMAGES_DIR / ev.id_unico
                event_dir.mkdir(parents=True, exist_ok=True)
                (event_dir / fname).write_bytes(content)
            else:
                _upload_image_remote(http, target, ev.id_unico, fname, content)
            if existing:
                continue
            local_url = f"/static/images/{ev.id_unico}/{fname}"
            with conn.cursor() as cur:
                cur.execute("""INSERT INTO BINARIOS_STORAGE
                    (ID_Unico_Evento, Nombre_Archivo, Tipo_Archivo, URL_Almacenamiento_Nube,
                     Es_Principal, Orden, Ancho_Px, Alto_Px, Orientacion, URL_Original_Externa, Checksum_SHA256)
                    VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                    (ev.id_unico, fname, tipo, local_url, 1 if orden == 0 else 0,
                     orden, w, h, determinar_orientacion(w, h), url, checksum))
            COST.add_imagen(pob)
        except Exception as e:
            log.error(f"    Imagen fallida {url}: {e}")


def sync_remote_binarios(conn, http: httpx.Client, target: IngestTarget, dry_run: bool) -> None:
    """Con --target railway: asegura que cada BINARIOS_STORAGE tenga su fichero en el servidor.

    Cubre eventos omitidos por ingesta incremental y binarios perdidos tras un redeploy."""
    if target.store_images_locally or dry_run:
        return
    with conn.cursor() as cur:
        cur.execute("""
            SELECT ID_Unico_Evento, Nombre_Archivo, URL_Almacenamiento_Nube, URL_Original_Externa
            FROM BINARIOS_STORAGE
            WHERE URL_Original_Externa IS NOT NULL AND URL_Original_Externa != ''
        """)
        rows = cur.fetchall()
    if not rows:
        return
    ok, subidas, fallidas = 0, 0, 0
    log.info(f"Sincronizando {len(rows)} imágenes con Railway ({target.api_base_url})...")
    for row in rows:
        eid = row["ID_Unico_Evento"]
        fname = row["Nombre_Archivo"]
        storage_url = row["URL_Almacenamiento_Nube"]
        if _remote_image_exists(http, target, storage_url):
            ok += 1
            continue
        ext_url = row["URL_Original_Externa"]
        try:
            r = http.get(ext_url, follow_redirects=True, timeout=HTTP_TIMEOUT)
            r.raise_for_status()
            if not (100 < len(r.content) <= MAX_IMAGE_SIZE_BYTES):
                raise ValueError(f"tamaño sospechoso ({len(r.content)} bytes)")
            _upload_image_remote(http, target, eid, fname, r.content)
            subidas += 1
        except Exception as exc:
            fallidas += 1
            log.error(f"    Sync fallida {eid[:12]}…/{fname}: {exc}")
    log.info(f"Sincronización imágenes Railway: {ok} ya OK, {subidas} subidas, {fallidas} fallidas")


def persist_event(conn, oai, http, ev: MergedEvent, cat_map, coords_cache,
                  fuente_cache, dry_run, target: IngestTarget):
    coords = coords_cache.get(ev.poblacion, {"lat": 41.6, "lng": 2.7})
    id_ciudad = ensure_ciudad(conn, oai, ev.poblacion, coords_cache)
    coords = coords_cache.get(ev.poblacion, coords)
    ensure_cp(conn, ev.cp, id_ciudad, coords)
    id_recinto = resolve_recinto(conn, ev, id_ciudad, coords)

    titulo_es = ev.titulo_es or ev.titulo
    img_principal = None  # se setea tras descargar

    # Familia: si el evento cuelga de un paraguas (festival/ciclo), su familia
    # es un hash determinista del nombre canónico -> todos los miembros
    # coinciden aunque sus títulos no se parezcan entre sí.
    id_fam = familia_id(ev.poblacion, ev.evento_paraguas) if ev.evento_paraguas else None

    # EVENTOS_MASTER upsert
    with conn.cursor() as cur:
        cur.execute("""
        INSERT INTO EVENTOS_MASTER (
            ID_Unico_Evento, Metodo_Ingesta, ID_Usuario_Carga, Fuente_ID, Fuente_URL_Original,
            Estado, ID_Ciudad, ID_Recinto, CP_Evento, Poblacion_Nombre, Lugar_Nombre,
            Direccion_Fisica, Coordenadas_JSON, ID_Familia, Organizador_Nombre, Es_Patrocinado, Idioma_Origen,
            Titulo_CAT, Titulo_ES, Desc_Larga_CAT, Desc_Larga_ES, Desc_Corta_CAT, Desc_Corta_ES,
            Tags_CAT, Tags_ES,
            Es_Gratuito, Precio_Euros, Requiere_Inscripcion, Link_Entradas_Inscripcion
        ) VALUES (%s,'SCRAPING','ingestion_cli','URL_ESTRUCTURAL',%s,'ACTIVO',%s,%s,%s,%s,%s,
                  %s,%s,%s,%s,0,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON DUPLICATE KEY UPDATE
            Fuente_URL_Original=VALUES(Fuente_URL_Original), ID_Ciudad=VALUES(ID_Ciudad),
            ID_Recinto=VALUES(ID_Recinto), CP_Evento=VALUES(CP_Evento),
            Poblacion_Nombre=VALUES(Poblacion_Nombre), Lugar_Nombre=VALUES(Lugar_Nombre),
            Direccion_Fisica=VALUES(Direccion_Fisica), Coordenadas_JSON=VALUES(Coordenadas_JSON),
            ID_Familia=COALESCE(VALUES(ID_Familia), ID_Familia),
            Organizador_Nombre=VALUES(Organizador_Nombre), Idioma_Origen=VALUES(Idioma_Origen),
            Titulo_CAT=VALUES(Titulo_CAT), Titulo_ES=VALUES(Titulo_ES),
            Desc_Larga_CAT=VALUES(Desc_Larga_CAT), Desc_Larga_ES=VALUES(Desc_Larga_ES),
            Desc_Corta_CAT=VALUES(Desc_Corta_CAT), Desc_Corta_ES=VALUES(Desc_Corta_ES),
            Tags_CAT=VALUES(Tags_CAT), Tags_ES=VALUES(Tags_ES), Es_Gratuito=VALUES(Es_Gratuito),
            Precio_Euros=VALUES(Precio_Euros), Requiere_Inscripcion=VALUES(Requiere_Inscripcion),
            Link_Entradas_Inscripcion=VALUES(Link_Entradas_Inscripcion)
        """, (
            ev.id_unico, ev.fuentes[0][0] if ev.fuentes else "", id_ciudad, id_recinto,
            ev.cp, ev.poblacion, ev.lugar or "Sin lugar",
            ev.direccion_fisica or None, json.dumps(coords), id_fam,
            ev.organizador_nombre or None, "ca",
            ev.titulo, titulo_es, ev.descripcion_larga or "", ev.desc_larga_es or "",
            ev.desc_corta or None, ev.desc_corta_es or None,
            json.dumps(ev.tags_ca, ensure_ascii=False), json.dumps(ev.tags_es, ensure_ascii=False),
            ev.es_gratuito, ev.precio_euros, 1 if ev.link_inscripcion else 0,
            ev.link_inscripcion or None,
        ))

    # HORARIOS (delete + insert)
    with conn.cursor() as cur:
        cur.execute("DELETE FROM EVENTO_HORARIOS WHERE ID_Unico_Evento=%s", (ev.id_unico,))
        for h in ev.horarios:
            cur.execute("""INSERT INTO EVENTO_HORARIOS
                (ID_Unico_Evento, Fecha_Inicio, Fecha_Fin, Hora_Inicio, Hora_Fin, Es_Recurrente)
                VALUES (%s,%s,%s,%s,%s,0)""",
                (ev.id_unico, h.fecha_inicio, h.fecha_fin or None,
                 h.hora_inicio or None, h.hora_fin or None))

    # CATEGORIAS (delete + insert)
    with conn.cursor() as cur:
        cur.execute("DELETE FROM EVENTO_CATEGORIAS WHERE ID_Unico_Evento=%s", (ev.id_unico,))
        codes = [ev.categoria_principal] + [c for c in ev.categorias if c != ev.categoria_principal]
        for code in codes:
            cid = cat_map.get(code)
            if cid:
                cur.execute("INSERT IGNORE INTO EVENTO_CATEGORIAS (ID_Unico_Evento, ID_Categoria) VALUES (%s,%s)",
                            (ev.id_unico, cid))

    # FUENTES (multi-fuente)
    with conn.cursor() as cur:
        for i, (url_origen, url_listado) in enumerate(ev.fuentes):
            id_fuente = ensure_fuente(conn, id_ciudad, url_listado, fuente_cache)
            cur.execute("""INSERT INTO EVENTO_FUENTES
                (ID_Unico_Evento, ID_Fuente, URL_Origen, Es_Fuente_Principal, Aporto_Extraccion)
                VALUES (%s,%s,%s,%s,1)
                ON DUPLICATE KEY UPDATE Fecha_Ultima_Confirmacion=NOW()""",
                (ev.id_unico, id_fuente, url_origen, 1 if i == 0 else 0))

    # IMÁGENES
    descargar_imagenes(conn, http, ev, ev.poblacion, target)
    with conn.cursor() as cur:
        cur.execute("""SELECT URL_Almacenamiento_Nube FROM BINARIOS_STORAGE
                       WHERE ID_Unico_Evento=%s AND Es_Principal=1 LIMIT 1""", (ev.id_unico,))
        r = cur.fetchone()
        if r:
            cur.execute("UPDATE EVENTOS_MASTER SET Imagen_Principal_URL=%s WHERE ID_Unico_Evento=%s",
                        (r["URL_Almacenamiento_Nube"], ev.id_unico))


# ============================================================================
# TARGETS DESDE BD: selección, detección de cambios y estado
# ============================================================================

def load_targets_from_db(conn, solo_poblacion: Optional[str] = None) -> list:
    """Targets activos desde SCRAPING_TARGETS + BIBLIOTECA_FUENTES + CIUDADES.
    Devuelve dicts con todo lo necesario para procesar y actualizar cada target,
    ordenados por población y prioridad de fuente."""
    sql = """
        SELECT t.ID_Target, t.ID_Fuente, t.Tipo_Target, t.Plataforma,
               t.URL_Target, t.Estado, t.Frecuencia_Horas,
               t.Http_ETag, t.Http_LastModified, t.Content_Fingerprint,
               t.Capturas_Vacias_Consecutivas, t.Capturas_Utiles_Consecutivas,
               f.Tipo_Fuente, f.Tipo_Contenido, f.Handle, f.Prioridad,
               c.ID_Ciudad, c.Nombre AS Poblacion,
               (SELECT cp.CP FROM CODIGOS_POSTALES cp
                WHERE cp.ID_Ciudad = c.ID_Ciudad LIMIT 1) AS CP
        FROM SCRAPING_TARGETS t
        JOIN BIBLIOTECA_FUENTES f ON f.ID_Fuente = t.ID_Fuente
        JOIN CIUDADES c ON c.ID_Ciudad = t.ID_Ciudad
        WHERE t.Estado != 'PAUSADO' AND f.Activa = 1
    """
    params = []
    if solo_poblacion:
        sql += " AND c.Nombre = %s"
        params.append(solo_poblacion)
    sql += " ORDER BY c.Nombre, f.Prioridad, t.ID_Target"
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.fetchall()


def content_fingerprint(html: str) -> str:
    """Fingerprint del TEXTO VISIBLE de la página, no del markup.

    El HTML suele llevar contenido dinámico que cambia en cada visita (tokens,
    URLs de caché de imágenes, contadores) y haría que el fingerprint sobre el
    markup detectara 'cambios' falsos en cada run, anulando el ahorro
    (observado en turismemaresme.cat, firescatalanes.cat y avui.info). El texto
    visible es estable: solo cambia si cambia el contenido real."""
    texto = BeautifulSoup(clean_html(html), "lxml").get_text(" ", strip=True)
    texto = re.sub(r"\s+", " ", texto)
    return hashlib.sha256(texto.encode("utf-8")).hexdigest()


def fetch_si_cambiado(http: httpx.Client, target_row: dict, refresh: bool):
    """Descarga la URL del target SOLO si ha cambiado desde la última ejecución.

    Cascade de coste:
      1. GET condicional con If-None-Match / If-Modified-Since -> 304 = skip
         sin descargar el cuerpo.
      2. Fingerprint sha256 del texto visible -> si coincide con el guardado,
         skip sin gastar ni una llamada LLM.
    Con --refresh se ignoran ambos y se procesa siempre.

    Devuelve (html | None, meta) donde meta = {etag, last_modified, fingerprint,
    cambio: bool}. html=None significa 'sin cambios' (no es un error)."""
    url = target_row["URL_Target"]
    headers = {}
    if not refresh:
        if target_row.get("Http_ETag"):
            headers["If-None-Match"] = target_row["Http_ETag"]
        if target_row.get("Http_LastModified"):
            headers["If-Modified-Since"] = target_row["Http_LastModified"]

    r = http.get(url, follow_redirects=True, headers=headers)
    if r.status_code == 304:
        log.info(f"    Sin cambios (HTTP 304): {url}")
        return None, {"etag": target_row.get("Http_ETag"),
                      "last_modified": target_row.get("Http_LastModified"),
                      "fingerprint": target_row.get("Content_Fingerprint"),
                      "cambio": False}
    r.raise_for_status()

    html = r.text
    fingerprint = content_fingerprint(html)
    meta = {"etag": r.headers.get("etag"),
            "last_modified": r.headers.get("last-modified"),
            "fingerprint": fingerprint, "cambio": True}

    if not refresh and fingerprint == target_row.get("Content_Fingerprint"):
        log.info(f"    Sin cambios (fingerprint idéntico): {url}")
        meta["cambio"] = False
        return None, meta

    return html, meta


def actualizar_target(conn, target_row: dict, ok: bool, meta: Optional[dict],
                      utiles: int, error: Optional[str], dry_run: bool):
    """Persiste el resultado de procesar un target: estado, ETag/fingerprint,
    contadores de capturas y programación del siguiente run. Auto-pausa los
    WEB_DETALLE agotados (página caducada) tras TARGET_MAX_VACIAS vacíos."""
    if dry_run:
        return
    meta = meta or {}
    cambio = bool(meta.get("cambio"))
    estado = "OK" if ok else "ERROR"
    vacias_prev = target_row.get("Capturas_Vacias_Consecutivas") or 0
    utiles_prev = target_row.get("Capturas_Utiles_Consecutivas") or 0
    if not ok or not cambio:
        # error o skip 'sin cambios': los contadores de captura no se tocan
        # (un skip por fingerprint NO es una captura vacía).
        vacias, utiles_acum = vacias_prev, utiles_prev
    elif utiles > 0:
        vacias, utiles_acum = 0, utiles_prev + 1
    else:
        vacias, utiles_acum = vacias_prev + 1, 0
    if (ok and cambio and utiles == 0 and target_row["Tipo_Target"] == "WEB_DETALLE"
            and vacias >= TARGET_MAX_VACIAS):
        estado = "PAUSADO"
        log.info(f"    Target WEB_DETALLE agotado ({vacias} capturas vacías), pausado: "
                 f"{target_row['URL_Target']}")
    with conn.cursor() as cur:
        cur.execute("""
            UPDATE SCRAPING_TARGETS SET
                Estado=%s,
                Last_Run_At=NOW(),
                Next_Run_At=DATE_ADD(NOW(), INTERVAL Frecuencia_Horas HOUR),
                Intentos=IF(%s, 0, Intentos + 1),
                Last_Error=%s,
                Http_ETag=%s,
                Http_LastModified=%s,
                Content_Fingerprint=%s,
                Last_Changed_At=IF(%s, NOW(), Last_Changed_At),
                Capturas_Utiles_Consecutivas=%s,
                Capturas_Vacias_Consecutivas=%s
            WHERE ID_Target=%s
        """, (estado, ok, (error or None),
              meta.get("etag") or target_row.get("Http_ETag"),
              meta.get("last_modified") or target_row.get("Http_LastModified"),
              meta.get("fingerprint") or target_row.get("Content_Fingerprint"),
              cambio, utiles_acum, vacias,
              target_row["ID_Target"]))
    conn.commit()


def registrar_confirmaciones(conn, confirmaciones: list, id_fuente: int, dry_run: bool):
    """Cuando la ingesta incremental omite un evento que ya existe, registra
    igualmente que esta fuente lo confirma (EVENTO_FUENTES, Aporto_Extraccion=0).
    Da trazabilidad multi-fuente sin reprocesar nada."""
    if dry_run or not confirmaciones:
        return
    with conn.cursor() as cur:
        for event_id, url_origen in confirmaciones:
            cur.execute("""INSERT INTO EVENTO_FUENTES
                (ID_Unico_Evento, ID_Fuente, URL_Origen, Es_Fuente_Principal, Aporto_Extraccion)
                VALUES (%s,%s,%s,0,0)
                ON DUPLICATE KEY UPDATE Fecha_Ultima_Confirmacion=NOW()""",
                (event_id, id_fuente, url_origen))
    conn.commit()


# ============================================================================
# CLASIFICADOR EVENTO/NOTICIA + PIPELINE DE NOTICIAS
# ============================================================================

def clasificar_items(oai, pob, html_clean, url, hint: str) -> list:
    """Clasifica los items de un listado MIXTO o de NOTICIAS en
    EVENTO/NOTICIA/DESCARTAR con una sola llamada LLM. El hint de la fuente
    sesga el prompt pero el LLM decide por contenido."""
    today = date.today().isoformat()
    system = (
        "Eres un clasificador de contenido de webs municipales catalanas. "
        f"Hoy es {today}. Esta fuente suele contener: {hint}. "
        "Para cada item del listado decide si es un EVENTO (actividad con fecha "
        "a la que se puede asistir), una NOTICIA (información/comunicado) o "
        "DESCARTAR (menús, banners, sin valor). Reglas: fechas absolutas "
        "YYYY-MM-DD; URLs absolutas y reales, null si no hay (NUNCA inventes); "
        "un item = una entrada, no dupliques."
    )
    user = f"URL listado: {url}\n\nHTML:\n{html_clean}"
    data = llm_json(oai, pob, system, user, CLASIFICACION_SCHEMA,
                    op="clasificacion", context=url)
    items = data.get("items", [])
    for it in items:
        if it.get("url_detalle"):
            it["url_detalle"] = urljoin(url, it["url_detalle"])
        if it.get("imagen_url"):
            it["imagen_url"] = urljoin(url, it["imagen_url"])
    return items


def buscar_noticia_existente(titulo: str, fecha_pub: Optional[str],
                             existentes: list, umbral: float):
    """Dedupe cross-fuente de noticias: misma población, título similar y
    fecha de publicación a menos de 7 días (si ambas se conocen)."""
    for n in existentes:
        if not titulos_similares(titulo, n["titulo"], umbral):
            continue
        if fecha_pub and n.get("fecha"):
            try:
                f1 = date.fromisoformat(str(fecha_pub))
                f2 = n["fecha"] if isinstance(n["fecha"], date) else date.fromisoformat(str(n["fecha"]))
                if abs((f1 - f2).days) > 7:
                    continue
            except (ValueError, TypeError):
                pass
        return n
    return None


def extraer_noticia(oai, pob, html_clean, url) -> dict:
    """Extrae el detalle de una noticia (cuerpo, fecha, imagen) de su página."""
    system = ("Extractor de noticias de webs municipales. Devuelve JSON con el "
              "texto completo de la noticia (sin menús ni navegación), su fecha "
              "de publicación, idioma e imagen principal. No inventes datos.")
    user = f"URL: {url}\n\nHTML:\n{html_clean}"
    data = llm_json(oai, pob, system, user, NOTICIA_DETAIL_SCHEMA,
                    op="noticia_detalle", context=url)
    if data.get("imagen_url"):
        data["imagen_url"] = urljoin(url, data["imagen_url"])
    return data


def enriquecer_noticia(oai, noticia: Noticia):
    """Traducción bilingüe CA/ES + tags. Una sola llamada por noticia nueva."""
    system = ("Enriqueces noticias municipales catalanas. Devuelve JSON con el "
              "título y cuerpo en catalán Y castellano (traduce el que falte, "
              "manteniendo nombres propios) y tags genéricos bilingües de "
              "búsqueda (temática, ámbito; nunca nombres propios).")
    user = (f"IDIOMA ORIGEN: {noticia.idioma}\n"
            f"TÍTULO: {noticia.titulo}\n"
            f"CUERPO:\n{noticia.cuerpo[:6000]}")
    d = llm_json(oai, noticia.poblacion, system, user, NOTICIA_ENRICH_SCHEMA,
                 op="noticia_enrich", context=noticia.titulo[:60])
    # El título/cuerpo "canónicos" (CAT) se sustituyen por la versión del LLM
    # para tener siempre ambos idiomas consistentes.
    noticia.titulo = d["titulo_ca"] or noticia.titulo
    noticia.cuerpo = d["cuerpo_ca"] or noticia.cuerpo
    noticia.titulo_es = d["titulo_es"] or noticia.titulo
    noticia.cuerpo_es = d["cuerpo_es"] or noticia.cuerpo
    noticia.resumen = (d.get("resumen_ca") or "").strip()[:500]
    noticia.resumen_es = (d.get("resumen_es") or "").strip()[:500]
    noticia.tags_ca = d["tags_ca"]
    noticia.tags_es = d["tags_es"]


def descargar_imagen_noticia(conn, http, nid: str, noticia: Noticia,
                             target: IngestTarget):
    """Descarga la imagen principal de la noticia (disco local o PUT Railway,
    mismo endpoint que eventos) y la registra en NOTICIA_BINARIOS."""
    url = noticia.imagen_url
    if not url:
        return None
    try:
        r = http.get(url, follow_redirects=True); r.raise_for_status()
        content = r.content
        if not (100 < len(content) <= MAX_IMAGE_SIZE_BYTES):
            raise ValueError(f"tamaño sospechoso ({len(content)} bytes)")
        img = Image.open(io.BytesIO(content)); img.verify()
        img = Image.open(io.BytesIO(content))
        w, h = img.size
        fmt = (img.format or "JPEG").upper()
        ext = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp"}.get(fmt, "jpg")
        tipo = {"JPEG": "JPG", "PNG": "PNG", "WEBP": "WEBP"}.get(fmt, "JPG")
        checksum = hashlib.sha256(content).hexdigest()
        fname = f"00_{checksum[:12]}.{ext}"
        if target.store_images_locally:
            ndir = IMAGES_DIR / nid
            ndir.mkdir(parents=True, exist_ok=True)
            (ndir / fname).write_bytes(content)
        else:
            _upload_image_remote(http, target, nid, fname, content)
        local_url = f"/static/images/{nid}/{fname}"
        with conn.cursor() as cur:
            cur.execute("""INSERT INTO NOTICIA_BINARIOS
                (ID_Unico_Noticia, Nombre_Archivo, Tipo_Archivo, URL_Almacenamiento_Nube,
                 Es_Principal, Orden, Ancho_Px, Alto_Px, Orientacion,
                 URL_Original_Externa, Checksum_SHA256)
                VALUES (%s,%s,%s,%s,1,0,%s,%s,%s,%s,%s)""",
                (nid, fname, tipo, local_url, w, h,
                 determinar_orientacion(w, h), url, checksum))
        COST.add_imagen(noticia.poblacion)
        return local_url
    except Exception as e:
        log.error(f"    Imagen de noticia fallida {url}: {e}")
        return None


def persist_noticia(conn, http, noticia: Noticia, id_ciudad: int,
                    target: IngestTarget) -> str:
    """INSERT idempotente de una noticia + su imagen. Devuelve el id."""
    nid = noticia_id(noticia.poblacion, noticia.titulo)
    fecha_pub = noticia.fecha_publicacion or date.today().isoformat()
    with conn.cursor() as cur:
        cur.execute("""
            INSERT INTO NOTICIAS_MASTER
                (ID_Unico_Noticia, ID_Ciudad, ID_Fuente, Fuente_URL_Original,
                 Titulo_CAT, Titulo_ES, Cuerpo_CAT, Cuerpo_ES,
                 Resumen_CAT, Resumen_ES, Tags_CAT, Tags_ES,
                 Fecha_Publicacion, Fecha_Caducidad, Estado, Idioma_Origen)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,
                    DATE_ADD(%s, INTERVAL %s DAY),'ACTIVA',%s)
            ON DUPLICATE KEY UPDATE
                Titulo_ES=VALUES(Titulo_ES), Cuerpo_CAT=VALUES(Cuerpo_CAT),
                Cuerpo_ES=VALUES(Cuerpo_ES),
                Resumen_CAT=VALUES(Resumen_CAT), Resumen_ES=VALUES(Resumen_ES),
                Tags_CAT=VALUES(Tags_CAT), Tags_ES=VALUES(Tags_ES)
        """, (nid, id_ciudad, noticia.id_fuente, noticia.fuente_url,
              noticia.titulo, noticia.titulo_es or noticia.titulo,
              noticia.cuerpo or "", noticia.cuerpo_es or "",
              noticia.resumen or None, noticia.resumen_es or None,
              json.dumps(noticia.tags_ca, ensure_ascii=False),
              json.dumps(noticia.tags_es, ensure_ascii=False),
              fecha_pub, fecha_pub, NEWS_VIGENCIA_DIAS, noticia.idioma))
    img_url = descargar_imagen_noticia(conn, http, nid, noticia, target)
    if img_url:
        with conn.cursor() as cur:
            cur.execute("UPDATE NOTICIAS_MASTER SET Imagen_Principal_URL=%s "
                        "WHERE ID_Unico_Noticia=%s", (img_url, nid))
    return nid


def noticia_caducada(fecha_pub: Optional[str]) -> bool:
    """True si la noticia queda FUERA de la ventana de vigencia: solo se
    ingieren noticias publicadas en los últimos NEWS_VIGENCIA_DIAS días (las
    antiguas no entran nunca, aunque la web las siga listando)."""
    if not fecha_pub:
        return False
    try:
        return date.fromisoformat(str(fecha_pub)[:10]) < (
            date.today() - timedelta(days=NEWS_VIGENCIA_DIAS))
    except (ValueError, TypeError):
        return False


def procesar_item_noticia(oai, http, pob, it, listado_url) -> Optional[Noticia]:
    """Convierte un item clasificado como NOTICIA en una Noticia, bajando su
    página de detalle si tiene URL (si no, queda con el título del listado)."""
    titulo = (it.get("titulo") or "").strip()
    if not titulo:
        return None
    fecha_pub = it.get("fecha")
    if noticia_caducada(fecha_pub):
        log.info(f"    Noticia más vieja que el TTL, descartada: {titulo[:60]}")
        return None
    noticia = Noticia(
        poblacion=pob, titulo=titulo,
        fecha_publicacion=fecha_pub or date.today().isoformat(),
        fuente_url=it.get("url_detalle") or listado_url,
        imagen_url=it.get("imagen_url") or "",
    )
    url_det = it.get("url_detalle")
    if url_det and same_or_sub_domain(url_det, listado_url):
        html_det = descargar_si_ok(url_det, http)
        if html_det is None:
            log.warning(f"    URL de noticia rota, se usa solo el listado: {url_det}")
            return noticia
        try:
            detail = extraer_noticia(oai, pob, html_a_texto_enlaces(html_det), url_det)
            if detail.get("titulo"):
                noticia.titulo = detail["titulo"].strip() or noticia.titulo
            noticia.cuerpo = (detail.get("cuerpo") or "").strip()
            if detail.get("fecha_publicacion"):
                noticia.fecha_publicacion = detail["fecha_publicacion"]
                if noticia_caducada(noticia.fecha_publicacion):
                    log.info(f"    Noticia más vieja que el TTL, descartada: {titulo[:60]}")
                    return None
            noticia.idioma = detail.get("idioma") or "ca"
            if detail.get("imagen_url"):
                noticia.imagen_url = detail["imagen_url"]
        except Exception as e:
            log.error(f"    Error en detalle de noticia {url_det}: {e}")
    return noticia


# ============================================================================
# CONECTOR TELEGRAM (canal público vía t.me/s/handle, sin API ni login)
# ============================================================================

def telegram_fetch_mensajes(http: httpx.Client, handle: str,
                            max_paginas: int = TELEGRAM_MAX_PAGINAS) -> list:
    """Descarga los mensajes recientes de un canal público de Telegram
    parseando el HTML de t.me/s/{handle}. Paginación hacia atrás con ?before=
    hasta max_paginas o hasta superar TELEGRAM_MAX_DIAS de antigüedad.

    Devuelve [{id, fecha (YYYY-MM-DD), texto, imagen_url, links}] del más
    reciente al más antiguo. Frágil por diseño (HTML no documentado): cualquier
    fallo de parseo devuelve lo acumulado hasta ese momento."""
    base = f"https://t.me/s/{handle}"
    limite = date.today() - timedelta(days=TELEGRAM_MAX_DIAS)
    mensajes, before = [], None

    for _ in range(max_paginas):
        url = f"{base}?before={before}" if before else base
        try:
            r = http.get(url, follow_redirects=True)
            r.raise_for_status()
        except httpx.HTTPError as e:
            log.warning(f"    Telegram: fallo descargando {url}: {e}")
            break

        soup = BeautifulSoup(r.text, "lxml")
        bloques = soup.select("div.tgme_widget_message")
        if not bloques:
            break

        ids_pagina = []
        for b in bloques:
            data_post = b.get("data-post", "")  # formato: handle/12345
            msg_id = data_post.split("/")[-1] if "/" in data_post else None
            if not msg_id or not msg_id.isdigit():
                continue
            ids_pagina.append(int(msg_id))

            t = b.select_one("time[datetime]")
            fecha = (t["datetime"][:10] if t and t.has_attr("datetime") else None)

            texto_el = b.select_one("div.tgme_widget_message_text")
            texto = texto_el.get_text("\n", strip=True) if texto_el else ""

            imagen_url = ""
            foto = b.select_one("a.tgme_widget_message_photo_wrap")
            if foto and foto.has_attr("style"):
                m = re.search(r"background-image:\s*url\('([^']+)'\)", foto["style"])
                if m:
                    imagen_url = m.group(1)

            links = [a["href"] for a in (texto_el.select("a[href]") if texto_el else [])
                     if a.get("href", "").startswith("http")]

            if texto or imagen_url:
                mensajes.append({"id": int(msg_id), "fecha": fecha,
                                 "texto": texto, "imagen_url": imagen_url,
                                 "links": links})

        if not ids_pagina:
            break
        # ¿La página ya es más antigua que la ventana? Paramos.
        fechas_validas = [m["fecha"] for m in mensajes if m["fecha"]]
        if fechas_validas:
            try:
                if date.fromisoformat(min(fechas_validas)) < limite:
                    break
            except ValueError:
                pass
        before = min(ids_pagina)

    # Filtrar fuera de ventana y ordenar del más reciente al más antiguo
    def en_ventana(m):
        if not m["fecha"]:
            return True
        try:
            return date.fromisoformat(m["fecha"]) >= limite
        except ValueError:
            return True

    mensajes = [m for m in mensajes if en_ventana(m)]
    mensajes.sort(key=lambda m: m["id"], reverse=True)
    return mensajes


def clasificar_mensajes_telegram(oai, pob, mensajes: list) -> list:
    """Clasifica un lote de mensajes de Telegram en EVENTO/NOTICIA/DESCARTAR
    con UNA llamada LLM. Devuelve la lista del schema (indice, tipo, ...)."""
    if not mensajes:
        return []
    today = date.today().isoformat()
    system = (
        "Clasificas mensajes del canal de Telegram de un ayuntamiento catalán. "
        f"Hoy (día de procesamiento) es {today}. Para cada mensaje numerado "
        "decide: EVENTO si anuncia una actividad con fecha a la que se puede "
        "asistir (extrae título, fecha YYYY-MM-DD, hora y lugar del propio "
        "texto); NOTICIA si es información municipal (avisos, obras, "
        "comunicados, resultados); DESCARTAR si no aporta (saludos, reenvíos "
        "vacíos, encuestas). "
        "CRÍTICO — fechas relativas ('aquest dissabte', 'demà', 'divendres', "
        "'este sábado'): resuélvelas respecto a la FECHA DE PUBLICACIÓN del "
        "mensaje (campo 'publicado'), NO respecto a hoy. Ejemplo: mensaje "
        "publicado el miércoles 15 con 'aquest dissabte' → sábado 18, aunque "
        "hoy sea posterior. No inventes fechas: null si el texto no la da."
    )
    partes = []
    for i, m in enumerate(mensajes):
        pub = m["fecha"] or "desconocida"
        partes.append(f"[{i}] publicado={pub}\n{m['texto'][:900]}")
    user = "\n\n---\n\n".join(partes)
    data = llm_json(oai, pob, system, user, TELEGRAM_BATCH_SCHEMA,
                    op="telegram", context=f"{len(mensajes)} mensajes")
    return data.get("mensajes", [])


def procesar_target_telegram(oai, http, target_row: dict, existing_events: list,
                             existing_noticias: list, umbral: float,
                             refresh: bool, confirmaciones: list, max_nuevos=None):
    """Procesa un canal de Telegram: fetch + clasificación batch + conversión a
    candidatos de evento y noticias. Devuelve (candidatos, noticias, meta, n_utiles).

    El fingerprint del target es el id del mensaje más reciente: si no hay
    mensaje nuevo desde el último run, skip total sin llamada LLM."""
    pob = target_row["Poblacion"]
    cp = target_row["CP"]
    handle = target_row["Handle"] or target_row["URL_Target"].rstrip("/").split("/")[-1]
    log.info(f"  Telegram: @{handle}")

    mensajes = telegram_fetch_mensajes(http, handle)
    if not mensajes:
        log.info("    Sin mensajes en la ventana temporal")
        return [], [], {"cambio": False}, 0

    fingerprint = hashlib.sha256(str(mensajes[0]["id"]).encode()).hexdigest()
    meta = {"etag": None, "last_modified": None,
            "fingerprint": fingerprint, "cambio": True}
    if not refresh and fingerprint == target_row.get("Content_Fingerprint"):
        log.info(f"    Sin mensajes nuevos desde el último run (último id {mensajes[0]['id']})")
        meta["cambio"] = False
        return [], [], meta, 0

    log.info(f"    {len(mensajes)} mensajes en ventana, clasificando en lote...")
    clasificados = clasificar_mensajes_telegram(oai, pob, mensajes)

    candidatos, noticias = [], []
    listado_url = f"https://t.me/s/{handle}"
    for c in clasificados:
        idx = c.get("indice")
        if not isinstance(idx, int) or not (0 <= idx < len(mensajes)):
            continue
        m = mensajes[idx]
        tipo = c.get("tipo")
        titulo = (c.get("titulo") or "").strip()
        if tipo == "DESCARTAR" or not titulo:
            continue
        url_msg = f"https://t.me/{handle}/{m['id']}"

        if tipo == "EVENTO":
            if not c.get("fecha"):
                continue  # evento sin fecha no es persistible
            existente = buscar_evento_existente(titulo, existing_events, umbral,
                                                c.get("lugar") or "", c["fecha"])
            if existente and not refresh:
                confirmaciones.append((existente["id"], url_msg))
                continue
            cand = Candidate(
                poblacion=pob, cp=cp, titulo=titulo,
                lugar=(c.get("lugar") or "").strip(),
                fuente_url=url_msg, fuente_listado=listado_url,
                fecha_inicio=c["fecha"],
                hora_inicio=c.get("hora_inicio"),
                descripcion_larga=m["texto"],
                imagenes=[m["imagen_url"]] if m["imagen_url"] else [],
            )
            candidatos.append(cand)
        elif tipo == "NOTICIA":
            fecha_pub = m["fecha"] or date.today().isoformat()
            if noticia_caducada(fecha_pub):
                continue
            if buscar_noticia_existente(titulo, fecha_pub, existing_noticias, umbral):
                continue
            noticias.append(Noticia(
                poblacion=pob, titulo=titulo, fecha_publicacion=fecha_pub,
                fuente_url=url_msg, cuerpo=m["texto"],
                imagen_url=m["imagen_url"],
                id_fuente=target_row["ID_Fuente"],
            ))

    if max_nuevos is not None and len(candidatos) + len(noticias) > max_nuevos:
        log.info(f"    Límite de prueba ({max_nuevos}): se recortan los items de Telegram")
        candidatos = candidatos[:max_nuevos]
        noticias = noticias[:max(0, max_nuevos - len(candidatos))]

    log.info(f"    Telegram: {len(candidatos)} eventos nuevos, {len(noticias)} noticias nuevas")
    return candidatos, noticias, meta, len(candidatos) + len(noticias)


# ============================================================================
# LOCK (evita ejecuciones simultáneas del cron)
# ============================================================================

def adquirir_lock() -> bool:
    """Lock-file con PID+timestamp. Si existe y es reciente, hay otra ejecución
    en marcha (False). Si es más viejo que LOCK_MAX_AGE_HORAS, se considera
    huérfano y se sobreescribe."""
    if LOCK_FILE.exists():
        try:
            edad_h = (time.time() - LOCK_FILE.stat().st_mtime) / 3600
            if edad_h < LOCK_MAX_AGE_HORAS:
                contenido = LOCK_FILE.read_text(encoding="utf-8", errors="ignore").strip()
                log.error(f"Otra ejecución en marcha ({contenido}, hace {edad_h:.1f}h). "
                          f"Si es un lock huérfano, borra {LOCK_FILE}")
                return False
            log.warning(f"Lock huérfano (hace {edad_h:.1f}h), se ignora")
        except OSError:
            pass
    LOCK_FILE.write_text(f"pid={os.getpid()} inicio={datetime.now().isoformat(timespec='seconds')}",
                         encoding="utf-8")
    return True


def liberar_lock():
    try:
        LOCK_FILE.unlink(missing_ok=True)
    except OSError:
        pass


# ============================================================================
# PIPELINE PRINCIPAL
# ============================================================================

def run_sync_images_only(target_name: str = "railway", api_base_url: Optional[str] = None,
                         dry_run: bool = False) -> None:
    """Re-descarga desde URL_Original_Externa y sube a Railway los binarios que falten."""
    if target_name != "railway":
        sys.exit("--sync-images-only requiere --target railway")
    ingest_target = resolve_ingest_target(target_name, api_base_url)
    http = make_http_client()
    conn = get_connection(ingest_target)
    try:
        log.info(f"Destino: railway -> {ingest_target.db_host}:{ingest_target.db_port}/{ingest_target.db_name}")
        log.info(f"API imágenes: {ingest_target.api_base_url}")
        verify_railway_upload_access(http, ingest_target)
        sync_remote_binarios(conn, http, ingest_target, dry_run)
    finally:
        http.close()
        conn.close()


def run(input_path: Path, dry_run: bool, umbral: float, refresh: bool = False,
        target_name: str = "local", api_base_url: Optional[str] = None):
    if not os.getenv("OPENAI_API_KEY"):
        sys.exit("Falta OPENAI_API_KEY en .env")
    if not input_path.exists():
        sys.exit(f"JSON de entrada no encontrado: {input_path}")

    ingest_target = resolve_ingest_target(target_name, api_base_url)
    fuentes_config = json.loads(input_path.read_text(encoding="utf-8"))
    oai = make_openai_client()
    http = make_http_client()
    conn = get_connection(ingest_target)

    coords_cache, fuente_cache = {}, {}

    try:
        cat_map = load_categorias_map(conn)
        if not cat_map:
            sys.exit("CATEGORIAS vacía. Ejecuta reset_catalogo_categorias.sql primero.")
        log.info(f"Categorías en BD: {len(cat_map)}")
        log.info(f"Umbral de fusión de títulos: {umbral}")
        log.info(f"Destino: {ingest_target.name} -> {ingest_target.db_host}:{ingest_target.db_port}/{ingest_target.db_name}")
        if ingest_target.store_images_locally:
            log.info(f"Imágenes: disco local ({IMAGES_DIR})")
        else:
            log.info(f"Imágenes: subida directa a Railway ({ingest_target.api_base_url})")
            verify_railway_upload_access(http, ingest_target)
            log.info("API de imágenes: acceso verificado")

        # 0. Limpieza inicial: eventos pasados completos + horarios sueltos pasados
        purge_past_events(conn, http, ingest_target, dry_run)
        purge_past_horarios(conn, dry_run)

        # Ingesta incremental: eventos ya en BD para omitir su reproceso.
        # Se carga DESPUÉS de la limpieza para no contar eventos ya borrados.
        if refresh:
            existing_by_pob = {}
            log.info("--refresh activo: se reprocesan TODOS los eventos (sin omitir)")
        else:
            existing_by_pob = load_existing_events(conn)
            total_existentes = sum(len(v) for v in existing_by_pob.values())
            log.info(f"Eventos ya en BD (se omitirán si reaparecen): {total_existentes}")

        # 1-6. Por población
        for pob_cfg in fuentes_config:
            pob = pob_cfg["poblacion"]
            cps = pob_cfg.get("codigos_postales", [])
            cp = cps[0] if cps else None
            links = pob_cfg.get("links", [])
            log.info("=" * 64)
            log.info(f"POBLACIÓN: {pob}  (CP {cp}, {len(links)} links)")

            # Extracción de todas las fuentes (omitiendo los ya existentes en BD)
            existing_titles = existing_by_pob.get(pob, [])
            candidates = []
            for link in links:
                candidates.extend(scrape_source(oai, http, pob, cp, link, dry_run,
                                                existing_titles, umbral, refresh))
            log.info(f"  Candidatos nuevos totales (todas las fuentes): {len(candidates)}")

            # Fusión
            merged = fusionar(candidates, umbral)
            log.info(f"  Tras fusión (umbral {umbral}): {len(merged)} eventos únicos")

            # Filtro temporal + enriquecimiento + persistencia
            persistidos = 0
            for ev in merged:
                if not filtrar_futuro(ev):
                    continue
                enrich(oai, pob, ev)
                if not dry_run:
                    try:
                        persist_event(conn, oai, http, ev, cat_map, coords_cache,
                                      fuente_cache, dry_run, ingest_target)
                        conn.commit()
                        persistidos += 1
                    except Exception as e:
                        conn.rollback()
                        log.error(f"  ERROR persistiendo '{ev.titulo[:50]}': {e}", exc_info=True)
                else:
                    persistidos += 1
            COST.add_evento(pob, persistidos)
            log.info(f"  Eventos persistidos en {pob}: {persistidos}")

        sync_remote_binarios(conn, http, ingest_target, dry_run)
        COST.report()
        if dry_run:
            log.info("(dry-run: no se ha tocado la BD ni descargado imágenes)")

    finally:
        http.close()
        conn.close()


def procesar_target_web(oai, http, target_row: dict, existing_events: list,
                        existing_noticias: list, umbral: float, refresh: bool,
                        dry_run: bool, confirmaciones: list, max_nuevos=None):
    """Procesa un target web (WEB_LISTADO, API_AGREGADOR o WEB_DETALLE) con
    detección de cambios. Devuelve (candidatos, noticias, meta, n_utiles)."""
    pob = target_row["Poblacion"]
    cp = target_row["CP"]
    url = target_row["URL_Target"]
    hint = target_row.get("Tipo_Contenido") or "MIXTO"

    html, meta = fetch_si_cambiado(http, target_row, refresh)
    if html is None:
        return [], [], meta, 0

    # --- Página de detalle directa (un solo evento; típica de agregadores) ---
    if target_row["Tipo_Target"] == "WEB_DETALLE":
        detail = extract_detail(oai, pob, html_a_texto_enlaces(html), url)
        titulo = (detail.get("titulo") or "").strip()
        fecha = (detail.get("fecha_inicio") or "").strip()
        if not titulo or not (fecha or detail.get("horarios_discretos")):
            log.info(f"    Detalle sin evento identificable (¿caducado?): {url}")
            return [], [], meta, 0
        existente = None if refresh else buscar_evento_existente(
            titulo, existing_events, umbral,
            detail.get("lugar_nombre") or "", fecha)
        if existente:
            confirmaciones.append((existente["id"], url))
            log.info(f"    Ya en BD, confirmada fuente: {titulo[:60]}")
            return [], [], meta, 1
        cand = Candidate(poblacion=pob, cp=cp, titulo=titulo, lugar="",
                         fuente_url=url, fuente_listado=url,
                         fecha_inicio=fecha)
        aplicar_detalle_a_candidato(oai, http, pob, cand, detail)
        return [cand], [], meta, 1

    # --- Listado de solo eventos: ruta clásica sin clasificador (coste 0 extra) ---
    if hint == "EVENTOS":
        cands = scrape_source(oai, http, pob, cp, url, dry_run,
                              existing_events, umbral, refresh,
                              confirmaciones, listing_html=html,
                              max_nuevos=max_nuevos)
        return cands, [], meta, len(cands) + len(confirmaciones)

    # --- Listado MIXTO o de NOTICIAS: clasificar cada item ---
    html_clean = html_a_texto_enlaces(html)
    log.info(f"    Clasificando listado {hint} ({len(html_clean):,} chars texto+enlaces)...")
    items = clasificar_items(oai, pob, html_clean, url, hint)
    n_ev = sum(1 for i in items if i.get("tipo") == "EVENTO")
    n_not = sum(1 for i in items if i.get("tipo") == "NOTICIA")
    log.info(f"    {len(items)} items: {n_ev} eventos, {n_not} noticias, "
             f"{len(items) - n_ev - n_not} descartados")

    candidatos, noticias = [], []
    detail_cache, ctx = {}, {"details_done": 0}
    for it in items:
        if max_nuevos is not None and len(candidatos) + len(noticias) >= max_nuevos:
            log.info(f"    Límite de prueba alcanzado ({max_nuevos} items nuevos): "
                     f"resto del listado omitido")
            break
        tipo = it.get("tipo")
        titulo = (it.get("titulo") or "").strip()
        if not titulo or tipo == "DESCARTAR":
            continue
        if tipo == "EVENTO":
            existente = None if refresh else buscar_evento_existente(
                titulo, existing_events, umbral,
                it.get("lugar_corto") or "", it.get("fecha") or "")
            if existente:
                confirmaciones.append((existente["id"], it.get("url_detalle") or url))
                continue
            item_ev = {"titulo": titulo, "fecha_inicio": it.get("fecha") or "",
                       "hora_inicio": it.get("hora_inicio"), "hora_fin": None,
                       "url_detalle": it.get("url_detalle"),
                       "lugar_corto": it.get("lugar_corto"),
                       "imagen_url": it.get("imagen_url")}
            candidatos.append(
                procesar_item_evento(oai, http, pob, cp, item_ev, url, detail_cache, ctx))
        elif tipo == "NOTICIA":
            if not refresh and buscar_noticia_existente(
                    titulo, it.get("fecha"), existing_noticias, umbral):
                continue
            noticia = procesar_item_noticia(oai, http, pob, it, url)
            if noticia:
                noticia.id_fuente = target_row["ID_Fuente"]
                noticias.append(noticia)

    return candidatos, noticias, meta, len(candidatos) + len(noticias)


def run_db(dry_run: bool, umbral: float, refresh: bool = False,
           target_name: str = "local", api_base_url: Optional[str] = None,
           solo_poblacion: Optional[str] = None, hard_reset: bool = False,
           con_dedupe: bool = True, max_items: Optional[int] = None):
    """Pipeline dirigido por BD: las fuentes/targets salen de BIBLIOTECA_FUENTES
    + SCRAPING_TARGETS (cargadas con scripts/import_fuentes.py). Es el modo
    pensado para el cron diario: detección de cambios por URL, ingesta
    incremental, clasificación evento/noticia y limpieza, todo en una pasada.

    --target both: la extracción y TODAS las llamadas LLM se hacen UNA sola vez
    y el resultado se persiste en ambas BDs (local y Railway). La BD local es
    la primaria: de ella salen los targets, el estado incremental y los
    fingerprints (las confirmaciones multi-fuente solo se registran en la
    primaria; los IDs internos de fuente pueden diferir entre BDs).

    --hard-reset: antes de empezar vacía los datos de ingesta en cada destino
    (eventos, noticias, binarios, recintos, estado de targets) conservando las
    tablas maestras. Combinado con la ingesta, equivale a 'empezar de cero'."""
    if not os.getenv("OPENAI_API_KEY"):
        sys.exit("Falta OPENAI_API_KEY en .env")

    inicio_run = datetime.now()
    nombres = ("local", "railway") if target_name == "both" else (target_name,)
    oai = make_openai_client()
    http = make_http_client()

    # destinos: [{target, conn, cat_map, fuente_cache}] — el primero es el primario
    destinos = []
    for nombre in nombres:
        tgt = resolve_ingest_target(nombre, api_base_url)
        destinos.append({"target": tgt, "conn": get_connection(tgt),
                         "fuente_cache": {}})

    coords_cache = {}
    resumen = {"OK": 0, "SKIP": 0, "ERROR": 0}
    primario = destinos[0]

    try:
        for d in destinos:
            tgt = d["target"]
            d["cat_map"] = load_categorias_map(d["conn"])
            if not d["cat_map"]:
                sys.exit(f"CATEGORIAS vacía en {tgt.name}. "
                         f"Ejecuta reset_catalogo_categorias.sql primero.")
            log.info(f"Destino: {tgt.name} -> {tgt.db_host}:{tgt.db_port}/{tgt.db_name} "
                     f"({len(d['cat_map'])} categorías)")
            if tgt.store_images_locally:
                log.info(f"  Imágenes: disco local ({IMAGES_DIR})")
            else:
                log.info(f"  Imágenes: subida directa a Railway ({tgt.api_base_url})")
                verify_railway_upload_access(http, tgt)
                log.info("  API de imágenes: acceso verificado")
        log.info(f"Umbral de fusión de títulos: {umbral}")
        if target_name == "both":
            log.info("--target both: extracción/LLM una sola vez; estado incremental "
                     "y fingerprints en la BD primaria (local); persistencia en ambas")

        # Hard reset opcional (por destino), antes de cualquier otra cosa
        if hard_reset:
            for d in destinos:
                hard_reset_datos(d["conn"], http, d["target"], dry_run)

        # 0. Limpieza inicial (por destino)
        for d in destinos:
            purge_past_events(d["conn"], http, d["target"], dry_run)
            purge_past_horarios(d["conn"], dry_run)
            purge_noticias_caducadas(d["conn"], http, d["target"], dry_run)

        # Estado para la ingesta incremental (tras la limpieza)
        if refresh:
            existing_by_pob, noticias_by_pob = {}, {}
            log.info("--refresh activo: se reprocesa TODO (sin omitir existentes)")
        else:
            existing_by_pob = load_existing_events(primario["conn"])
            noticias_by_pob = load_existing_noticias(primario["conn"])
            log.info(f"Ya en BD: {sum(len(v) for v in existing_by_pob.values())} eventos, "
                     f"{sum(len(v) for v in noticias_by_pob.values())} noticias "
                     f"(se omitirán si reaparecen)")

        # Targets desde la BD primaria
        targets = load_targets_from_db(primario["conn"], solo_poblacion)
        if not targets:
            sys.exit("No hay targets activos en SCRAPING_TARGETS. "
                     "Carga las semillas con: python scripts/import_fuentes.py "
                     "--input scripts/fuentes/Malgrat.json")
        log.info(f"Targets activos: {len(targets)}"
                 + (f" (solo {solo_poblacion})" if solo_poblacion else ""))

        # Agrupar por población conservando el orden por prioridad
        por_poblacion = {}
        for t in targets:
            por_poblacion.setdefault(t["Poblacion"], []).append(t)

        for pob, rows in por_poblacion.items():
            log.info("=" * 64)
            log.info(f"POBLACIÓN: {pob}  ({len(rows)} targets)")
            existing_events = existing_by_pob.get(pob, [])
            existing_noticias = noticias_by_pob.get(pob, [])
            candidates, noticias_nuevas = [], []

            for t in rows:
                # Límite de prueba (--max-items): al alcanzarlo se saltan los
                # targets restantes SIN actualizar su estado/fingerprint, para
                # que el siguiente run completo los procese con normalidad.
                if max_items is not None:
                    procesados = len(candidates) + len(noticias_nuevas)
                    if procesados >= max_items:
                        log.info(f"  Límite de prueba alcanzado ({max_items} items): "
                                 f"targets restantes de {pob} omitidos sin tocar su estado")
                        break
                    presupuesto = max_items - procesados
                else:
                    presupuesto = None

                confirmaciones = []
                try:
                    if t["Tipo_Target"] in ("SOCIAL_PERFIL", "SOCIAL_QUERY"):
                        if t.get("Plataforma") == "TELEGRAM":
                            cands, nots, meta, utiles = procesar_target_telegram(
                                oai, http, t, existing_events, existing_noticias,
                                umbral, refresh, confirmaciones, presupuesto)
                        else:
                            # IG/FB/X/YouTube: conector Apify pendiente (fase 2).
                            # No deberían tener target activo; defensa por si acaso.
                            log.info(f"  Plataforma {t.get('Plataforma')} sin conector "
                                     f"(fase 2), target ignorado: {t['URL_Target']}")
                            continue
                    else:
                        cands, nots, meta, utiles = procesar_target_web(
                            oai, http, t, existing_events, existing_noticias,
                            umbral, refresh, dry_run, confirmaciones, presupuesto)

                    candidates.extend(cands)
                    noticias_nuevas.extend(nots)
                    # Confirmaciones y estado del target: solo en la primaria.
                    # Con --max-items NO se actualiza el estado/fingerprint del
                    # target (run de prueba): el siguiente run completo debe
                    # reprocesarlo entero.
                    registrar_confirmaciones(primario["conn"], confirmaciones,
                                             t["ID_Fuente"], dry_run)
                    if max_items is None:
                        actualizar_target(primario["conn"], t, True, meta, utiles,
                                          None, dry_run)
                    resumen["OK" if meta.get("cambio") else "SKIP"] += 1
                except Exception as e:
                    log.error(f"  ERROR en target {t['URL_Target']}: {e}")
                    actualizar_target(primario["conn"], t, False, None, 0,
                                      str(e)[:500], dry_run)
                    resumen["ERROR"] += 1

            log.info(f"  Candidatos nuevos: {len(candidates)} eventos, "
                     f"{len(noticias_nuevas)} noticias")

            # --- Eventos: fusión + filtro + enriquecimiento + persistencia ---
            merged = fusionar(candidates, umbral)
            if candidates:
                log.info(f"  Tras fusión (umbral {umbral}): {len(merged)} eventos únicos")
            persistidos = 0
            for ev in merged:
                if not filtrar_futuro(ev):
                    continue
                enrich(oai, pob, ev)
                if dry_run:
                    persistidos += 1
                    continue
                ok_alguno = False
                for d in destinos:
                    try:
                        persist_event(d["conn"], oai, http, ev, d["cat_map"],
                                      coords_cache, d["fuente_cache"], dry_run,
                                      d["target"])
                        d["conn"].commit()
                        ok_alguno = True
                    except Exception as e:
                        d["conn"].rollback()
                        log.error(f"  ERROR persistiendo '{ev.titulo[:50]}' en "
                                  f"{d['target'].name}: {e}", exc_info=True)
                if ok_alguno:
                    persistidos += 1
            COST.add_evento(pob, persistidos)

            # --- Noticias: dedupe intra-run + enriquecimiento + persistencia ---
            noticias_persistidas = 0
            vistas_run = []
            for noticia in noticias_nuevas:
                if buscar_noticia_existente(noticia.titulo, noticia.fecha_publicacion,
                                            vistas_run, umbral):
                    continue
                vistas_run.append({"id": "", "titulo": noticia.titulo,
                                   "fecha": noticia.fecha_publicacion})
                if dry_run:
                    noticias_persistidas += 1
                    continue
                try:
                    enriquecer_noticia(oai, noticia)
                except Exception as e:
                    log.error(f"  ERROR enriqueciendo noticia "
                              f"'{noticia.titulo[:50]}': {e}")
                    continue
                ok_alguno = False
                for d in destinos:
                    try:
                        # ID de ciudad propio de cada BD (pueden diferir)
                        id_ciudad_d = ensure_ciudad(d["conn"], oai, pob, coords_cache)
                        persist_noticia(d["conn"], http, noticia, id_ciudad_d,
                                        d["target"])
                        d["conn"].commit()
                        ok_alguno = True
                    except Exception as e:
                        d["conn"].rollback()
                        log.error(f"  ERROR persistiendo noticia "
                                  f"'{noticia.titulo[:50]}' en {d['target'].name}: {e}",
                                  exc_info=True)
                if ok_alguno:
                    noticias_persistidas += 1
            COST.add_noticia(pob, noticias_persistidas)
            log.info(f"  Persistidos en {pob}: {persistidos} eventos, "
                     f"{noticias_persistidas} noticias")

            # --- Deduplicación/familias de la población recién parseada ---
            # Análisis (embeddings + juez) una sola vez sobre la BD primaria;
            # las fusiones/familias se aplican a todos los destinos. Un fallo
            # aquí no tumba el run (la ingesta ya está persistida).
            if con_dedupe and not dry_run:
                try:
                    from dedupe_events import dedupe_poblacion
                    dedupe_poblacion(oai, http, destinos, pob,
                                     dry_run=False, cost=COST, modelo=LLM_MODEL)
                except Exception as e:
                    log.error(f"  Dedupe falló en {pob} (la ingesta no se ve "
                              f"afectada): {e}", exc_info=True)

        # Limpieza final + sincronización (por destino)
        for d in destinos:
            purge_binarios_huerfanos(d["conn"], d["target"], dry_run)
            sync_remote_binarios(d["conn"], http, d["target"], dry_run)

        log.info("=" * 64)
        log.info(f"RESUMEN DE TARGETS: {resumen['OK']} con cambios · "
                 f"{resumen['SKIP']} sin cambios (skip) · {resumen['ERROR']} con error")
        COST.report()

        # Persistir el gasto del run en cada destino (lo consume la API/front).
        if not dry_run:
            partes = [f"target={target_name}"]
            if solo_poblacion:
                partes.append(f"poblacion={solo_poblacion}")
            if refresh:
                partes.append("refresh")
            if hard_reset:
                partes.append("hard-reset")
            if max_items is not None:
                partes.append(f"max-items={max_items}")
            parametros = " ".join(partes)
            for d in destinos:
                try:
                    COST.persistir_run(d["conn"], inicio_run, d["target"].name,
                                       parametros, resumen)
                except Exception as e:
                    log.warning(f"No se pudo guardar el gasto del run en "
                                f"{d['target'].name} (¿falta SQL/costes_delta.sql?): {e}")

        if dry_run:
            log.info("(dry-run: no se ha tocado la BD ni descargado imágenes)")

    finally:
        http.close()
        for d in destinos:
            try:
                d["conn"].close()
            except Exception:
                pass


def main():
    ap = argparse.ArgumentParser(
        description=("Pipeline completo de ingesta de eventos y noticias (un proceso). "
                     "Sin --input lee las fuentes de la BD (BIBLIOTECA_FUENTES + "
                     "SCRAPING_TARGETS, modo cron); con --input usa el JSON plano legacy."))
    ap.add_argument("--input", help=("JSON legacy de poblaciones/links. Si se omite, "
                                     "las fuentes salen de la BD (recomendado; "
                                     "cargar antes con scripts/import_fuentes.py)"))
    ap.add_argument("--sync-images-only", action="store_true",
                    help="Solo re-descarga y sube a Railway las imágenes que falten en el servidor")
    ap.add_argument("--dry-run", action="store_true", help="No toca BD ni descarga imágenes")
    ap.add_argument("--umbral", type=float, default=SIMILARITY_THRESHOLD,
                    help=(f"Umbral de similitud (0..1) para fusionar eventos de la misma "
                          f"población con títulos parecidos. Default {SIMILARITY_THRESHOLD}. "
                          f"Más alto = más estricto (menos fusiones)."))
    ap.add_argument("--refresh", action="store_true",
                    help=("Reprocesa TODO: ignora la omisión incremental de eventos/noticias "
                          "ya en BD y la detección de cambios por URL (ETag/fingerprint). "
                          "Por defecto la ingesta es incremental para ahorrar coste."))
    ap.add_argument("--poblacion", "--solo-poblacion", dest="solo_poblacion",
                    default=None, metavar="NOMBRE",
                    help="Procesa solo los targets de esa población (solo modo BD)")
    ap.add_argument("--sin-dedupe", action="store_true",
                    help=("Desactiva la deduplicación/familias automática que se "
                          "ejecuta tras parsear cada población (solo modo BD)."))
    ap.add_argument("--modelo", default=None, metavar="MODELO",
                    help=("Modelo LLM del run (default: env LLM_MODEL o gpt-4.1-mini). "
                          "Útil para comparar calidad/coste: gpt-4.1-mini vs gpt-4.1-nano."))
    ap.add_argument("--max-items", type=int, default=None, metavar="N",
                    help=("Límite de PRUEBA: procesa como mucho N eventos+noticias "
                          "nuevos por población y para. Los targets afectados NO "
                          "guardan fingerprint (el siguiente run completo los "
                          "reprocesa). Solo modo BD."))
    ap.add_argument("--target", choices=("local", "railway", "both"), default="local",
                    help=("Destino de la ingesta: 'local' usa DB_* (Docker); "
                          "'railway' usa RAILWAY_DB_* y sube imágenes al servidor API; "
                          "'both' extrae UNA vez y persiste en ambas BDs "
                          "(la local actúa como primaria; solo modo BD)."))
    ap.add_argument("--hard-reset", action="store_true",
                    help=("ATENCIÓN: vacía los datos de ingesta del destino (eventos, "
                          "noticias, binarios, recintos y estado de targets) antes de "
                          "ingerir desde cero. Conserva CATEGORIAS, CIUDADES, "
                          "CODIGOS_POSTALES y BIBLIOTECA_FUENTES/SCRAPING_TARGETS."))
    ap.add_argument("--api-base-url", default=None,
                    help=("URL base de la API en producción (solo con --target railway). "
                          "Por defecto EVENTS_API_BASE_URL o https://eventquery.km0lab.com"))
    args = ap.parse_args()
    if args.modelo:
        set_llm_model(args.modelo)
    if args.sync_images_only:
        if args.target == "both":
            ap.error("--sync-images-only requiere --target railway")
        run_sync_images_only(args.target, args.api_base_url, args.dry_run)
        return
    if args.input and args.target == "both":
        ap.error("--target both solo está soportado en modo BD (sin --input)")
    if args.input and args.hard_reset:
        ap.error("--hard-reset solo está soportado en modo BD (sin --input)")
    if args.input and args.max_items is not None:
        ap.error("--max-items solo está soportado en modo BD (sin --input)")

    if not adquirir_lock():
        sys.exit(1)
    try:
        if args.input:
            run(Path(args.input), args.dry_run, args.umbral, args.refresh,
                args.target, args.api_base_url)
        else:
            run_db(args.dry_run, args.umbral, args.refresh,
                   args.target, args.api_base_url, args.solo_poblacion,
                   args.hard_reset, con_dedupe=not args.sin_dedupe,
                   max_items=args.max_items)
    finally:
        liberar_lock()


if __name__ == "__main__":
    main()
