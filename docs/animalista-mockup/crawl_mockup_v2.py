"""
crawl_mockup_v2.py — Mockup v2 de El Viajero Animalista (ver CAMBIOS-V2.md).

Flujo: fuentes (RSS / listado HTML / página / Google News) → candidatos →
filtro de ventana → artículo → clasificación + enriquecimiento con OpenAI →
resolución geográfica INE → playas → dedupe por embeddings → XML v2.

Todo lo descargado y cada respuesta del LLM se cachean en WORK/cache para
poder repetir fases sin volver a pagar ni descargar.

USO
---
  python crawl_mockup_v2.py --work <dir> [--stop-after capture|enrich]
                            [--max-per-source 12] [--window 10] [--limit N]
  Requiere OPENAI_API_KEY en el entorno o en events-query/.env.
  --work debe contener municipios.json (parseado del INE) y se crean
  cache/, candidatos.json, enriquecidos.json y la salida XML.
"""
from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import os
import re
import sys
import threading
import time
import unicodedata
from collections import Counter, defaultdict
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import date, datetime, timedelta
from email.utils import parsedate_to_datetime
from pathlib import Path
from urllib import robotparser
from urllib.parse import quote, urljoin, urlparse
from xml.dom import minidom
from xml.etree import ElementTree as ET

import requests
from bs4 import BeautifulSoup

if hasattr(sys.stdout, "reconfigure"):
    sys.stdout.reconfigure(encoding="utf-8", errors="replace")

HERE = Path(__file__).resolve().parent
try:
    from dotenv import load_dotenv
    load_dotenv(HERE.parents[1] / ".env")
except ImportError:
    pass

from openai import OpenAI  # noqa: E402

# ----------------------------------------------------------------------------- config
TODAY = date.today()
MODEL = os.getenv("OPENAI_MODEL", "gpt-4.1-mini")
PROMPT_VERSION = "v2.2"
EMBED_MODEL = "text-embedding-3-small"
UA = "Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/124.0 Safari/537.36 ViajeroAnimalista-Mockup/0.2"
ROBOTS_UA = "ViajeroAnimalista-Mockup"
TIMEOUT = 25
MAX_RECURSOS_POR_FUENTE = 5
GN_COOKIES = {"CONSENT": "YES+cb.20210720-07-p0.en+FX+410",
              "SOCS": "CAESHAgBEhJnd3NfMjAyMzA4MTAtMF9SQzIaAmRlIAEaBgiA_LyaBg"}
PRICES = {"gpt-4.1-mini": (0.40, 0.10, 1.60), "gpt-4.1-nano": (0.10, 0.025, 0.40), "gpt-4.1": (2.0, 0.5, 8.0)}
EMBED_PRICE = 0.02
URL_FICHA_MUNICIPIO = "https://viajeroanimalista.com/municipios/{slug}-{codigoINE}"
URL_FICHA_PLAYA = "https://viajeroanimalista.com/playas/{slug}"

TIPOS = [("NOTICIA", "Noticia y reportaje"), ("EVENTO", "Evento y actividad"), ("INICIATIVA", "Iniciativa pública"),
         ("CAMPANA", "Campaña y participación"), ("RECURSO", "Recurso y guía práctica")]
TEMAS = [("adopcion-proteccion", "Adopción y protección"), ("salud-bienestar", "Salud y bienestar animal"),
         ("comportamiento-educacion", "Comportamiento y educación animal"), ("legislacion", "Legislación y normativa"),
         ("turismo-viajes", "Turismo y viajes"), ("naturaleza-rutas", "Naturaleza y rutas"), ("playas-caninas", "Playas caninas"),
         ("espacios-convivencia", "Espacios y convivencia"), ("ocio-actividades-deporte", "Ocio, actividades y deporte"),
         ("educacion-divulgacion", "Educación y divulgación"), ("fauna-conservacion", "Fauna y conservación"),
         ("sociedad-historias", "Sociedad e historias animalistas"), ("colonias-felinas-cer", "Colonias felinas y CER"),
         ("maltrato-abandono", "Maltrato y abandono"), ("protectoras-santuarios", "Protectoras y santuarios")]
ANIMALES = [("perros", "Perros"), ("gatos", "Gatos"), ("pequenos-mamiferos", "Conejos y pequeños mamíferos"), ("aves", "Aves"),
            ("reptiles-anfibios", "Reptiles y anfibios"), ("caballos-equidos", "Caballos y otros équidos"), ("granja", "Animales de granja"),
            ("fauna-silvestre", "Fauna silvestre"), ("peces-acuaticos", "Peces y otros animales acuáticos"), ("otros", "Otros animales"),
            ("general", "Animales en general")]
AMBITOS = [("ESTATAL", "Estatal"), ("AUTONOMICO", "Autonómico"), ("PROVINCIAL", "Provincial"), ("MUNICIPAL", "Municipal"), ("VARIOS", "Varios territorios")]
GRUPOS = [("ayuntamientos", "Ayuntamientos"), ("organismos", "Diputaciones, gobiernos autonómicos y organismos estatales"),
          ("protectoras", "Protectoras y refugios"), ("santuarios", "Santuarios"), ("asociaciones", "Asociaciones y fundaciones animalistas"),
          ("medios", "Medios de comunicación"), ("portales", "Portales especializados"), ("profesionales", "Profesionales y centros especializados"),
          ("empresas", "Empresas y establecimientos"), ("creadores", "Creadores de contenido y divulgadores"), ("otras", "Otras fuentes")]
ESTADOS_EVENTO = ["PROXIMO", "EN_CURSO", "FINALIZADO", "CANCELADO", "APLAZADO"]
PROCEDENCIAS = [("extraido", "Dato literal del texto de la fuente"), ("inferido", "Deducido por la IA a partir del texto"),
                ("generado", "Redactado por la IA"), ("maestro", "Resuelto contra el maestro geográfico INE"),
                ("fuente", "Heredado de la configuración de la fuente"), ("no_consta", "La fuente no lo indica")]

CCAA = {"01": "Andalucía", "02": "Aragón", "03": "Principado de Asturias", "04": "Illes Balears", "05": "Canarias", "06": "Cantabria",
        "07": "Castilla y León", "08": "Castilla-La Mancha", "09": "Cataluña", "10": "Comunitat Valenciana", "11": "Extremadura",
        "12": "Galicia", "13": "Comunidad de Madrid", "14": "Región de Murcia", "15": "Comunidad Foral de Navarra", "16": "País Vasco",
        "17": "La Rioja", "18": "Ceuta", "19": "Melilla"}
PROV = {"01": ("Araba/Álava", "16"), "02": ("Albacete", "08"), "03": ("Alicante/Alacant", "10"), "04": ("Almería", "01"), "05": ("Ávila", "07"),
        "06": ("Badajoz", "11"), "07": ("Illes Balears", "04"), "08": ("Barcelona", "09"), "09": ("Burgos", "07"), "10": ("Cáceres", "11"),
        "11": ("Cádiz", "01"), "12": ("Castellón/Castelló", "10"), "13": ("Ciudad Real", "08"), "14": ("Córdoba", "01"), "15": ("A Coruña", "12"),
        "16": ("Cuenca", "08"), "17": ("Girona", "09"), "18": ("Granada", "01"), "19": ("Guadalajara", "08"), "20": ("Gipuzkoa", "16"),
        "21": ("Huelva", "01"), "22": ("Huesca", "02"), "23": ("Jaén", "01"), "24": ("León", "07"), "25": ("Lleida", "09"), "26": ("La Rioja", "17"),
        "27": ("Lugo", "12"), "28": ("Madrid", "13"), "29": ("Málaga", "01"), "30": ("Murcia", "14"), "31": ("Navarra", "15"), "32": ("Ourense", "12"),
        "33": ("Asturias", "03"), "34": ("Palencia", "07"), "35": ("Las Palmas", "05"), "36": ("Pontevedra", "12"), "37": ("Salamanca", "07"),
        "38": ("Santa Cruz de Tenerife", "05"), "39": ("Cantabria", "06"), "40": ("Segovia", "07"), "41": ("Sevilla", "01"), "42": ("Soria", "07"),
        "43": ("Tarragona", "09"), "44": ("Teruel", "02"), "45": ("Toledo", "08"), "46": ("Valencia/València", "10"), "47": ("Valladolid", "07"),
        "48": ("Bizkaia", "16"), "49": ("Zamora", "07"), "50": ("Zaragoza", "02"), "51": ("Ceuta", "18"), "52": ("Melilla", "19")}
