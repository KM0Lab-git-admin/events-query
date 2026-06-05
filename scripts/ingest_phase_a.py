"""
ingest_phase_a.py — Extracción universal de eventos desde webs municipales.

Fase A del módulo de ingesta KM0_Events. Para cada fuente configurada:
  1. Descarga el HTML del listado de la agenda.
  2. Lo limpia (quita menús, scripts, etc.) para reducir tokens al LLM.
  3. Llama a un LLM para extraer los eventos del listado.
  4. Para cada evento, descarga su página de detalle y la procesa también con el LLM.
  5. Combina listado + detalle y vuelca todo a un CSV.

NO hace traducción, ni tags, ni categorías, ni embeddings, ni persistencia en BD.
Eso es Fase B (enriquecimiento) y Fase C (persistencia).

El mismo código sirve para cualquier web municipal añadiendo una entrada en SOURCES.
No hay selectores CSS hardcoded por web: el LLM hace de extractor universal.

USO
---
    export OPENAI_API_KEY=sk-...
    python ingest_phase_a.py --fuente malgrat
    python ingest_phase_a.py --fuente blanes
    python ingest_phase_a.py --fuente malgrat --output ./out/malgrat.csv

DEPENDENCIAS
------------
    pip install httpx beautifulsoup4 lxml openai
"""

import argparse
import csv
import hashlib
import json
import logging
import os
import re
import sys
from dataclasses import dataclass, asdict
from datetime import date
from pathlib import Path
from typing import Optional
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup, Comment
from openai import OpenAI

# Cargar variables del fichero .env del proyecto, si python-dotenv está
# instalado. Permite tener OPENAI_API_KEY en .env en vez de exportarla cada vez.
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass  # sin dotenv, usaremos solo variables de entorno del sistema


# ============================================================================
# CONFIGURACIÓN
# ============================================================================

# Modelo LLM. Probado con gpt-4.1-mini. Si no lo tienes habilitado en tu cuenta,
# alternativas válidas: "gpt-4o-mini", "gpt-4.1", "gpt-4o".
LLM_MODEL = "gpt-4.1-mini"

# Fuentes configuradas. Para añadir un municipio, copia un bloque y cambia los
# valores. NO hace falta tocar más código.
SOURCES = {
    "malgrat": {
        "id_ciudad": 1,                         # FK a CIUDADES.ID_Ciudad
        "nombre_ciudad": "Malgrat de Mar",
        "cp_default": "08380",
        "idioma_origen": "ca",
        "url_listado": "https://www.ajmalgrat.cat/comunicacio/agenda",
        "dominio_esperado": "ajmalgrat.cat",
    },
    "blanes": {
        "id_ciudad": 2,
        "nombre_ciudad": "Blanes",
        "cp_default": "17300",
        "idioma_origen": "ca",
        "url_listado": "https://www.blanes.cat/agenda",
        "dominio_esperado": "blanes.cat",
    },
}

# HTTP
HTTP_TIMEOUT_SECONDS = 30
HTTP_USER_AGENT = "KM0EventsIngestion/0.1"

# Tope de seguridad: máximo de páginas de detalle a procesar por ejecución.
# Si el listado tiene cientos de eventos (Blanes repite eventos largos varios días),
# evitamos un coste desbocado en la primera ejecución.
MAX_DETAIL_PAGES = 50


# ============================================================================
# LOGGING
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("ingest")


# ============================================================================
# MODELOS DE DATOS
# ============================================================================

@dataclass
class ListingItem:
    """Un evento extraído del listado, antes de visitar su página de detalle."""
    titulo: str
    fecha_inicio: str               # YYYY-MM-DD
    hora_inicio: Optional[str]      # HH:MM
    hora_fin: Optional[str]
    url_detalle: Optional[str]
    lugar_corto: Optional[str]
    imagen_url: Optional[str]


@dataclass
class DetailData:
    """Datos adicionales extraídos de la página de detalle de un evento."""
    descripcion_larga: Optional[str]
    fecha_fin: Optional[str]
    hora_inicio: Optional[str]
    hora_fin: Optional[str]
    lugar_nombre: Optional[str]
    direccion_fisica: Optional[str]
    organizador_nombre: Optional[str]
    es_gratuito: Optional[bool]
    precio_euros: Optional[float]
    link_inscripcion: Optional[str]
    imagenes_urls: list  # cambiado de imagen_url: Optional[str]


