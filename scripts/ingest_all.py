"""
ingest_all.py — Pipeline completo de ingesta de eventos municipales (un solo proceso).

Toma un JSON de poblaciones (cada una con sus códigos postales y N links de
agenda) y, en UNA sola ejecución, deja la base de datos poblada con eventos
listos para consumir por la API: traducidos, etiquetados, categorizados, con
recintos canónicos, imágenes descargadas y horarios agrupados.

QUÉ HACE, EN ORDEN
------------------
  0. Limpieza inicial: borra de la BD los eventos cuya última fecha ya pasó
     (y sus imágenes en disco) y, de los eventos vigentes, los horarios sueltos
     que ya caducaron. La agenda solo contiene hoy y futuro.
  1. Por cada población y cada link: descarga el listado, lo limpia y extrae
     los eventos con un LLM (extractor universal, sin selectores por web).
     INGESTA INCREMENTAL: los eventos del listado que YA existen en la BD
     (mismo título o similar en esa población) se omiten por completo, sin
     gastar llamadas de detalle/cartel/enriquecimiento. Con --refresh se
     reprocesan todos.
  2. Para cada evento NUEVO con página de detalle válida (descarta links rotos):
     descarga el detalle y extrae descripción larga, horas, lugar, imágenes.
  3. FUSIÓN: agrupa por población + similitud de título (>= umbral).
       - Mismo evento en varias fechas  -> 1 evento + N horarios.
       - Mismo evento en varias fuentes  -> 1 evento + N fuentes registradas.
       - Une imágenes de todas las fuentes.
  4. Filtro temporal: descarta horarios pasados; si un evento se queda sin
     horarios futuros, se descarta entero.
  5. ENRIQUECIMIENTO (1 llamada LLM por evento ya fusionado): traducción ES,
     tags genéricos bilingües, categorías del catálogo cerrado, y deducción
     del recinto canónico + su tipo.
  6. PERSISTENCIA transaccional: CIUDADES, CODIGOS_POSTALES, RECINTOS,
     BIBLIOTECA_FUENTES, EVENTOS_MASTER, EVENTO_HORARIOS, EVENTO_CATEGORIAS,
     EVENTO_FUENTES, BINARIOS_STORAGE. Idempotente por ID_Unico_Evento.
  7. Informe de costes desglosado por población.

NO hace: embeddings (se generan aparte cuando se active la búsqueda semántica).

USO
---
    python ingest_all.py --input fuentes.json
    python ingest_all.py --input fuentes.json --dry-run   # no toca BD ni descarga imágenes

FORMATO DEL JSON DE ENTRADA
---------------------------
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
    OPENAI_API_KEY
    DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME
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
import unicodedata
from dataclasses import dataclass, field
from datetime import date, datetime
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

LLM_MODEL = "gpt-4.1-mini"

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")

IMAGES_DIR = Path("static") / "images"

# Orientación de imágenes (ratio = ancho / alto)
RATIO_HORIZONTAL_MIN = 1.20
RATIO_VERTICAL_MAX = 0.80

HTTP_TIMEOUT = 30
HTTP_USER_AGENT = "KM0EventsIngestion/0.2"
MAX_IMAGE_SIZE_BYTES = 20 * 1024 * 1024
MAX_DETAIL_PAGES_PER_SOURCE = 60  # tope de seguridad de coste por link

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
    # gpt-4.1-mini
    "gpt-4.1-mini": {"input": 0.40, "cached_input": 0.10, "output": 1.60},
}


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
        self.global_stats = self._new_bucket()

    def _new_bucket(self):
        return {
            "llm_calls": 0,
            "tokens_in": 0,        # tokens de entrada NO cacheados
            "tokens_cached": 0,    # tokens de entrada cacheados (tarifa reducida)
            "tokens_out": 0,       # tokens de salida
            "imagenes": 0, "eventos": 0,
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
                  self.global_stats):
            b["llm_calls"] += 1
            b["tokens_in"] += no_cacheados
            b["tokens_cached"] += cached
            b["tokens_out"] += out

    def add_imagen(self, pob, n=1):
        self._bucket(self.by_pob, pob)["imagenes"] += n
        self.global_stats["imagenes"] += n

    def add_evento(self, pob, n=1):
        self._bucket(self.by_pob, pob)["eventos"] += n
        self.global_stats["eventos"] += n

    @staticmethod
    def _coste(b, prices):
        return (b["tokens_in"] / 1_000_000 * prices["input"] +
                b["tokens_cached"] / 1_000_000 * prices["cached_input"] +
                b["tokens_out"] / 1_000_000 * prices["output"])

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
        log.info("-" * W)
        log.info(f">>> GASTO TOTAL OPENAI: ${self._coste(g, prices):.4f} USD")
        log.info("=" * W)


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


# ============================================================================
# CONEXIÓN BD
# ============================================================================

def get_connection():
    if not all([DB_HOST, DB_USER, DB_PASSWORD, DB_NAME]):
        sys.exit("Faltan variables DB_HOST/DB_USER/DB_PASSWORD/DB_NAME en .env")
    return pymysql.connect(
        host=DB_HOST, port=DB_PORT, user=DB_USER, password=DB_PASSWORD,
        database=DB_NAME, charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor, autocommit=False,
    )


def load_categorias_map(conn) -> dict:
    with conn.cursor() as cur:
        cur.execute("SELECT ID_Categoria, Slug FROM CATEGORIAS WHERE Activo=1")
        return {r["Slug"]: r["ID_Categoria"] for r in cur.fetchall()}


# ============================================================================
# LIMPIEZA INICIAL: borrar eventos pasados + sus imágenes en disco
# ============================================================================

def purge_past_events(conn, dry_run: bool) -> int:
    """Borra eventos cuya última fecha (Fecha_Fin o Fecha_Inicio) < hoy.
    Borra también los archivos de imagen en disco. CASCADE limpia tablas hijas."""
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
        # Borrar carpeta de imágenes en disco
        event_dir = IMAGES_DIR / eid
        if event_dir.exists():
            shutil.rmtree(event_dir, ignore_errors=True)
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
    """Mapa poblacion -> [títulos (Titulo_CAT)] ya presentes en EVENTOS_MASTER.

    Se usa para la ingesta incremental: si un evento del listado ya existe en la
    BD (mismo título o suficientemente similar en la misma población), se omite
    por completo y no se gasta ni una llamada de detalle/cartel/enriquecimiento."""
    out = {}
    with conn.cursor() as cur:
        cur.execute("SELECT Poblacion_Nombre, Titulo_CAT FROM EVENTOS_MASTER")
        for r in cur.fetchall():
            pob = r["Poblacion_Nombre"] or ""
            out.setdefault(pob, []).append(r["Titulo_CAT"] or "")
    return out


# ============================================================================
# HTTP + LIMPIEZA HTML
# ============================================================================

def make_http_client():
    return httpx.Client(timeout=HTTP_TIMEOUT, headers={"User-Agent": HTTP_USER_AGENT})


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
        "required": ["descripcion_larga", "fecha_fin", "hora_inicio", "hora_fin",
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
            "titulo_es": {"type": "string", "description": "Traducción al castellano. Mantén nombres propios."},
            "desc_larga_es": {"type": "string", "description": "Traducción al castellano de la descripción. '' si vacía."},
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
        },
        "required": ["titulo_es", "desc_larga_es", "tags_ca", "tags_es",
                     "categorias_codigos", "categoria_principal",
                     "recinto_canonico", "recinto_tipo"],
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


# ============================================================================
# LLM: LLAMADAS
# ============================================================================

def llm_json(oai, pob, system, user, schema, op="otros"):
    resp = oai.chat.completions.create(
        model=LLM_MODEL,
        messages=[{"role": "system", "content": system},
                  {"role": "user", "content": user}],
        response_format={"type": "json_schema", "json_schema": schema},
        temperature=0,
    )
    COST.add_llm(pob, resp, op)
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
    data = llm_json(oai, pob, system, user, LISTING_SCHEMA, op="listado")
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
    data = llm_json(oai, pob, system, user, DETAIL_SCHEMA, op="detalle")
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
        data = json.loads(resp.choices[0].message.content)
        if not data.get("tiene_texto_util"):
            log.info(f"    Cartel-OCR: imagen sin texto útil, descartada")
            return None
        return data
    except Exception as e:
        log.warning(f"    Cartel-OCR falló: {e}")
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
    "Enriqueces eventos municipales catalanes. Devuelve JSON: traducción al "
    "castellano, tags genéricos bilingües, categorías del catálogo cerrado, y el "
    "recinto canónico limpio con su tipo. Traduce con naturalidad manteniendo "
    "nombres propios. Tags = conceptos de búsqueda, nunca nombres propios ni el "
    "lugar. Un evento DEPORTIVO va en 'deportes' y no lleva tag 'ocio'."
)


def enrich(oai, pob, ev: MergedEvent):
    user = (f"TÍTULO (ca): {ev.titulo}\n"
            f"DESCRIPCIÓN (ca):\n{ev.descripcion_larga}\n"
            f"LUGAR (crudo): {ev.lugar}\n"
            f"ORGANIZADOR: {ev.organizador_nombre}")
    d = llm_json(oai, pob, ENRICH_SYSTEM, user, ENRICHMENT_SCHEMA, op="enriquecimiento")
    ev.titulo_es = d["titulo_es"]
    ev.desc_larga_es = d["desc_larga_es"]
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


# ============================================================================
# EXTRACCIÓN DE UNA FUENTE (un link) -> lista de Candidate
# ============================================================================

def scrape_source(oai, http, pob, cp, listado_url, dry_run,
                  existing_titles=None, umbral=SIMILARITY_THRESHOLD,
                  refresh=False) -> list:
    existing_titles = existing_titles or []
    log.info(f"  Link: {listado_url}")
    try:
        listing_html = download_html(listado_url, http)
    except httpx.HTTPError as e:
        log.error(f"    No se pudo descargar el listado: {e}")
        return []

    items = extract_listing(oai, pob, clean_html(listing_html), listado_url)
    log.info(f"    {len(items)} eventos en el listado")

    candidates = []
    detail_cache = {}
    details_done = 0
    omitidos = 0  # ya existentes en BD: no se reprocesan (ahorro de coste)

    for it in items:
        titulo = (it.get("titulo") or "").strip()
        fecha_inicio = (it.get("fecha_inicio") or "").strip()
        if not titulo or not fecha_inicio:
            continue

        # Ingesta incremental: si el evento ya está en la BD (mismo título o
        # suficientemente similar en esta población), se omite por completo: no
        # se baja el detalle, no se lee el cartel, no se enriquece ni se
        # descargan imágenes. Es el grueso del ahorro de coste por ejecución.
        if not refresh and any(
            titulos_similares(titulo, t, umbral) for t in existing_titles
        ):
            omitidos += 1
            continue

        cand = Candidate(
            poblacion=pob, cp=cp, titulo=titulo,
            lugar=(it.get("lugar_corto") or "").strip(),
            fuente_url=it.get("url_detalle") or listado_url,
            fuente_listado=listado_url,
            fecha_inicio=fecha_inicio,
            hora_inicio=it.get("hora_inicio"),
            hora_fin=it.get("hora_fin"),
            imagenes=[it["imagen_url"]] if it.get("imagen_url") else [],
        )

        url_det = it.get("url_detalle")
        if url_det and same_or_sub_domain(url_det, listado_url):
            if url_det in detail_cache:
                detail = detail_cache[url_det]
            elif details_done >= MAX_DETAIL_PAGES_PER_SOURCE:
                log.warning(f"    Tope de detalles ({MAX_DETAIL_PAGES_PER_SOURCE}) alcanzado")
                detail = None
            elif not url_ok(url_det, http):
                log.warning(f"    URL de detalle rota, descartada: {url_det}")
                detail = None
            else:
                try:
                    detail = extract_detail(oai, pob, clean_html(download_html(url_det, http)), url_det)
                    detail_cache[url_det] = detail
                    details_done += 1
                except Exception as e:
                    log.error(f"    Error en detalle {url_det}: {e}")
                    detail = None

            if detail:
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
                if detail.get("es_gratuito") is not None:
                    cand.es_gratuito = 1 if detail["es_gratuito"] else 0
                cand.precio_euros = detail.get("precio_euros")
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

        candidates.append(cand)

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
        if c.precio_euros is not None:
            precio = c.precio_euros
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


def fusionar(candidates: list, umbral: float = SIMILARITY_THRESHOLD) -> list:
    """Agrupa candidatos que son el mismo evento. Criterio único: misma población
    + títulos similares (>= umbral). Las fechas NO condicionan la fusión: si son
    el mismo evento en distintos horarios, se fusionan y se generan N entradas en
    EVENTO_HORARIOS. Si son el mismo evento con horarios idénticos (duplicado real),
    _build_merged_from_cluster los deduplica vía seen_h.

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
                if titulos_similares(rep.titulo, c.titulo, umbral):
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