ALIAS = {  # nombre normalizado -> (nivel, código)
    "alava": ("PROVINCIA", "01"), "araba": ("PROVINCIA", "01"), "alacant": ("PROVINCIA", "03"), "alicante": ("PROVINCIA", "03"),
    "castello": ("PROVINCIA", "12"), "castellon": ("PROVINCIA", "12"), "valencia": ("PROVINCIA", "46"), "la coruna": ("PROVINCIA", "15"),
    "coruna": ("PROVINCIA", "15"), "orense": ("PROVINCIA", "32"), "guipuzcoa": ("PROVINCIA", "20"), "vizcaya": ("PROVINCIA", "48"),
    "gerona": ("PROVINCIA", "17"), "lerida": ("PROVINCIA", "25"), "baleares": ("CCAA", "04"), "islas baleares": ("CCAA", "04"),
    "mallorca": ("PROVINCIA", "07"), "menorca": ("PROVINCIA", "07"), "ibiza": ("PROVINCIA", "07"), "eivissa": ("PROVINCIA", "07"),
    "tenerife": ("PROVINCIA", "38"), "gran canaria": ("PROVINCIA", "35"), "lanzarote": ("PROVINCIA", "35"), "fuerteventura": ("PROVINCIA", "35"),
    "catalunya": ("CCAA", "09"), "cataluna": ("CCAA", "09"), "euskadi": ("CCAA", "16"), "pais vasco": ("CCAA", "16"),
    "comunidad valenciana": ("CCAA", "10"), "comunitat valenciana": ("CCAA", "10"), "comunidad de madrid": ("CCAA", "13"),
    "region de murcia": ("CCAA", "14"), "castilla la mancha": ("CCAA", "08"), "castilla y leon": ("CCAA", "07"), "asturias": ("CCAA", "03"),
    "principado de asturias": ("CCAA", "03"), "navarra": ("CCAA", "15"), "andalucia": ("CCAA", "01"), "aragon": ("CCAA", "02"),
    "canarias": ("CCAA", "05"), "islas canarias": ("CCAA", "05"), "cantabria": ("CCAA", "06"), "extremadura": ("CCAA", "11"),
    "galicia": ("CCAA", "12"), "la rioja": ("CCAA", "17"), "ceuta": ("CCAA", "18"), "melilla": ("CCAA", "19"),
}


def norm(s: str | None) -> str:
    s = unicodedata.normalize("NFKD", s or "")
    s = "".join(c for c in s if not unicodedata.combining(c))
    s = re.sub(r"[^a-z0-9 ]+", " ", s.lower())
    return re.sub(r"\s+", " ", s).strip()


def slugify(s: str) -> str:
    return re.sub(r"\s+", "-", norm(s))


def sha(s: str) -> str:
    return hashlib.sha256(s.encode("utf-8")).hexdigest()


# ----------------------------------------------------------------------------- cost tracker
class Cost:
    def __init__(self):
        self.lock = threading.Lock()
        self.calls = 0; self.tin = 0; self.tcached = 0; self.tout = 0; self.extra = 0.0
        self.by_op = defaultdict(lambda: [0, 0, 0, 0])

    def add(self, resp, op):
        u = getattr(resp, "usage", None)
        if not u:
            return
        cached = getattr(getattr(u, "prompt_tokens_details", None), "cached_tokens", 0) or 0
        with self.lock:
            self.calls += 1; self.tin += u.prompt_tokens - cached; self.tcached += cached; self.tout += u.completion_tokens
            b = self.by_op[op]; b[0] += 1; b[1] += u.prompt_tokens - cached; b[2] += cached; b[3] += u.completion_tokens

    def add_embed(self, tokens):
        with self.lock:
            self.calls += 1; self.extra += tokens / 1e6 * EMBED_PRICE

    def usd(self):
        p_in, p_cached, p_out = PRICES.get(MODEL, PRICES["gpt-4.1-mini"])
        return self.tin / 1e6 * p_in + self.tcached / 1e6 * p_cached + self.tout / 1e6 * p_out + self.extra


COST = Cost()
session = requests.Session()
session.headers.update({"User-Agent": UA, "Accept-Language": "es-ES,es;q=0.9,ca;q=0.8"})
_oai = None


def oai():
    global _oai
    if _oai is None:
        _oai = OpenAI(timeout=120, max_retries=3)
    return _oai


# ----------------------------------------------------------------------------- cache
class Cache:
    def __init__(self, root: Path):
        self.root = root; root.mkdir(parents=True, exist_ok=True)

    def get(self, kind, key):
        p = self.root / kind / (sha(key) + ".json")
        return json.loads(p.read_text(encoding="utf-8")) if p.exists() else None

    def put(self, kind, key, value):
        p = self.root / kind / (sha(key) + ".json"); p.parent.mkdir(exist_ok=True)
        p.write_text(json.dumps(value, ensure_ascii=False), encoding="utf-8")


CACHE: Cache = None  # type: ignore


# ----------------------------------------------------------------------------- http
_robots = {}
_rlock = threading.Lock()


def robots_allows(url):
    u = urlparse(url); host = f"{u.scheme}://{u.netloc}"
    with _rlock:
        rp = _robots.get(host, "unset")
        if rp == "unset":
            rp = None
            try:
                rr = session.get(host + "/robots.txt", timeout=15)
                if rr.status_code == 200 and "<html" not in rr.text[:300].lower():
                    rp = robotparser.RobotFileParser(); rp.parse(rr.text.splitlines())
            except Exception:
                rp = None
            _robots[host] = rp
    return True if rp is None else (rp.can_fetch(ROBOTS_UA, url) and rp.can_fetch("*", url))


def fetch(url, kind="html"):
    """kind='feed': los RSS/consultas son sindicación ofrecida a lectores; no se aplica robots.txt."""
    c = CACHE.get("http", url)
    if c:
        return c
    out = {"url": url, "status": None, "final_url": url, "text": None, "error": None}
    try:
        if kind != "feed" and not robots_allows(url):
            out["error"] = "ROBOTS"
        else:
            r = session.get(url, timeout=TIMEOUT, allow_redirects=True)
            out["status"] = r.status_code; out["final_url"] = r.url
            if r.status_code == 200:
                if r.encoding is None or r.encoding.lower() == "iso-8859-1":
                    r.encoding = r.apparent_encoding
                out["text"] = r.text
    except Exception as e:
        out["error"] = f"{type(e).__name__}"
    if out["status"] is not None:  # no cachear errores de red ni robots
        CACHE.put("http", url, out)
    return out


def gn_decode(gn_url):
    c = CACHE.get("gn", gn_url)
    if c:
        return c.get("url")
    base64_str = urlparse(gn_url).path.rstrip("/").split("/")[-1]
    real = None
    try:
        r = session.get(f"https://news.google.com/articles/{base64_str}", cookies=GN_COOKIES, timeout=TIMEOUT)
        soup = BeautifulSoup(r.text, "lxml"); div = soup.select_one("c-wiz > div")
        if div is not None and div.get("data-n-a-sg"):
            sig, ts = div["data-n-a-sg"], div["data-n-a-ts"]
            payload = ["Fbv4je", f'["garturlreq",[["X","X",["X","X"],null,null,1,1,"US:en",null,1,null,null,null,null,null,0,1],"X","X",1,[1,1,1],1,1,null,0,0,null,0],"{base64_str}",{ts},"{sig}"]']
            r2 = session.post("https://news.google.com/_/DotsSplashUi/data/batchexecute",
                              headers={"Content-Type": "application/x-www-form-urlencoded;charset=UTF-8"},
                              data=f"f.req={quote(json.dumps([[payload]]))}", cookies=GN_COOKIES, timeout=TIMEOUT)
            parsed = json.loads(r2.text.split("\n\n")[1])[:-2]
            real = json.loads(parsed[0][2])[1]
    except Exception:
        real = None
    CACHE.put("gn", gn_url, {"url": real})
    return real


# ----------------------------------------------------------------------------- parsing
def parse_date(s):
    if not s:
        return None
    s = str(s).strip()
    try:
        return parsedate_to_datetime(s).date().isoformat()
    except Exception:
        pass
    m = re.search(r"(\d{4})-(\d{2})-(\d{2})", s)
    if m:
        return f"{m.group(1)}-{m.group(2)}-{m.group(3)}"
    m = re.search(r"(\d{1,2})/(\d{1,2})/(\d{4})", s)
    if m:
        return f"{m.group(3)}-{int(m.group(2)):02d}-{int(m.group(1)):02d}"
    return None