@dataclass
class Event:
    """Evento final, listo para volcar a CSV. Mapea conceptualmente a
    EVENTOS_MASTER + EVENTO_HORARIOS (solo los campos que esta fase llena;
    el resto se rellenan en Fase B/C).
    """
    # Identidad y trazabilidad
    id_unico_evento: str
    metodo_ingesta: str
    id_usuario_carga: str
    fuente_id: str
    fuente_url_original: str
    estado: str

    # Geografía
    id_ciudad: int
    nombre_ciudad: str
    cp_evento: str
    lugar_nombre: str
    direccion_fisica: str

    # Contenido (idioma origen, sin traducción todavía)
    idioma_origen: str
    titulo: str
    descripcion_larga: str

    # Temporal
    fecha_inicio: str
    fecha_fin: str
    hora_inicio: str
    hora_fin: str

    # Económico
    es_gratuito: int
    precio_euros: str
    requiere_inscripcion: int
    link_inscripcion: str

    # Organización
    organizador_nombre: str

    # Multimedia
    imagenes_urls: str  # JSON array de URLs serializado, primera = principal


# ============================================================================
# DESCARGA Y LIMPIEZA DE HTML
# ============================================================================

def download_html(url: str, client: httpx.Client) -> str:
    """Descarga el HTML de una URL. httpx detecta el encoding del Content-Type
    automáticamente, así que webs con ISO-8859-1 (Blanes) se manejan bien sin
    código extra.
    """
    log.info(f"  GET {url}")
    response = client.get(url, follow_redirects=True)
    response.raise_for_status()
    return response.text


def clean_html(html: str) -> str:
    """Reduce el HTML a su contenido relevante para extracción.

    Quita scripts, estilos, navegación, footer y comentarios. Si encuentra una
    etiqueta semántica <main> o <article>, se queda solo con eso. Suele reducir
    el tamaño del HTML un 70-90%, lo que abarata mucho la llamada al LLM.
    """
    soup = BeautifulSoup(html, "lxml")

    # Eliminar elementos que no aportan información del evento
    for tag in soup(["script", "style", "head", "nav", "footer",
                     "aside", "noscript", "iframe", "form", "header"]):
        tag.decompose()

    # Eliminar comentarios HTML
    for comment in soup.find_all(string=lambda s: isinstance(s, Comment)):
        comment.extract()

    # Quedarnos con el contenido principal si la web es semántica
    main = soup.find("main") or soup.find("article") or soup.body
    if main is None:
        main = soup

    # Compactar whitespace
    text = str(main)
    text = re.sub(r"\n\s*\n", "\n", text)
    text = re.sub(r"[ \t]+", " ", text)
    return text


# ============================================================================
# LLM: SCHEMAS DE EXTRACCIÓN
# ============================================================================

LISTING_SCHEMA = {
    "name": "events_from_listing",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "eventos": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "titulo": {
                            "type": "string",
                            "description": "Título limpio del evento, sin fechas, horas ni datos extra mezclados",
                        },
                        "fecha_inicio": {
                            "type": "string",
                            "description": "Fecha de inicio en formato YYYY-MM-DD. Si la fecha en la web es relativa ('avui', 'demà', 'aquest divendres'), conviértela a fecha absoluta usando la fecha de hoy proporcionada. Si la fecha está expresada en catalán o castellano ('5 maig'), conviértela a ISO.",
                        },
                        "hora_inicio": {
                            "type": ["string", "null"],
                            "description": "Hora de inicio en formato HH:MM (24h). null si no aparece.",
                        },
                        "hora_fin": {
                            "type": ["string", "null"],
                            "description": "Hora de fin en formato HH:MM. null si no aparece. Extrae de rangos del tipo 'de 20:30h a 22:00h'.",
                        },
                        "url_detalle": {
                            "type": ["string", "null"],
                            "description": "URL absoluta a la página de detalle del evento. Si está relativa en el HTML, hazla absoluta usando la URL base del listado.",
                        },
                        "lugar_corto": {
                            "type": ["string", "null"],
                            "description": "Nombre del lugar tal y como aparece en el listado, sin direcciones largas.",
                        },
                        "imagen_url": {
                            "type": ["string", "null"],
                            "description": "URL absoluta de la imagen si aparece.",
                        },
                    },
                    "required": ["titulo", "fecha_inicio", "hora_inicio", "hora_fin",
                                 "url_detalle", "lugar_corto", "imagen_url"],
                    "additionalProperties": False,
                },
            }
        },
        "required": ["eventos"],
        "additionalProperties": False,
    },
}