def descargar_imagenes(conn, http, ev: MergedEvent, pob):
    for orden, url in enumerate(ev.imagenes):
        with conn.cursor() as cur:
            cur.execute("SELECT 1 FROM BINARIOS_STORAGE WHERE ID_Unico_Evento=%s AND URL_Original_Externa=%s",
                        (ev.id_unico, url))
            if cur.fetchone():
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
            event_dir = IMAGES_DIR / ev.id_unico
            event_dir.mkdir(parents=True, exist_ok=True)
            fname = f"{orden:02d}_{checksum[:12]}.{ext}"
            (event_dir / fname).write_bytes(content)
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


def persist_event(conn, oai, http, ev: MergedEvent, cat_map, coords_cache,
                  fuente_cache, dry_run):
    coords = coords_cache.get(ev.poblacion, {"lat": 41.6, "lng": 2.7})
    id_ciudad = ensure_ciudad(conn, oai, ev.poblacion, coords_cache)
    coords = coords_cache.get(ev.poblacion, coords)
    ensure_cp(conn, ev.cp, id_ciudad, coords)
    id_recinto = resolve_recinto(conn, ev, id_ciudad, coords)

    titulo_es = ev.titulo_es or ev.titulo
    img_principal = None  # se setea tras descargar

    # EVENTOS_MASTER upsert
    with conn.cursor() as cur:
        cur.execute("""
        INSERT INTO EVENTOS_MASTER (
            ID_Unico_Evento, Metodo_Ingesta, ID_Usuario_Carga, Fuente_ID, Fuente_URL_Original,
            Estado, ID_Ciudad, ID_Recinto, CP_Evento, Poblacion_Nombre, Lugar_Nombre,
            Direccion_Fisica, Coordenadas_JSON, Organizador_Nombre, Es_Patrocinado, Idioma_Origen,
            Titulo_CAT, Titulo_ES, Desc_Larga_CAT, Desc_Larga_ES, Tags_CAT, Tags_ES,
            Es_Gratuito, Precio_Euros, Requiere_Inscripcion, Link_Entradas_Inscripcion
        ) VALUES (%s,'SCRAPING','ingestion_cli','URL_ESTRUCTURAL',%s,'ACTIVO',%s,%s,%s,%s,%s,
                  %s,%s,%s,0,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
        ON DUPLICATE KEY UPDATE
            Fuente_URL_Original=VALUES(Fuente_URL_Original), ID_Ciudad=VALUES(ID_Ciudad),
            ID_Recinto=VALUES(ID_Recinto), CP_Evento=VALUES(CP_Evento),
            Poblacion_Nombre=VALUES(Poblacion_Nombre), Lugar_Nombre=VALUES(Lugar_Nombre),
            Direccion_Fisica=VALUES(Direccion_Fisica), Coordenadas_JSON=VALUES(Coordenadas_JSON),
            Organizador_Nombre=VALUES(Organizador_Nombre), Idioma_Origen=VALUES(Idioma_Origen),
            Titulo_CAT=VALUES(Titulo_CAT), Titulo_ES=VALUES(Titulo_ES),
            Desc_Larga_CAT=VALUES(Desc_Larga_CAT), Desc_Larga_ES=VALUES(Desc_Larga_ES),
            Tags_CAT=VALUES(Tags_CAT), Tags_ES=VALUES(Tags_ES), Es_Gratuito=VALUES(Es_Gratuito),
            Precio_Euros=VALUES(Precio_Euros), Requiere_Inscripcion=VALUES(Requiere_Inscripcion),
            Link_Entradas_Inscripcion=VALUES(Link_Entradas_Inscripcion)
        """, (
            ev.id_unico, ev.fuentes[0][0] if ev.fuentes else "", id_ciudad, id_recinto,
            ev.cp, ev.poblacion, ev.lugar or "Sin lugar",
            ev.direccion_fisica or None, json.dumps(coords),
            ev.organizador_nombre or None, "ca",
            ev.titulo, titulo_es, ev.descripcion_larga or "", ev.desc_larga_es or "",
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
    descargar_imagenes(conn, http, ev, ev.poblacion)
    with conn.cursor() as cur:
        cur.execute("""SELECT URL_Almacenamiento_Nube FROM BINARIOS_STORAGE
                       WHERE ID_Unico_Evento=%s AND Es_Principal=1 LIMIT 1""", (ev.id_unico,))
        r = cur.fetchone()
        if r:
            cur.execute("UPDATE EVENTOS_MASTER SET Imagen_Principal_URL=%s WHERE ID_Unico_Evento=%s",
                        (r["URL_Almacenamiento_Nube"], ev.id_unico))


# ============================================================================
# PIPELINE PRINCIPAL
# ============================================================================

def run(input_path: Path, dry_run: bool, umbral: float, refresh: bool = False):
    if not os.getenv("OPENAI_API_KEY"):
        sys.exit("Falta OPENAI_API_KEY en .env")
    if not input_path.exists():
        sys.exit(f"JSON de entrada no encontrado: {input_path}")

    fuentes_config = json.loads(input_path.read_text(encoding="utf-8"))
    oai = OpenAI()
    http = make_http_client()
    conn = get_connection()

    coords_cache, fuente_cache = {}, {}

    try:
        cat_map = load_categorias_map(conn)
        if not cat_map:
            sys.exit("CATEGORIAS vacía. Ejecuta reset_catalogo_categorias.sql primero.")
        log.info(f"Categorías en BD: {len(cat_map)}")
        log.info(f"Umbral de fusión de títulos: {umbral}")

        # 0. Limpieza inicial: eventos pasados completos + horarios sueltos pasados
        purge_past_events(conn, dry_run)
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
                        persist_event(conn, oai, http, ev, cat_map, coords_cache, fuente_cache, dry_run)
                        conn.commit()
                        persistidos += 1
                    except Exception as e:
                        conn.rollback()
                        log.error(f"  ERROR persistiendo '{ev.titulo[:50]}': {e}", exc_info=True)
                else:
                    persistidos += 1
            COST.add_evento(pob, persistidos)
            log.info(f"  Eventos persistidos en {pob}: {persistidos}")

        COST.report()
        if dry_run:
            log.info("(dry-run: no se ha tocado la BD ni descargado imágenes)")

    finally:
        http.close()
        conn.close()


def main():
    ap = argparse.ArgumentParser(description="Pipeline completo de ingesta de eventos (un proceso).")
    ap.add_argument("--input", required=True, help="JSON de poblaciones/links")
    ap.add_argument("--dry-run", action="store_true", help="No toca BD ni descarga imágenes")
    ap.add_argument("--umbral", type=float, default=SIMILARITY_THRESHOLD,
                    help=(f"Umbral de similitud (0..1) para fusionar eventos de la misma "
                          f"población con títulos parecidos. Default {SIMILARITY_THRESHOLD}. "
                          f"Más alto = más estricto (menos fusiones)."))
    ap.add_argument("--refresh", action="store_true",
                    help=("Reprocesa TODOS los eventos, incluidos los que ya existen en "
                          "la BD. Por defecto (sin este flag) la ingesta es incremental: "
                          "los eventos ya registrados se omiten para ahorrar coste."))
    args = ap.parse_args()
    run(Path(args.input), args.dry_run, args.umbral, args.refresh)


if __name__ == "__main__":
    main()