def parse_rss(text):
    items = []
    try:
        root = ET.fromstring(text.encode("utf-8") if isinstance(text, str) else text)
    except ET.ParseError:
        root = ET.fromstring(re.sub(r"&(?!amp;|lt;|gt;|quot;|apos;|#)", "&amp;", text).encode("utf-8"))
    ns_atom = "{http://www.w3.org/2005/Atom}"
    for it in root.iter("item"):
        g = lambda t: (it.findtext(t) or "").strip()
        items.append({"titulo": g("title"), "url": g("link") or (it.find("guid").text if it.find("guid") is not None else ""),
                      "fecha": parse_date(g("pubDate") or g("{http://purl.org/dc/elements/1.1/}date")),
                      "descripcion": re.sub(r"<[^>]+>", " ", g("description"))[:600]})
    for it in root.iter(ns_atom + "entry"):
        link = it.find(ns_atom + "link"); href = link.get("href") if link is not None else ""
        items.append({"titulo": (it.findtext(ns_atom + "title") or "").strip(), "url": href,
                      "fecha": parse_date(it.findtext(ns_atom + "published") or it.findtext(ns_atom + "updated")),
                      "descripcion": re.sub(r"<[^>]+>", " ", it.findtext(ns_atom + "summary") or "")[:600]})
    return items


def html_text_links(html, base_url, max_chars=28000):
    soup = BeautifulSoup(html, "lxml")
    for t in soup(["script", "style", "noscript", "iframe", "svg", "form", "footer", "nav", "header"]):
        t.decompose()
    main = soup.find("main") or soup.body or soup
    arts = main.find_all("article")
    if len(arts) >= 3:
        container = main
    else:
        container = main
    lines = []
    for el in container.descendants:
        if el.name == "a" and el.get("href"):
            txt = el.get_text(" ", strip=True)
            if txt and len(txt) > 3:
                lines.append(f"[{txt}]({urljoin(base_url, el['href'])})")
        elif el.name in ("h1", "h2", "h3", "h4", "p", "li", "time", "span") and el.find("a") is None:
            txt = el.get_text(" ", strip=True)
            if txt and len(txt) > 2:
                lines.append(txt)
    seen = set(); out = []
    for ln in lines:
        if ln not in seen:
            seen.add(ln); out.append(ln)
    return "\n".join(out)[:max_chars]


def _meta(soup, *names):
    for n in names:
        tag = soup.find("meta", attrs={"property": n}) or soup.find("meta", attrs={"name": n})
        if tag and tag.get("content"):
            return tag["content"].strip()
    return None


def extract_article(url, html):
    soup = BeautifulSoup(html, "lxml")
    ld_date = None
    for s in soup.find_all("script", type="application/ld+json"):
        try:
            data = json.loads(s.string or "")
        except Exception:
            continue
        nodes = data if isinstance(data, list) else [data]
        for node in list(nodes):
            if isinstance(node, dict) and "@graph" in node:
                nodes.extend(n for n in node["@graph"] if isinstance(n, dict))
            if isinstance(node, dict) and node.get("datePublished") and not ld_date:
                ld_date = node["datePublished"]
    title = _meta(soup, "og:title") or (soup.title.get_text(strip=True) if soup.title else None)
    desc = _meta(soup, "og:description", "description")
    fecha = _meta(soup, "article:published_time", "date", "DC.date.issued", "pubdate", "datePublished") or ld_date
    mod = _meta(soup, "article:modified_time", "og:updated_time", "dateModified")
    fecha_texto = None
    t_tag = soup.find("time", attrs={"datetime": True})
    if t_tag:
        fecha_texto = parse_date(t_tag["datetime"])
    if not fecha_texto:
        MESES = {"enero": 1, "febrero": 2, "marzo": 3, "abril": 4, "mayo": 5, "junio": 6, "julio": 7, "agosto": 8, "septiembre": 9, "setiembre": 9,
                 "octubre": 10, "noviembre": 11, "diciembre": 12, "gener": 1, "febrer": 2, "marc": 3, "març": 3, "maig": 5, "juny": 6, "juliol": 7,
                 "setembre": 9, "novembre": 11, "desembre": 12, "xaneiro": 1, "febreiro": 2, "xuño": 6, "xullo": 7, "setembro": 9, "outubro": 10, "novembro": 11, "decembro": 12}
        txt = soup.get_text(" ", strip=True)[:4000]
        m = re.search(r"\b(\d{1,2})\s+(?:de\s+|d')?([a-zç]+)\s+(?:de\s+|del\s+)?(\d{4})\b", txt, flags=re.I)
        if m and m.group(2).lower() in MESES:
            try:
                fecha_texto = date(int(m.group(3)), MESES[m.group(2).lower()], int(m.group(1))).isoformat()
            except ValueError:
                fecha_texto = None
        if not fecha_texto:
            m = re.search(r"\b(\d{1,2})[/.](\d{1,2})[/.](20\d{2})\b", txt)
            if m:
                try:
                    fecha_texto = date(int(m.group(3)), int(m.group(2)), int(m.group(1))).isoformat()
                except ValueError:
                    fecha_texto = None
    for t in soup(["script", "style", "nav", "footer", "aside", "noscript", "iframe", "form", "header", "figure"]):
        t.decompose()
    container = soup.find("article") or soup.find("main") or soup.body or soup
    paras = [p.get_text(" ", strip=True) for p in container.find_all(["p", "li", "h2", "h3"])]
    paras = [p for p in paras if len(p) > 40]
    body = "\n".join(paras)
    if len(body) < 300:  # fallback: todo el texto
        body = container.get_text("\n", strip=True)
    return {"titulo_html": title, "descripcion": desc, "fecha_meta": parse_date(fecha) or fecha_texto, "fecha_texto": fecha_texto, "modificado": parse_date(mod),
            "cuerpo": body[:6000], "n_chars": len(body)}


# ----------------------------------------------------------------------------- LLM
LISTADO_SCHEMA = {
    "name": "items_listado", "strict": True,
    "schema": {"type": "object", "additionalProperties": False, "required": ["items"],
               "properties": {"items": {"type": "array", "items": {
                   "type": "object", "additionalProperties": False,
                   "required": ["titulo", "url", "fecha", "tipo_probable"],
                   "properties": {
                       "titulo": {"type": "string"},
                       "url": {"type": "string", "description": "URL ABSOLUTA tal como aparece entre paréntesis en el texto. Nunca inventes ni completes."},
                       "fecha": {"type": ["string", "null"], "description": "YYYY-MM-DD si aparece junto al ítem; null si no."},
                       "tipo_probable": {"type": "string", "enum": ["NOTICIA", "EVENTO", "INICIATIVA", "CAMPANA", "RECURSO", "DESCARTAR"]},
                   }}}}}}

LISTADO_SYSTEM = (
    "Eres el extractor de listados del buscador El Viajero Animalista (España). Recibes el texto de una página de "
    "noticias, actualidad, blog o agenda de una entidad animalista, administración o medio, con los enlaces en "
    "formato [texto](url). Devuelve SOLO los ítems de contenido (noticias, reportajes, eventos, campañas, guías) "
    "con su URL exacta. Excluye menús, categorías, etiquetas, paginación, fichas individuales de animales en "
    "adopción, directorios y enlaces a redes sociales. Máximo 20 ítems, los más recientes primero si hay fechas. "
    f"Hoy es {TODAY.isoformat()}."
)