DETAIL_SCHEMA = {
    "name": "event_detail",
    "strict": True,
    "schema": {
        "type": "object",
        "properties": {
            "descripcion_larga": {
                "type": ["string", "null"],
                "description": "Descripción completa del evento en el idioma original. Solo el texto descriptivo: NO incluyas elementos de navegación, breadcrumbs, 'comparte en redes', 'última actualización', etc.",
            },
            "fecha_fin": {
                "type": ["string", "null"],
                "description": "Si el evento dura varios días, fecha final en YYYY-MM-DD. null si es de un solo día.",
            },
            "hora_inicio": {
                "type": ["string", "null"],
                "description": "HH:MM si la página de detalle precisa o aporta una hora de inicio.",
            },
            "hora_fin": {
                "type": ["string", "null"],
                "description": "HH:MM si aparece. Extrae de rangos del tipo 'de 20:30 a 22:00'.",
            },
            "lugar_nombre": {
                "type": ["string", "null"],
                "description": "Nombre del lugar/equipamiento (ej: 'Centre Cultural', 'Biblioteca La Cooperativa').",
            },
            "direccion_fisica": {
                "type": ["string", "null"],
                "description": "Dirección postal completa del lugar si aparece (calle, número, CP, ciudad).",
            },
            "organizador_nombre": {
                "type": ["string", "null"],
                "description": "Quién organiza el evento (ej: grupo, asociación, regidoría) si está mencionado explícitamente.",
            },
            "es_gratuito": {
                "type": ["boolean", "null"],
                "description": "true si dice explícitamente que es gratis o entrada libre, false si menciona un precio, null si no se sabe.",
            },
            "precio_euros": {
                "type": ["number", "null"],
                "description": "Precio en euros si aparece. null si es gratuito o no se sabe.",
            },
            "link_inscripcion": {
                "type": ["string", "null"],
                "description": "URL absoluta de inscripción/compra de entradas si aparece.",
            },
            "imagenes_urls": {
                "type": "array",
                "description": (
                    "Lista de URLs absolutas de TODAS las imágenes que ilustran "
                    "el evento, en orden de aparición en la página. La primera "
                    "debe ser la principal/destacada (la imagen que va más "
                    "arriba o más grande). Si solo hay una imagen, devuelve un "
                    "array con esa única URL. Si no hay ninguna imagen del "
                    "evento, devuelve array vacío []. NO incluyas iconos, "
                    "logos del ayuntamiento, banners de cookies, ni imágenes "
                    "de navegación."
                ),
                "items": {"type": "string"},
            },
        },
        "required": ["descripcion_larga", "fecha_fin", "hora_inicio", "hora_fin",
                     "lugar_nombre", "direccion_fisica", "organizador_nombre",
                     "es_gratuito", "precio_euros", "link_inscripcion", "imagenes_urls"],
        "additionalProperties": False,
    },
}


# ============================================================================
# LLM: LLAMADAS
# ============================================================================

# Acumulador global de uso para reportar al final
_usage = {"prompt_tokens": 0, "completion_tokens": 0, "calls": 0}


def _log_usage(response):
    """Registra tokens consumidos por una llamada al LLM."""
    if hasattr(response, "usage") and response.usage:
        _usage["prompt_tokens"] += response.usage.prompt_tokens
        _usage["completion_tokens"] += response.usage.completion_tokens
        _usage["calls"] += 1