ENRICH_SCHEMA = {
    "name": "contenido_animalista", "strict": True,
    "schema": {
        "type": "object", "additionalProperties": False,
        "required": ["relevante", "relevancia", "motivo_descarte", "tipo", "titulo", "resumen", "idioma_origen",
                     "fecha_publicacion", "ultima_actualizacion", "publica_nombre", "organiza_nombre", "organiza_tipo",
                     "evento", "campana", "recurso", "ambito", "lugares", "playas", "temas", "animales", "etiquetas",
                     "procedencia", "nota_calidad"],
        "properties": {
            "relevante": {"type": "boolean", "description": "true si trata de animales de compañía, protección animal, convivencia con animales, fauna o viajar con animales, y se refiere a España."},
            "relevancia": {"type": "number", "description": "0 a 1."},
            "motivo_descarte": {"type": ["string", "null"], "enum": ["NO_RELEVANTE", "NO_RELEVANTE_GEO", "FICHA_ADOPCION", "DIRECTORIO", "SIN_CONTENIDO", "DUPLICADO_INTERNO", None]},
            "tipo": {"type": "string", "enum": ["NOTICIA", "EVENTO", "INICIATIVA", "CAMPANA", "RECURSO"]},
            "titulo": {"type": "string", "description": "Título claro y fiel en castellano, máx. 120 caracteres. Traduce si el original es catalán u otro idioma."},
            "resumen": {"type": "string", "description": "2-3 frases en castellano con el dato esencial (qué, quién, dónde, cuándo). Sin repetir el título. Sin añadir nada que no conste."},
            "idioma_origen": {"type": "string", "enum": ["es", "ca", "en", "gl", "eu", "otro"]},
            "fecha_publicacion": {"type": ["string", "null"], "description": "YYYY-MM-DD. Usa la fecha de metadatos si se da; null si no consta."},
            "ultima_actualizacion": {"type": ["string", "null"]},
            "publica_nombre": {"type": ["string", "null"], "description": "Medio o entidad que publica el texto."},
            "organiza_nombre": {"type": ["string", "null"], "description": "Quien organiza, impulsa o protagoniza (ayuntamiento, protectora, empresa). null si no consta o es lo mismo que quien publica y no hay actividad."},
            "organiza_tipo": {"type": ["string", "null"], "enum": ["PUBLICA", "ASOCIACION", "EMPRESA", "MEDIO", "PARTICULAR", None]},
            "evento": {"type": "object", "additionalProperties": False,
                       "required": ["fecha_inicio", "fecha_fin", "horario", "lugar", "municipio", "precio", "es_gratuito", "inscripcion", "condiciones", "acceso_animales", "estado_fuente"],
                       "properties": {
                           "fecha_inicio": {"type": ["string", "null"], "description": "YYYY-MM-DD solo para EVENTO con fecha confirmada."},
                           "fecha_fin": {"type": ["string", "null"]},
                           "horario": {"type": ["string", "null"], "description": "Tal como consta, p. ej. '10:00 a 18:00'."},
                           "lugar": {"type": ["string", "null"]},
                           "municipio": {"type": ["string", "null"]},
                           "precio": {"type": ["string", "null"], "description": "Texto literal del precio; 'Gratuito' solo si está confirmado."},
                           "es_gratuito": {"type": ["boolean", "null"]},
                           "inscripcion": {"type": ["string", "null"], "description": "Cómo inscribirse o URL, si consta."},
                           "condiciones": {"type": ["string", "null"], "description": "Condiciones de participación si constan."},
                           "acceso_animales": {"type": ["string", "null"], "description": "Si consta si se puede ir con animales y en qué condiciones."},
                           "estado_fuente": {"type": ["string", "null"], "enum": ["CANCELADO", "APLAZADO", None], "description": "Solo si la fuente lo dice."},
                       }},
            "campana": {"type": "object", "additionalProperties": False,
                        "required": ["entidad_impulsora", "como_participar", "enlace_oficial", "fecha_limite"],
                        "properties": {"entidad_impulsora": {"type": ["string", "null"]}, "como_participar": {"type": ["string", "null"]},
                                       "enlace_oficial": {"type": ["string", "null"]}, "fecha_limite": {"type": ["string", "null"]}}},
            "recurso": {"type": "object", "additionalProperties": False, "required": ["autoria", "ultima_actualizacion"],
                        "properties": {"autoria": {"type": ["string", "null"]}, "ultima_actualizacion": {"type": ["string", "null"]}}},
            "ambito": {"type": "string", "enum": ["ESTATAL", "AUTONOMICO", "PROVINCIAL", "MUNICIPAL", "VARIOS"],
                       "description": "Territorio al que afecta la información. Una ley estatal es ESTATAL aunque se publique en Madrid."},
            "lugares": {"type": "array", "items": {"type": "object", "additionalProperties": False,
                        "required": ["nombre", "nivel", "provincia", "rol", "principal"],
                        "properties": {"nombre": {"type": "string"}, "nivel": {"type": "string", "enum": ["CCAA", "PROVINCIA", "MUNICIPIO"]},
                                       "provincia": {"type": ["string", "null"], "description": "Provincia del municipio si el texto la da o es evidente."},
                                       "rol": {"type": "string", "enum": ["OCURRE", "AFECTA"], "description": "OCURRE: donde pasa el hecho. AFECTA: territorio al que afecta la información."},
                                       "principal": {"type": "boolean"}}},
                        "description": "Vacío si el ámbito es ESTATAL sin lugar concreto. NO incluyas la sede de la entidad que publica si el hecho no ocurre allí."},
            "playas": {"type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["nombre", "municipio"],
                       "properties": {"nombre": {"type": "string"}, "municipio": {"type": ["string", "null"]}}},
                       "description": "Playas concretas mencionadas (nombre tal como aparece)."},
            "temas": {"type": "array", "minItems": 1, "maxItems": 3, "items": {"type": "object", "additionalProperties": False, "required": ["slug", "principal"],
                      "properties": {"slug": {"type": "string", "enum": [t[0] for t in TEMAS]}, "principal": {"type": "boolean"}}}},
            "animales": {"type": "array", "items": {"type": "object", "additionalProperties": False, "required": ["slug", "principal"],
                         "properties": {"slug": {"type": "string", "enum": [a[0] for a in ANIMALES]}, "principal": {"type": "boolean"}}}},
            "etiquetas": {"type": "array", "minItems": 4, "maxItems": 10, "items": {"type": "string"},
                          "description": "Etiquetas genéricas en castellano, minúsculas, sin nombres propios ni lugares."},
            "procedencia": {"type": "object", "additionalProperties": False,
                            "required": ["titulo", "resumen", "fecha_publicacion", "evento", "organiza", "ambito", "lugares", "animales", "temas", "etiquetas"],
                            "properties": {k: {"type": "string", "enum": ["extraido", "inferido", "generado", "no_consta"]}
                                           for k in ["titulo", "resumen", "fecha_publicacion", "evento", "organiza", "ambito", "lugares", "animales", "temas", "etiquetas"]}},
            "nota_calidad": {"type": ["string", "null"], "description": "Solo si hay algo dudoso: texto truncado, fecha incierta, posible nota de prensa comercial, idioma, etc."},
        }}}

TEMAS_DESC = "\n".join(f"- {s}: {n}" for s, n in TEMAS)
ENRICH_SYSTEM = f"""Eres el clasificador y redactor del buscador El Viajero Animalista, un portal español sobre animales de compañía, protección animal, convivencia y viajar con animales. Hoy es {TODAY.isoformat()}.

REGLAS DURAS
1. No inventes. Si un dato (horario, precio, lugar, condición de acceso, fecha) no consta en el texto, devuelve null. Nunca deduzcas una fecha de evento a partir de una fecha de publicación.
2. Relevancia: solo contenidos sobre animales (compañía, fauna, granja, protección, convivencia, viajes con animales) y referidos a España o a entidades españolas. Hechos de fuera de España: relevante=false, motivo NO_RELEVANTE_GEO. EXCEPCIONES relevantes: normativa europea o internacional que se aplica en España (p. ej. reglas de la UE para viajar con perros y gatos), y campañas o acciones de entidades españolas aunque el hecho ocurra fuera. Fichas individuales de animales en adopción: motivo FICHA_ADOPCION. Directorios, páginas institucionales ('quiénes somos', 'contacto', 'hazte socio') y páginas de servicio sin contenido informativo: DIRECTORIO. Si el municipio o la entidad son de México, Colombia, Argentina, Chile, Perú, Ecuador, Uruguay, Venezuela, Bolivia, República Dominicana u otro país no europeo, es NO_RELEVANTE_GEO aunque el texto esté en castellano: comprueba el país antes de aceptar. Notas de prensa puramente comerciales valen si aportan información útil, con nota de calidad.
3. Tipo (uno): NOTICIA = actualidad y reportajes. EVENTO = actividad con fecha de celebración (una jornada de un ayuntamiento es EVENTO, no INICIATIVA). INICIATIVA = acción, plan, ordenanza o servicio de una administración pública sin fecha de evento. CAMPANA = campañas, voluntariado, recogidas solidarias, peticiones, sensibilización en las que se pide participar. RECURSO = información práctica válida en el tiempo (guías, condiciones oficiales, normativa explicada).
4. Temas (1 a 3, uno principal), con estos significados:
{TEMAS_DESC}
'comportamiento-educacion' es conducta y necesidades de los animales; 'educacion-divulgacion' es formación y sensibilización de las personas. Una playa canina puede llevar playas-caninas, turismo-viajes y legislacion a la vez.
5. Animales: los que protagonizan el contenido. 'general' solo si no se concreta ninguno.
6. Geografía: distingue dónde ocurre el hecho (rol OCURRE) del territorio al que afecta (AFECTA). No asignes un municipio solo porque allí tiene la sede quien publica. Ámbito: ESTATAL para normas y hechos de toda España; AUTONOMICO, PROVINCIAL, MUNICIPAL según el territorio; VARIOS si afecta a varios territorios concretos.
7. Idioma: título, resumen y etiquetas siempre en castellano aunque la fuente esté en catalán, gallego, euskera o inglés.
8. Resumen: 2-3 frases, claro, fiel, sin repetir el título ni relleno institucional. Nada de "verificado" ni valoraciones.
9. Procedencia: 'extraido' si el dato está literal en el texto, 'inferido' si lo deduces, 'generado' si lo redactas tú, 'no_consta' si el campo queda vacío."""


def llm_json(system, user, schema, op):
    key = f"{MODEL}|{PROMPT_VERSION}|{op}|{system[:80]}|{user}"
    c = CACHE.get("llm", key)
    if c:
        return c
    resp = oai().chat.completions.create(model=MODEL, temperature=0,
                                         messages=[{"role": "system", "content": system}, {"role": "user", "content": user}],
                                         response_format={"type": "json_schema", "json_schema": schema})
    COST.add(resp, op)
    data = json.loads(resp.choices[0].message.content)
    CACHE.put("llm", key, data)
    return data


def embed(texts):
    out = [None] * len(texts); todo = []
    for i, t in enumerate(texts):
        c = CACHE.get("emb", t)
        if c:
            out[i] = c["v"]
        else:
            todo.append(i)
    for start in range(0, len(todo), 64):
        idx = todo[start:start + 64]
        resp = oai().embeddings.create(model=EMBED_MODEL, input=[texts[i] for i in idx])
        COST.add_embed(resp.usage.total_tokens)
        for j, i in enumerate(idx):
            out[i] = resp.data[j].embedding; CACHE.put("emb", texts[i], {"v": out[i]})
    return out


def cosine(a, b):
    return sum(x * y for x, y in zip(a, b)) / (math.sqrt(sum(x * x for x in a)) * math.sqrt(sum(y * y for y in b)) + 1e-9)


# ----------------------------------------------------------------------------- geo
class Geo:
    def __init__(self, municipios):
        self.by_norm = defaultdict(list); self.by_code = {}
        for m in municipios:
            self.by_code[m["codigo"]] = m
            self.by_norm[m["nombre_norm"]].append(m)
            # 'Coruña, A' -> también 'coruna'
            base = norm(m["nombre_ine"].split(",")[0]) if "," in m["nombre_ine"] else None
            if base and base != m["nombre_norm"]:
                self.by_norm[base].append(m)
            # bilingües 'Alacant/Alicante'
            if "/" in m["nombre"]:
                for part in m["nombre"].split("/"):
                    self.by_norm[norm(part)].append(m)
        self.prov_by_norm = {norm(v[0]): k for k, v in PROV.items()}
        for k, v in PROV.items():
            for part in v[0].split("/"):
                self.prov_by_norm[norm(part)] = k
        self.ccaa_by_norm = {norm(v): k for k, v in CCAA.items()}

    def resolve_prov(self, name):
        n = norm(name)
        if n in self.prov_by_norm:
            return self.prov_by_norm[n]
        if n in ALIAS and ALIAS[n][0] == "PROVINCIA":
            return ALIAS[n][1]
        return None

    def resolve_ccaa(self, name):
        n = norm(name)
        if n in self.ccaa_by_norm:
            return self.ccaa_by_norm[n]
        if n in ALIAS and ALIAS[n][0] == "CCAA":
            return ALIAS[n][1]
        return None

    def resolve(self, lugar, prov_hint=None):
        """Devuelve dict {nivel, codigo, nombre, provincia_cod, ccaa_cod, metodo} o None."""
        nombre = lugar.get("nombre") or ""; nivel = lugar.get("nivel")
        n = norm(re.sub(r"^(ayuntamiento|ajuntament|concello|concejo|ciudad|ciutat|municipio|villa|localidad)\s+(de|d'|del|de la|de les|de los)\s+", "", nombre, flags=re.I))
        hint = self.resolve_prov(lugar.get("provincia")) if lugar.get("provincia") else prov_hint
        if nivel == "CCAA" or (nivel != "MUNICIPIO" and n in self.ccaa_by_norm):
            c = self.resolve_ccaa(nombre)
            if c:
                return {"nivel": "CCAA", "codigo": c, "nombre": CCAA[c], "ccaa_cod": c, "metodo": "maestro"}
        if nivel == "PROVINCIA" or (nivel != "MUNICIPIO" and n in self.prov_by_norm):
            p = self.resolve_prov(nombre)
            if p:
                return {"nivel": "PROVINCIA", "codigo": p, "nombre": PROV[p][0], "provincia_cod": p, "ccaa_cod": PROV[p][1], "metodo": "maestro"}
        if n in ALIAS:
            lvl, code = ALIAS[n]
            if lvl == "CCAA":
                return {"nivel": "CCAA", "codigo": code, "nombre": CCAA[code], "ccaa_cod": code, "metodo": "alias"}
            return {"nivel": "PROVINCIA", "codigo": code, "nombre": PROV[code][0], "provincia_cod": code, "ccaa_cod": PROV[code][1], "metodo": "alias"}
        cands = self.by_norm.get(n, [])
        if not cands and " " in n:  # 'tobera (frias)' etc.
            for tok in re.findall(r"\(([^)]+)\)", nombre):
                cands = self.by_norm.get(norm(tok), [])
                if cands:
                    break
        if len(cands) > 1 and hint:
            cands = [c for c in cands if c["provincia"] == hint] or cands
        if len(cands) == 1:
            m = cands[0]
            return {"nivel": "MUNICIPIO", "codigo": m["codigo"], "nombre": m["nombre"], "provincia_cod": m["provincia"],
                    "ccaa_cod": PROV[m["provincia"]][1], "metodo": "maestro"}
        if len(cands) > 1:  # ambiguo sin pista: subir a provincia si todas comparten provincia, si no descartar
            provs = {c["provincia"] for c in cands}
            if len(provs) == 1:
                p = provs.pop()
                return {"nivel": "PROVINCIA", "codigo": p, "nombre": PROV[p][0], "provincia_cod": p, "ccaa_cod": PROV[p][1], "metodo": "ambiguo->provincia"}
            return None
        if hint and nivel == "MUNICIPIO":  # municipio desconocido pero provincia conocida
            return {"nivel": "PROVINCIA", "codigo": hint, "nombre": PROV[hint][0], "provincia_cod": hint, "ccaa_cod": PROV[hint][1], "metodo": "no-encontrado->provincia"}
        return None


# ----------------------------------------------------------------------------- pipeline
def collect_candidates(fuentes, max_per_source):
    """Devuelve lista de candidatos {fuente_id, titulo, url, fecha, descripcion, medio} y stats por fuente."""
    cands = []; stats = {}
    def work(f):
        st = {"vistos": 0, "candidatos": 0, "estado": "OK", "error": None}
        items = []
        try:
            if f["modo"] == "rss":
                r = fetch(f["rss"], kind="feed")
                if r["text"]:
                    items = parse_rss(r["text"])
                else:
                    st["estado"] = "ERROR"; st["error"] = r["error"] or f"HTTP {r['status']}"
            elif f["modo"] == "google_news":
                r = fetch(f["url"], kind="feed")
                if r["text"]:
                    for it in parse_rss(r["text"]):
                        real = gn_decode(it["url"]) if "news.google.com" in it["url"] else it["url"]
                        src = re.search(r"<source[^>]*>([^<]+)</source>", r["text"]) if False else None
                        it["medio"] = it["titulo"].rsplit(" - ", 1)[1].strip() if " - " in it["titulo"] else None
                        it["titulo"] = it["titulo"].rsplit(" - ", 1)[0].strip() if " - " in it["titulo"] else it["titulo"]
                        if real:
                            it["url"] = real; items.append(it)
                        else:
                            st.setdefault("sin_decodificar", 0); st["sin_decodificar"] += 1
                else:
                    st["estado"] = "ERROR"; st["error"] = r["error"] or f"HTTP {r['status']}"
            elif f["modo"] == "listado":
                r = fetch(f["url"])
                if r["text"]:
                    text = html_text_links(r["text"], r["final_url"])
                    data = llm_json(LISTADO_SYSTEM, f"FUENTE: {f['nombre']} ({f['url']})\n\n{text}", LISTADO_SCHEMA, "listado")
                    host = urlparse(f["url"]).netloc.replace("www.", "")
                    for it in data["items"]:
                        if it["tipo_probable"] == "DESCARTAR" or not it["url"].startswith("http"):
                            continue
                        if host not in urlparse(it["url"]).netloc.replace("www.", ""):
                            continue
                        items.append({"titulo": it["titulo"], "url": it["url"], "fecha": it["fecha"], "descripcion": ""})
                else:
                    st["estado"] = "ERROR"; st["error"] = r["error"] or f"HTTP {r['status']}"
            elif f["modo"] == "pagina":
                items = [{"titulo": f["nombre"], "url": f["url"], "fecha": None, "descripcion": "", "pagina": True}]
        except Exception as e:
            st["estado"] = "ERROR"; st["error"] = f"{type(e).__name__}: {e}"[:200]
        st["vistos"] = len(items)
        items = items[:max_per_source] if f["modo"] != "google_news" else items[:100]
        for it in items:
            it["fuente_id"] = f["id"]
        st["candidatos"] = len(items)
        return f["id"], st, items
    with ThreadPoolExecutor(6) as ex:
        for fid, st, items in ex.map(work, fuentes):
            stats[fid] = st; cands.extend(items)
            print(f"  {fid:16} {st['estado']:5} vistos={st['vistos']:3} cand={st['candidatos']:3} {st.get('error') or ''}", flush=True)
    return cands, stats