def extract_listing(html_clean: str, source: dict, oai: OpenAI) -> list[ListingItem]:
    """Pide al LLM la lista de eventos del listado."""
    today_iso = date.today().isoformat()
    system = (
        "Eres un extractor de eventos de agendas municipales catalanas/españolas. "
        "Recibes el HTML ya limpiado de una página de listado de agenda y devuelves "
        "la lista de eventos en JSON estructurado. "
        f"La fecha de hoy es {today_iso}. "
        "REGLAS IMPORTANTES: "
        "(1) Conviértelo todo a fechas absolutas YYYY-MM-DD. "
        "(2) Si el listado agrupa eventos por día y un mismo evento aparece varios "
        "días seguidos (por ser un evento de varios días o una exposición), "
        "devuélvelo UNA SOLA VEZ con fecha_inicio = primer día visible. "
        "(3) Las URLs deben ser absolutas. Resuelve URLs relativas usando la URL base del listado. "
        "(4) NO inventes datos: si un campo no aparece, devuélvelo como null. "
        "(5) Solo incluye eventos futuros o en curso. Descarta eventos cuya fecha "
        "haya pasado completamente."
    )
    user = (
        f"URL base del listado: {source['url_listado']}\n"
        f"Idioma del contenido: {source['idioma_origen']}\n\n"
        f"HTML LIMPIO DEL LISTADO:\n{html_clean}"
    )

    log.info(f"  LLM listado: {len(html_clean):,} chars de HTML")
    response = oai.chat.completions.create(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        response_format={"type": "json_schema", "json_schema": LISTING_SCHEMA},
        temperature=0,
    )
    _log_usage(response)

    payload = json.loads(response.choices[0].message.content)
    items = [ListingItem(**raw) for raw in payload["eventos"]]

    # Por si el LLM devuelve URLs relativas, las absolutizamos
    for it in items:
        if it.url_detalle:
            it.url_detalle = urljoin(source["url_listado"], it.url_detalle)
        if it.imagen_url:
            it.imagen_url = urljoin(source["url_listado"], it.imagen_url)

    log.info(f"  LLM listado: extraídos {len(items)} eventos")
    return items


def extract_detail(html_clean: str, url: str, source: dict, oai: OpenAI) -> DetailData:
    """Pide al LLM los datos adicionales de una página de detalle."""
    system = (
        "Eres un extractor de detalles de eventos municipales. Recibes el HTML ya "
        "limpiado de la página de detalle de UN evento. Extrae los campos pedidos "
        "en JSON. "
        f"Idioma esperado: {source['idioma_origen']}. "
        "REGLAS: "
        "(1) Para descripción, solo el texto descriptivo del evento. NO incluyas "
        "menús, breadcrumbs, 'comparte en redes', 'última actualización', etc. "
        "(2) NO inventes datos: si un campo no aparece, devuélvelo como null. "
        "(3) URLs absolutas siempre."
    )
    user = f"URL de la página: {url}\n\nHTML LIMPIO:\n{html_clean}"

    log.info(f"  LLM detalle: {len(html_clean):,} chars")
    response = oai.chat.completions.create(
        model=LLM_MODEL,
        messages=[
            {"role": "system", "content": system},
            {"role": "user", "content": user},
        ],
        response_format={"type": "json_schema", "json_schema": DETAIL_SCHEMA},
        temperature=0,
    )
    _log_usage(response)

    payload = json.loads(response.choices[0].message.content)
    detail = DetailData(**payload)

    if detail.link_inscripcion:
        detail.link_inscripcion = urljoin(url, detail.link_inscripcion)
    # Absolutizar todas las URLs de imágenes
    detail.imagenes_urls = [urljoin(url, u) for u in (detail.imagenes_urls or []) if u]

    return detail


# ============================================================================
# MERGE Y VALIDACIÓN
# ============================================================================