def in_window(fecha, window):
    if not fecha:
        return None
    try:
        d = date.fromisoformat(fecha[:10])
    except ValueError:
        return None
    return (TODAY - timedelta(days=window)) <= d <= TODAY + timedelta(days=1)


def fetch_articles(cands):
    def fetch_one(c):
        r = fetch(c["url"])
        c["http"] = r["status"]; c["error"] = r["error"]; c["url_final"] = r["final_url"]
        if r["text"]:
            c.update(extract_article(r["final_url"], r["text"]))
        return c
    with ThreadPoolExecutor(6) as ex:
        return list(ex.map(fetch_one, cands))


def enrich(c, fuente):
    user = (f"FUENTE QUE PUBLICA: {fuente['nombre']} (grupo: {fuente['grupo']}; cobertura declarada: {fuente.get('cobertura')}; "
            f"provincia de referencia: {fuente.get('provincia_ref')})\n"
            f"MEDIO (si viene de un agregador): {c.get('medio') or '-'}\nURL: {c.get('url_final') or c['url']}\n"
            f"FECHA EN METADATOS: {c.get('fecha_meta') or c.get('fecha') or '-'} · FECHA VISTA EN EL TEXTO: {c.get('fecha_texto') or '-'} · MODIFICADO: {c.get('modificado') or '-'}\n"
            f"TÍTULO HTML: {c.get('titulo_html') or c.get('titulo')}\nDESCRIPCIÓN: {c.get('descripcion') or '-'}\n\n"
            f"TEXTO:\n{c.get('cuerpo') or ''}")
    return llm_json(ENRICH_SYSTEM, user, ENRICH_SCHEMA, "enriquecimiento")


def evento_estado(ev):
    if ev.get("estado_fuente"):
        return ev["estado_fuente"]
    try:
        fi = date.fromisoformat(ev["fecha_inicio"]) if ev.get("fecha_inicio") else None
        ff = date.fromisoformat(ev["fecha_fin"]) if ev.get("fecha_fin") else fi
    except ValueError:
        return None
    if not fi:
        return None
    if ff and ff < TODAY:
        return "FINALIZADO"
    if fi <= TODAY <= (ff or fi):
        return "EN_CURSO"
    return "PROXIMO"


def build_xml(contenidos, fuentes, stats, descartes, run, geo, playas, municipios_usados, out_path):
    root = ET.Element("viajeroAnimalista", version="0.2", generado=datetime.now().isoformat(timespec="seconds"),
                      ambito="España", idioma="es", ventanaDias=str(run["ventana"]),
                      urlFichaMunicipio=URL_FICHA_MUNICIPIO, urlFichaPlaya=URL_FICHA_PLAYA)
    tx = ET.SubElement(root, "taxonomia")
    def lista(parent, tag, child, items, **extra):
        el = ET.SubElement(parent, tag)
        for s, n in items:
            ET.SubElement(el, child, slug=s, nombre=n)
        return el
    lista(tx, "tiposContenido", "tipo", TIPOS); lista(tx, "temas", "tema", TEMAS); lista(tx, "animales", "animal", ANIMALES)
    lista(tx, "ambitos", "ambito", AMBITOS); lista(tx, "gruposFuente", "grupo", GRUPOS)
    ee = ET.SubElement(tx, "estadosEvento")
    for s in ESTADOS_EVENTO:
        ET.SubElement(ee, "estado", slug=s, nombre=s.replace("_", " ").capitalize())
    pr = ET.SubElement(tx, "procedencias")
    for s, n in PROCEDENCIAS:
        ET.SubElement(pr, "procedencia", slug=s, descripcion=n)
    g = ET.SubElement(root, "geo")
    for cc, cn in CCAA.items():
        ce = ET.SubElement(g, "ccaa", codigo=cc, nombre=cn)
        for pc, (pn, pcc) in PROV.items():
            if pcc == cc:
                ET.SubElement(ce, "provincia", codigo=pc, nombre=pn)
    cm = ET.SubElement(root, "catalogoMunicipios")
    for code in sorted(municipios_usados):
        m = geo.by_code.get(code)
        if m:
            ET.SubElement(cm, "municipio", codigoINE=code, nombre=m["nombre"], provincia=PROV[m["provincia"]][0],
                          ccaa=CCAA[PROV[m["provincia"]][1]], slug=slugify(m["nombre"]),
                          urlFicha=URL_FICHA_MUNICIPIO.format(slug=slugify(m["nombre"]), codigoINE=code))
    cp = ET.SubElement(root, "catalogoPlayas", nota="Catálogo de ejemplo (costa del Maresme). Lo mantendría la web de Viajero Animalista.")
    for p in playas:
        ET.SubElement(cp, "playa", id=p["id"], nombre=p["nombre"], municipio=p["municipio"], municipioINE=p.get("codigo") or "",
                      slug=slugify(p["nombre"]), urlFicha=URL_FICHA_PLAYA.format(slug=slugify(p["nombre"])), nota=p.get("nota", ""))
    fs = ET.SubElement(root, "fuentes")
    for f in fuentes:
        st = stats.get(f["id"], {})
        attrs = dict(id=f["id"], nombre=f["nombre"], grupo=f["grupo"], modo=f["modo"], url=f["url"], activa="false" if f.get("excluir") else "true",
                     vistos=str(st.get("vistos", 0)), aportados=str(st.get("aportados", 0)), descartados=str(st.get("descartados", 0)),
                     estado=("EXCLUIDA" if f.get("excluir") else st.get("estado", "OK")))
        if f.get("rss"):
            attrs["rss"] = f["rss"]
        if f.get("excluir"):
            attrs["motivoExclusion"] = f["excluir"]
        if st.get("error"):
            attrs["ultimoError"] = st["error"]
        if f.get("provincia_ref") and f["provincia_ref"] not in ("Varias / no procede", "No confirmada"):
            attrs["provinciaRef"] = f["provincia_ref"]
        ET.SubElement(fs, "fuente", **attrs)
    cs = ET.SubElement(root, "contenidos", total=str(len(contenidos)))
    for c in contenidos:
        e = c["e"]; el = ET.SubElement(cs, "contenido", id=c["id"], tipo=e["tipo"])
        ET.SubElement(el, "titulo").text = e["titulo"]
        ET.SubElement(el, "resumen").text = e["resumen"]
        if c["fecha_pub"]:
            ET.SubElement(el, "fechaPublicacion").text = c["fecha_pub"]
        if e.get("ultima_actualizacion"):
            ET.SubElement(el, "ultimaActualizacion").text = e["ultima_actualizacion"]
        ET.SubElement(el, "idiomaOrigen").text = e["idioma_origen"]
        if e["tipo"] == "EVENTO":
            ev = e["evento"]; a = {}
            for k, xk in [("fecha_inicio", "fechaInicio"), ("fecha_fin", "fechaFin"), ("horario", "horario"), ("lugar", "lugar"),
                          ("precio", "precio"), ("inscripcion", "inscripcion"), ("condiciones", "condiciones"), ("acceso_animales", "accesoAnimales")]:
                if ev.get(k):
                    a[xk] = str(ev[k])
            if ev.get("es_gratuito") is not None:
                a["esGratuito"] = "true" if ev["es_gratuito"] else "false"
            if c.get("estado_evento"):
                a["estado"] = c["estado_evento"]
            ET.SubElement(el, "evento", **a)
        if e["tipo"] == "CAMPANA":
            ca = e["campana"]; a = {xk: str(ca[k]) for k, xk in [("entidad_impulsora", "entidadImpulsora"), ("como_participar", "comoParticipar"),
                                                              ("enlace_oficial", "enlaceOficial"), ("fecha_limite", "fechaLimite")] if ca.get(k)}
            ET.SubElement(el, "campana", **a)
        if e["tipo"] == "RECURSO":
            rc = e["recurso"]; a = {xk: str(rc[k]) for k, xk in [("autoria", "autoria"), ("ultima_actualizacion", "ultimaActualizacion")] if rc.get(k)}
            ET.SubElement(el, "recurso", **a)
        ET.SubElement(el, "publica", nombre=c["publica"], grupo=c["grupo"])
        if e.get("organiza_nombre"):
            ET.SubElement(el, "organiza", nombre=e["organiza_nombre"], tipo=e.get("organiza_tipo") or "")
        ET.SubElement(el, "ambito").text = e["ambito"]
        ub = ET.SubElement(el, "ubicacion")
        for l in c["lugares"]:
            a = dict(nivel=l["nivel"], codigoINE=l["codigo"], nombre=l["nombre"], rol=l["rol"], principal="true" if l["principal"] else "false")
            if l.get("provincia_cod"):
                a["provincia"] = PROV[l["provincia_cod"]][0]
            a["ccaa"] = CCAA[l["ccaa_cod"]]
            if l["nivel"] == "MUNICIPIO":
                a["urlFicha"] = URL_FICHA_MUNICIPIO.format(slug=slugify(l["nombre"]), codigoINE=l["codigo"])
            ET.SubElement(ub, "lugar", **a)
        if c["playas"]:
            pe = ET.SubElement(el, "playas")
            for p in c["playas"]:
                ET.SubElement(pe, "playa", ref=p["id"], nombre=p["nombre"], urlFicha=URL_FICHA_PLAYA.format(slug=slugify(p["nombre"])))
        an = ET.SubElement(el, "animales")
        for a_ in e["animales"]:
            ET.SubElement(an, "animal", slug=a_["slug"], principal="true" if a_["principal"] else "false")
        te = ET.SubElement(el, "temas")
        for t in e["temas"]:
            ET.SubElement(te, "tema", slug=t["slug"], principal="true" if t["principal"] else "false")
        et = ET.SubElement(el, "etiquetas")
        for t in e["etiquetas"]:
            ET.SubElement(et, "etiqueta").text = t
        fu = ET.SubElement(el, "fuentes")
        for f in c["fuentes"]:
            ET.SubElement(fu, "fuente", ref=f["ref"], medio=f["medio"], url=f["url"], principal="true" if f["principal"] else "false", fecha=f.get("fecha") or "")
        it = ET.SubElement(el, "interno", relevancia=f"{e['relevancia']:.2f}", fuentesAportoExtraccion=str(sum(1 for f in c["fuentes"] if f.get("aporto"))))
        ET.SubElement(it, "procedencia", **{k: v for k, v in e["procedencia"].items()}, geo=c["geo_metodo"])
        if c.get("lugares_no_resueltos"):
            ET.SubElement(it, "lugaresNoResueltos").text = "; ".join(c["lugares_no_resueltos"])
        if e.get("nota_calidad"):
            ET.SubElement(it, "notaCalidad").text = e["nota_calidad"]
        if c.get("dedupe_nota"):
            ET.SubElement(it, "dedupe").text = c["dedupe_nota"]
    ej = ET.SubElement(root, "ejecucion", **{k: str(v) for k, v in run.items() if k != "ventana"})
    de = ET.SubElement(ej, "descartes")
    for motivo, lst in sorted(descartes.items(), key=lambda kv: -len(kv[1])):
        d = ET.SubElement(de, "descarte", motivo=motivo, cantidad=str(len(lst)))
        for s in lst[:5]:
            ET.SubElement(d, "muestra", fuente=s.get("fuente_id", ""), titulo=(s.get("titulo") or "")[:140], url=s.get("url", ""))
    cg = ET.SubElement(ej, "coberturaGeo")
    cnt = Counter()
    for c in contenidos:
        seen = set()
        for l in c["lugares"]:
            seen.add(CCAA[l["ccaa_cod"]])
        for s in seen or {"(Estatal)"}:
            cnt[s] += 1
    for name, n in cnt.most_common():
        ET.SubElement(cg, "ccaa", nombre=name, contenidos=str(n))
    xml = minidom.parseString(ET.tostring(root, encoding="utf-8")).toprettyxml(indent="  ", encoding="utf-8")
    Path(out_path).write_bytes(xml)