def merge(item: ListingItem, detail: Optional[DetailData], source: dict) -> Event:
    """Combina datos del listado y del detalle en un Event.

    Política:
      - El listado define la identidad del evento (título, fecha de inicio).
      - El detalle aporta cuerpo (descripción, dirección, organizador).
      - Si el detalle precisa una hora que el listado no tenía, gana el detalle.
      - Si el detalle tiene una imagen mejor que la miniatura del listado, gana.
    """
    # ID estable: hash del URL canónico (si lo tenemos) o de los identificadores
    # de identidad del evento.
    if item.url_detalle:
        id_basis = item.url_detalle
    else:
        id_basis = f"{source['id_ciudad']}|{item.titulo}|{item.fecha_inicio}"
    id_unico = hashlib.sha256(id_basis.encode("utf-8")).hexdigest()

    # Defaults desde el listado
    fecha_fin = ""
    descripcion = ""
    lugar = item.lugar_corto or ""
    direccion = ""
    organizador = ""
    es_gratuito = 1   # default agenda municipal
    precio = ""
    link_inscripcion = ""
    # Lista de imágenes: del detalle si las hay, si no fallback a la del listado
    imagenes: list = [item.imagen_url] if item.imagen_url else []
    hora_inicio = item.hora_inicio
    hora_fin = item.hora_fin

    # Complementar con el detalle si lo hay
    if detail is not None:
        descripcion = detail.descripcion_larga or ""
        fecha_fin = detail.fecha_fin or ""
        hora_inicio = hora_inicio or detail.hora_inicio
        hora_fin = hora_fin or detail.hora_fin
        if detail.lugar_nombre:
            lugar = detail.lugar_nombre
        direccion = detail.direccion_fisica or ""
        organizador = detail.organizador_nombre or ""
        if detail.es_gratuito is not None:
            es_gratuito = 1 if detail.es_gratuito else 0
        if detail.precio_euros is not None:
            precio = f"{detail.precio_euros:.2f}"
        link_inscripcion = detail.link_inscripcion or ""
        # El detalle tiene la lista canónica; sobrescribe la miniatura del listado
        if detail.imagenes_urls:
            imagenes = detail.imagenes_urls

    # Deduplicar conservando orden
    seen = set()
    imagenes_dedup = []
    for url in imagenes:
        if url and url not in seen:
            seen.add(url)
            imagenes_dedup.append(url)

    return Event(
        id_unico_evento=id_unico,
        metodo_ingesta="SCRAPING",
        id_usuario_carga="ingestion_cli",
        fuente_id="URL_ESTRUCTURAL",
        fuente_url_original=item.url_detalle or source["url_listado"],
        estado="ACTIVO",
        id_ciudad=source["id_ciudad"],
        nombre_ciudad=source["nombre_ciudad"],
        cp_evento=source["cp_default"],
        lugar_nombre=lugar,
        direccion_fisica=direccion,
        idioma_origen=source["idioma_origen"],
        titulo=item.titulo,
        descripcion_larga=descripcion,
        fecha_inicio=item.fecha_inicio,
        fecha_fin=fecha_fin,
        hora_inicio=hora_inicio or "",
        hora_fin=hora_fin or "",
        es_gratuito=es_gratuito,
        precio_euros=precio,
        requiere_inscripcion=1 if link_inscripcion else 0,
        link_inscripcion=link_inscripcion,
        organizador_nombre=organizador,
        imagenes_urls=json.dumps(imagenes_dedup, ensure_ascii=False),
    )


def is_future(event: Event) -> bool:
    """True si el evento todavía no ha terminado."""
    try:
        end_iso = event.fecha_fin or event.fecha_inicio
        return date.fromisoformat(end_iso) >= date.today()
    except Exception:
        # Si la fecha viene mal, dejamos pasar para no perder eventos por errores
        # de formato. Se pueden filtrar después manualmente revisando el CSV.
        return True


def is_same_domain(url: str, source: dict) -> bool:
    """Verifica que la URL pertenece al dominio de la fuente. Defensa contra
    el LLM si nos diera una URL inventada o externa."""
    try:
        netloc = urlparse(url).netloc or ""
        return source["dominio_esperado"] in netloc
    except Exception:
        return False


# ============================================================================
# CSV
# ============================================================================

def write_csv(events: list[Event], output_path: Path) -> None:
    if not events:
        log.warning("No hay eventos para escribir en CSV")
        return
    fieldnames = list(asdict(events[0]).keys())
    with output_path.open("w", encoding="utf-8", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames, quoting=csv.QUOTE_NONNUMERIC)
        writer.writeheader()
        for ev in events:
            writer.writerow(asdict(ev))
    log.info(f"CSV escrito: {output_path}  ({len(events)} eventos)")


# ============================================================================
# COSTE ESTIMADO
# ============================================================================

# Precios aproximados de gpt-4.1-mini (verifica el actual en
# https://openai.com/api/pricing/). Si usas otro modelo, ajusta estas constantes.
PRICE_INPUT_PER_M = 0.40   # USD por millón de tokens de entrada
PRICE_OUTPUT_PER_M = 1.60  # USD por millón de tokens de salida


def estimate_cost_usd() -> float:
    return (
        _usage["prompt_tokens"] / 1_000_000 * PRICE_INPUT_PER_M +
        _usage["completion_tokens"] / 1_000_000 * PRICE_OUTPUT_PER_M
    )


# ============================================================================
# PIPELINE PRINCIPAL
# ============================================================================

def run_source(source_id: str, output_path: Path) -> None:
    if source_id not in SOURCES:
        sys.exit(f"Fuente desconocida: '{source_id}'. Disponibles: {list(SOURCES.keys())}")
    if not os.getenv("OPENAI_API_KEY"):
        sys.exit(
            "Falta variable de entorno OPENAI_API_KEY.\n"
            "Opciones:\n"
            "  (a) Añadir 'OPENAI_API_KEY=sk-...' a tu archivo .env del proyecto\n"
            "      (requiere: pip install python-dotenv)\n"
            "  (b) Exportarla en la sesión actual de PowerShell:\n"
            "      $env:OPENAI_API_KEY=\"sk-...\""
        )

    source = SOURCES[source_id]
    log.info(f"=== Fuente: {source_id}  ({source['nombre_ciudad']}) ===")

    http = httpx.Client(timeout=HTTP_TIMEOUT_SECONDS, headers={"User-Agent": HTTP_USER_AGENT})
    oai = OpenAI()

    try:
        # 1. Listado
        log.info(f"[1/4] Descargando listado")
        listing_html = download_html(source["url_listado"], http)
        listing_clean = clean_html(listing_html)
        log.info(f"  Limpieza: {len(listing_html):,} → {len(listing_clean):,} chars")

        # 2. Extracción del listado vía LLM
        log.info("[2/4] Extrayendo eventos del listado con LLM")
        items = extract_listing(listing_clean, source, oai)

        # 3. Para cada evento, descargar y procesar el detalle
        log.info(f"[3/4] Procesando detalles ({len(items)} eventos)")
        events: list[Event] = []
        visited_detail_urls: dict[str, DetailData] = {}

        for i, item in enumerate(items, 1):
            log.info(f"  Evento {i}/{len(items)}: {item.titulo[:70]}")
            detail: Optional[DetailData] = None

            if item.url_detalle and is_same_domain(item.url_detalle, source):
                if item.url_detalle in visited_detail_urls:
                    # Mismo evento que ya hemos visto en el listado: reutilizamos
                    detail = visited_detail_urls[item.url_detalle]
                    log.info(f"    URL ya procesada, reutilizando detalle")
                elif len(visited_detail_urls) >= MAX_DETAIL_PAGES:
                    log.warning(f"    Alcanzado MAX_DETAIL_PAGES={MAX_DETAIL_PAGES}, omitiendo detalle")
                else:
                    try:
                        detail_html = download_html(item.url_detalle, http)
                        detail_clean = clean_html(detail_html)
                        detail = extract_detail(detail_clean, item.url_detalle, source, oai)
                        visited_detail_urls[item.url_detalle] = detail
                    except httpx.HTTPError as e:
                        log.error(f"    HTTP error en detalle {item.url_detalle}: {e}")
                    except Exception as e:
                        log.error(f"    Error procesando detalle {item.url_detalle}: {e}")
            elif item.url_detalle:
                log.warning(f"    URL fuera del dominio esperado: {item.url_detalle}")

            event = merge(item, detail, source)
            if is_future(event):
                events.append(event)
            else:
                log.info(f"    Descartado (fecha pasada): {event.fecha_inicio}")

        # 4. CSV
        log.info(f"[4/4] Volcando {len(events)} eventos a CSV")
        write_csv(events, output_path)

        # Reporte final
        log.info("=== Reporte ===")
        log.info(f"  Eventos en el listado:     {len(items)}")
        log.info(f"  Eventos finales en CSV:    {len(events)}")
        log.info(f"  Páginas de detalle leídas: {len(visited_detail_urls)}")
        log.info(f"  Llamadas LLM:              {_usage['calls']}")
        log.info(f"  Tokens input:              {_usage['prompt_tokens']:,}")
        log.info(f"  Tokens output:             {_usage['completion_tokens']:,}")
        log.info(f"  Coste estimado:            ${estimate_cost_usd():.4f}")

    finally:
        http.close()


# ============================================================================
# CLI
# ============================================================================

def main():
    parser = argparse.ArgumentParser(
        description="Fase A — Extracción universal de eventos desde una web municipal."
    )
    parser.add_argument(
        "--fuente",
        required=True,
        help=f"Identificador de la fuente. Disponibles: {list(SOURCES.keys())}",
    )
    parser.add_argument(
        "--output",
        default=None,
        help="Ruta del CSV de salida. Default: out/{fuente}_events.csv",
    )
    args = parser.parse_args()

    output_path = Path(args.output) if args.output else Path(f"out/{args.fuente}_events.csv")
    output_path.parent.mkdir(parents=True, exist_ok=True)

    run_source(args.fuente, output_path)


if __name__ == "__main__":
    main()