def main():
    global CACHE
    ap = argparse.ArgumentParser()
    ap.add_argument("--work", required=True)
    ap.add_argument("--fuentes", default=str(HERE / "fuentes_v2.json"))
    ap.add_argument("--playas", default=str(HERE / "playas_maresme.json"))
    ap.add_argument("--out", default=str(HERE / "contenidos.xml"))
    ap.add_argument("--window", type=int, default=10)
    ap.add_argument("--max-per-source", type=int, default=20)
    ap.add_argument("--limit", type=int, default=None, help="Máximo de candidatos a enriquecer (pruebas)")
    ap.add_argument("--stop-after", choices=["capture", "enrich"], default=None)
    ap.add_argument("--only", default=None, help="IDs de fuente separados por coma (pruebas)")
    args = ap.parse_args()
    work = Path(args.work); CACHE = Cache(work / "cache")
    t0 = datetime.now()

    fuentes_all = json.load(open(args.fuentes, encoding="utf-8"))["fuentes"]
    fuentes = [f for f in fuentes_all if not f.get("excluir")]
    if args.only:
        fuentes = [f for f in fuentes if f["id"] in args.only.split(",")]
    fmap = {f["id"]: f for f in fuentes_all}
    municipios = json.load(open(work / "municipios.json", encoding="utf-8"))
    geo = Geo(municipios)
    playas = json.load(open(args.playas, encoding="utf-8"))["playas"]
    for p in playas:
        r = geo.resolve({"nombre": p["municipio"], "nivel": "MUNICIPIO"}, p.get("provincia"))
        p["codigo"] = r["codigo"] if r and r["nivel"] == "MUNICIPIO" else None

    # 1-2. candidatos
    print(f"== Captura: {len(fuentes)} fuentes activas, ventana {args.window} días")
    cands, stats = collect_candidates(fuentes, args.max_per_source)
    # dedupe por URL
    seen = set(); uniq = []
    for c in cands:
        k = c["url"].split("#")[0].rstrip("/")
        if k in seen:
            continue
        seen.add(k); uniq.append(c)
    descartes = defaultdict(list)
    keep = []
    EVENT_RE = re.compile(r"\b(jornada|feria|fira|taller|charla|xerrada|marcha|carrera|cursa|canicross|curso|exposici|concurso|festival|evento|encuentro|trobada|visita|voluntari|gala|mercadillo|caminata|ruta|salida|excursi|conferencia|webinar|seminario|congreso|campeonato|torneo|desfile|inscripci)", re.I)
    for c in uniq:
        w = in_window(c.get("fecha"), args.window)
        if w is False and not c.get("pagina"):
            if EVENT_RE.search(c.get("titulo") or "") and in_window(c.get("fecha"), 60):
                c["posible_evento"] = True
            else:
                descartes["CADUCADO_FEED"].append(c); continue
        keep.append(c)
    print(f"   candidatos únicos {len(uniq)} · dentro de ventana o sin fecha {len(keep)} · caducados por fecha del feed {len(descartes['CADUCADO_FEED'])}")
    json.dump({"candidatos": keep, "stats": stats}, open(work / "candidatos.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    if args.stop_after == "capture":
        print(f"coste hasta ahora: ${COST.usd():.3f} ({COST.calls} llamadas)"); return

    # 3. artículos
    if args.limit:
        keep = keep[:args.limit]
    print(f"== Artículos: {len(keep)}")
    arts = fetch_articles(keep)
    ok = []
    for c in arts:
        if c.get("error") == "ROBOTS":
            descartes["ROBOTS"].append(c)
        elif c.get("http") != 200:
            descartes["HTTP_ERROR"].append(c)
        elif (c.get("n_chars") or 0) < 200:
            descartes["SIN_CONTENIDO"].append(c)
        else:
            fecha = c.get("fecha_meta") or c.get("fecha")
            w = in_window(fecha, args.window)
            if w is False and not c.get("pagina") and not c.get("posible_evento"):
                descartes["CADUCADO"].append(c)
            else:
                ok.append(c)
    print(f"   legibles {len(ok)} · robots {len(descartes['ROBOTS'])} · http {len(descartes['HTTP_ERROR'])} · sin texto {len(descartes['SIN_CONTENIDO'])} · caducados {len(descartes['CADUCADO'])}")

    # 4. enriquecimiento
    print(f"== Enriquecimiento con {MODEL}: {len(ok)} artículos")
    enriched = []
    def enrich_one(c):
        try:
            return c, enrich(c, fmap[c["fuente_id"]]), None
        except Exception as e:
            return c, None, f"{type(e).__name__}: {e}"[:200]
    done = 0
    with ThreadPoolExecutor(4) as ex:
        for c, e, err in ex.map(enrich_one, ok):
            done += 1
            if err:
                c["error"] = err; descartes["ERROR_LLM"].append(c); continue
            c["e"] = e; enriched.append(c)
            if done % 25 == 0:
                print(f"   {done}/{len(ok)} · ${COST.usd():.3f}", flush=True)
    json.dump(enriched, open(work / "enriquecidos.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1, default=str)
    if args.stop_after == "enrich":
        print(f"coste: ${COST.usd():.3f}"); return

    # 5. filtros post-LLM
    contenidos = []; recursos_por_fuente = {}
    for c in enriched:
        e = c["e"]
        if not e["relevante"] or e["relevancia"] < 0.6:
            descartes[e.get("motivo_descarte") or "NO_RELEVANTE"].append(c); continue
        fecha_pub = e.get("fecha_publicacion") or c.get("fecha_meta") or c.get("fecha")
        if e["tipo"] == "EVENTO":
            ev = e["evento"]
            if not ev.get("fecha_inicio"):
                e["tipo"] = "NOTICIA"  # evento sin fecha confirmada se trata como noticia
            else:
                c["estado_evento"] = evento_estado(ev)
                if c["estado_evento"] == "FINALIZADO" and (not fecha_pub or in_window(fecha_pub, args.window) is False):
                    descartes["EVENTO_PASADO"].append(c); continue
        if e["tipo"] != "RECURSO":
            if not fecha_pub:
                descartes["SIN_FECHA"].append(c); continue
            if in_window(fecha_pub, args.window) is False and not (e["tipo"] == "EVENTO" and c.get("estado_evento") in ("PROXIMO", "EN_CURSO")):
                descartes["CADUCADO"].append(c); continue
        if e["tipo"] == "RECURSO":
            recursos_por_fuente[c["fuente_id"]] = recursos_por_fuente.get(c["fuente_id"], 0) + 1
            if recursos_por_fuente[c["fuente_id"]] > MAX_RECURSOS_POR_FUENTE:
                descartes["RECURSO_EXCEDENTE"].append(c); continue
        c["fecha_pub"] = fecha_pub or ("" if e["tipo"] == "RECURSO" else TODAY.isoformat())
        f = fmap[c["fuente_id"]]
        c["publica"] = (c.get("medio") or e.get("publica_nombre") or f["nombre"]) if f["modo"] == "google_news" else f["nombre"]
        c["grupo"] = f["grupo"]
        # geo
        hint = geo.resolve_prov(f["provincia_ref"]) if f.get("provincia_ref") else None
        lug = []; nores = []; metodos = set()
        for l in e["lugares"]:
            r = geo.resolve(l, hint)
            if r:
                r.update(rol=l["rol"], principal=l["principal"]); metodos.add(r["metodo"])
                if not any(x["codigo"] == r["codigo"] and x["nivel"] == r["nivel"] for x in lug):
                    lug.append(r)
            else:
                nores.append(l["nombre"])
        if e["tipo"] == "EVENTO" and e["evento"].get("municipio") and not any(x["nivel"] == "MUNICIPIO" for x in lug):
            r = geo.resolve({"nombre": e["evento"]["municipio"], "nivel": "MUNICIPIO"}, hint)
            if r:
                r.update(rol="OCURRE", principal=True); lug.insert(0, r); metodos.add(r["metodo"])
        if lug and not any(x["principal"] for x in lug):
            lug[0]["principal"] = True
        if e["ambito"] == "MUNICIPAL" and e["lugares"] and not lug:
            descartes["NO_RELEVANTE_GEO"].append(c); continue  # municipio que no existe en España (comarcas y parques naturales se conservan)
        c["lugares"] = lug; c["lugares_no_resueltos"] = nores
        c["geo_metodo"] = ",".join(sorted(metodos)) if metodos else ("no_consta" if not e["lugares"] else "no_resuelto")
        # playas
        pl = []
        texto = norm(" ".join([e["titulo"], e["resumen"]] + [p["nombre"] for p in e["playas"]] + [l["nombre"] for l in e["lugares"]]))
        muni_codes = {x["codigo"] for x in lug if x["nivel"] == "MUNICIPIO"}
        for p in playas:
            if p.get("codigo") and p["codigo"] in muni_codes and any(norm(a) in texto for a in [p["nombre"]] + p.get("alias", [])):
                pl.append(p)
        c["playas"] = pl
        c["fuentes"] = [{"ref": c["fuente_id"], "medio": c["publica"], "url": c.get("url_final") or c["url"], "principal": True, "aporto": True, "fecha": c["fecha_pub"] or ""}]
        c["id"] = "c-" + sha(f"{e['tipo']}|{norm(e['titulo'])}|{c['fecha_pub'] or c['url']}")[:12]
        contenidos.append(c)
    print(f"== Tras filtros: {len(contenidos)} contenidos")

    # 6. dedupe por embeddings
    texts = [f"{c['e']['titulo']}. {c['e']['resumen']}" for c in contenidos]
    vecs = embed(texts) if contenidos else []
    merged = []; absorbed = set()
    for i, c in enumerate(contenidos):
        if i in absorbed:
            continue
        for j in range(i + 1, len(contenidos)):
            if j in absorbed or contenidos[j]["e"]["tipo"] != c["e"]["tipo"]:
                continue
            try:
                dd = abs((date.fromisoformat(c["fecha_pub"]) - date.fromisoformat(contenidos[j]["fecha_pub"])).days)
            except ValueError:
                dd = 0 if c["e"]["tipo"] == "RECURSO" else 99
            if dd <= 7 and cosine(vecs[i], vecs[j]) >= 0.90:
                absorbed.add(j)
                o = contenidos[j]
                c["fuentes"].append({"ref": o["fuente_id"], "medio": o["publica"], "url": o["fuentes"][0]["url"], "principal": False, "aporto": False, "fecha": o["fecha_pub"]})
                c["dedupe_nota"] = (c.get("dedupe_nota") or "") + f"Fusionado con '{o['e']['titulo'][:60]}' (coseno ≥ 0,90). "
                for l in o["lugares"]:
                    if not any(x["codigo"] == l["codigo"] and x["nivel"] == l["nivel"] for x in c["lugares"]):
                        l = dict(l); l["principal"] = False; c["lugares"].append(l)
        merged.append(c)
    print(f"== Dedupe: {len(contenidos)} → {len(merged)} ({len(absorbed)} fusionados)")
    merged.sort(key=lambda c: (c["e"]["tipo"] != "EVENTO", c["fecha_pub"]), reverse=False)
    merged.sort(key=lambda c: c["fecha_pub"] or "0000", reverse=True)

    # stats por fuente
    for c in merged:
        for f in c["fuentes"]:
            stats.setdefault(f["ref"], {}).setdefault("aportados", 0); stats[f["ref"]]["aportados"] += 1
    for motivo, lst in descartes.items():
        for c in lst:
            stats.setdefault(c.get("fuente_id", "?"), {}).setdefault("descartados", 0); stats[c["fuente_id"]]["descartados"] += 1

    munis = {l["codigo"] for c in merged for l in c["lugares"] if l["nivel"] == "MUNICIPIO"} | {p["codigo"] for p in playas if p.get("codigo")}
    run = {"id": f"run-{TODAY.strftime('%Y%m%d')}-v2", "inicio": t0.isoformat(timespec="seconds"), "fin": datetime.now().isoformat(timespec="seconds"),
           "modelo": MODEL, "costeUsd": f"{COST.usd():.3f}", "llamadasLlm": COST.calls, "tokensIn": COST.tin + COST.tcached, "tokensOut": COST.tout,
           "fuentesActivas": len(fuentes), "fuentesError": sum(1 for s in stats.values() if s.get("estado") == "ERROR"),
           "candidatos": len(uniq), "articulosLeidos": len(ok), "contenidos": len(merged), "descartados": sum(len(v) for v in descartes.values()),
           "ventana": args.window}
    build_xml(merged, fuentes_all, stats, descartes, run, geo, playas, munis, args.out)
    json.dump({"run": run, "stats": stats, "descartes": {k: len(v) for k, v in descartes.items()}, "by_op": dict(COST.by_op)},
              open(work / "run.json", "w", encoding="utf-8"), ensure_ascii=False, indent=1)
    with open(work / "descartes.csv", "w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, delimiter=";"); w.writerow(["motivo", "fuente", "titulo", "url"])
        for motivo, lst in descartes.items():
            for c in lst:
                w.writerow([motivo, c.get("fuente_id"), (c.get("e", {}).get("titulo") if c.get("e") else c.get("titulo")) or "", c.get("url")])
    print(f"== XML: {args.out} · contenidos {len(merged)} · coste ${COST.usd():.3f} · {COST.calls} llamadas")
    print("   tipos:", Counter(c["e"]["tipo"] for c in merged))
    print("   descartes:", {k: len(v) for k, v in descartes.items()})


if __name__ == "__main__":
    main()
