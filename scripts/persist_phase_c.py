"""
persist_phase_c.py — Persistencia en BD de eventos enriquecidos.

Fase C del módulo de ingesta KM0_Events. Toma un CSV producido por Fase B
(eventos extraídos y enriquecidos) y los persiste en MySQL:

  - EVENTOS_MASTER:     upsert idempotente por ID_Unico_Evento.
  - EVENTO_HORARIOS:    delete + insert por evento (re-ejecución limpia).
  - EVENTO_CATEGORIAS:  INSERT IGNORE (idempotente).
  - BINARIOS_STORAGE:   descarga imágenes a disco local + insert por checksum.

Las imágenes se descargan a ./static/images/{id_unico_evento}/ y se determina
orientación (horizontal/vertical/cuadrada) y dimensiones. La aplicación
FastAPI debe servir ese directorio como recurso estático en /static/images/...

Eventos sin fecha_inicio se descartan silenciosamente (se reportan al final).

USO
---
    python persist_phase_c.py --input out/malgrat_events_enriched.csv
    python persist_phase_c.py --input out/blanes_events_enriched.csv

DEPENDENCIAS
------------
    pip install pymysql Pillow httpx python-dotenv

REQUIERE VARIABLES DE ENTORNO (.env)
------------------------------------
    DB_HOST, DB_PORT, DB_USER, DB_PASSWORD, DB_NAME

REQUIERE EN BD
--------------
    - Esquema base (KM0_Events.sql).
    - Categorías jerárquicas pobladas (categorias_jerarquia.sql).
    - Columnas de imágenes en BINARIOS_STORAGE (images_delta.sql).
    - Códigos postales en CODIGOS_POSTALES (el script crea CP/ciudad que falten con coords por defecto;
      si el CSV usa otro ID que la BD pero mismo nombre, se usa el ID canónico de la BD).
"""

import argparse
import csv
import hashlib
import io
import json
import logging
import os
import sys
from pathlib import Path
from typing import Optional

import httpx
import pymysql
import pymysql.cursors
from PIL import Image

try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass


# ============================================================================
# CONFIGURACIÓN
# ============================================================================

DB_HOST = os.getenv("DB_HOST", "localhost")
DB_PORT = int(os.getenv("DB_PORT", "3306"))
DB_USER = os.getenv("DB_USER")
DB_PASSWORD = os.getenv("DB_PASSWORD")
DB_NAME = os.getenv("DB_NAME")

# Directorio raíz donde se guardan las imágenes descargadas.
# La aplicación FastAPI debería servir este directorio en /static/images/...
IMAGES_DIR = Path("static") / "images"

# Umbrales de orientación (ratio = ancho / alto)
RATIO_HORIZONTAL_MIN = 1.20
RATIO_VERTICAL_MAX = 0.80

HTTP_TIMEOUT = 30
HTTP_USER_AGENT = "KM0EventsIngestion/0.1"
MAX_IMAGE_SIZE_BYTES = 20 * 1024 * 1024

# Centro aproximado por CP cuando CODIGOS_POSTALES aún no tiene esa fila (FK + coordenadas_json).
DEFAULT_CP_COORDS: dict[str, tuple[float, float]] = {
    "08380": (41.6467, 2.7414),  # Malgrat de Mar
    "17300": (41.6753, 2.7925),  # Blanes
}
DEFAULT_CP_COORDS_FALLBACK = (41.5912, 1.5209)  # Cataluña (genérico)


# ============================================================================
# LOGGING
# ============================================================================

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger("persist")


# ============================================================================
# CONEXIÓN BD
# ============================================================================

def get_connection():
    if not all([DB_HOST, DB_USER, DB_PASSWORD, DB_NAME]):
        sys.exit("Faltan variables de entorno DB_HOST/DB_USER/DB_PASSWORD/DB_NAME. Verifica tu .env.")
    return pymysql.connect(
        host=DB_HOST,
        port=DB_PORT,
        user=DB_USER,
        password=DB_PASSWORD,
        database=DB_NAME,
        charset="utf8mb4",
        cursorclass=pymysql.cursors.DictCursor,
        autocommit=False,
    )


def ensure_ciudad(conn, id_ciudad: int, nombre: str) -> None:
    """Inserta ciudad por ID+nombre si no existe (FK). No usar si ya hay otro ID con el mismo nombre."""
    nombre = (nombre or "").strip() or f"Ciudad_{id_ciudad}"
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO CIUDADES (ID_Ciudad, Nombre, Provincia, Latitud, Longitud)
            VALUES (%s, %s, NULL, NULL, NULL)
            ON DUPLICATE KEY UPDATE Nombre = VALUES(Nombre)
            """,
            (id_ciudad, nombre),
        )


def resolve_ciudad_fk(conn, row: dict) -> int:
    """ID_Ciudad válido para FK: coincide por nombre con BD, por ID del CSV, o alta nueva.

    Evita el caso típico CSV id_ciudad=2 y BD con Blanes en id=5 (UNIQUE en Nombre impediría otro INSERT).
    """
    nombre = (row.get("nombre_ciudad") or "").strip()
    raw_id = (row.get("id_ciudad") or "").strip()
    csv_id = int(raw_id) if raw_id else 0

    with conn.cursor() as cur:
        if nombre:
            cur.execute("SELECT ID_Ciudad FROM CIUDADES WHERE Nombre = %s LIMIT 1", (nombre,))
            hit = cur.fetchone()
            if hit:
                return int(hit["ID_Ciudad"])
        if csv_id:
            cur.execute("SELECT ID_Ciudad FROM CIUDADES WHERE ID_Ciudad = %s", (csv_id,))
            if cur.fetchone():
                return csv_id

    if not csv_id:
        raise ValueError(
            "No se puede resolver FK ciudad: falta id_ciudad en CSV y la ciudad no existe por nombre."
        )
    if not nombre:
        raise ValueError(
            f"No se puede crear ciudad id={csv_id}: falta nombre_ciudad en CSV."
        )
    ensure_ciudad(conn, csv_id, nombre)
    return csv_id


def ensure_codigo_postal(conn, cp: str, id_ciudad: int, cp_map: dict) -> None:
    """Garantiza CP en CODIGOS_POSTALES (FK_EVENTO_CP). Actualiza cp_map en memoria."""
    cp = (cp or "").strip()
    if not cp:
        return
    with conn.cursor() as cur:
        cur.execute("SELECT CP FROM CODIGOS_POSTALES WHERE CP=%s", (cp,))
        if cur.fetchone():
            return
    lat, lng = DEFAULT_CP_COORDS.get(cp, DEFAULT_CP_COORDS_FALLBACK)
    with conn.cursor() as cur:
        cur.execute(
            """
            INSERT INTO CODIGOS_POSTALES (CP, ID_Ciudad, Latitud, Longitud)
            VALUES (%s, %s, %s, %s)
            """,
            (cp, id_ciudad, lat, lng),
        )
    cp_map[cp] = {"lat": lat, "lng": lng}
    log.info(f"    Catálogo: insertado CP {cp} (ciudad {id_ciudad}) con coords por defecto")


def ensure_geografia(conn, row: dict, cp_map: dict) -> None:
    """Ciudad + código postal requeridos por FK antes del upsert del evento."""
    cid = resolve_ciudad_fk(conn, row)
    row["id_ciudad"] = str(cid)
    ensure_codigo_postal(conn, row.get("cp_evento") or "", cid, cp_map)


# ============================================================================
# LOOKUPS PRE-CARGADOS
# ============================================================================

def load_categorias_map(conn) -> dict:
    """Devuelve dict {Slug: ID_Categoria} de categorías activas."""
    with conn.cursor() as cur:
        cur.execute("SELECT ID_Categoria, Slug FROM CATEGORIAS WHERE Activo = 1")
        return {r["Slug"]: r["ID_Categoria"] for r in cur.fetchall()}


def load_cps_map(conn) -> dict:
    """Devuelve dict {CP: {lat, lng}} de todos los CPs registrados."""
    with conn.cursor() as cur:
        cur.execute("SELECT CP, Latitud, Longitud FROM CODIGOS_POSTALES")
        return {
            r["CP"]: {"lat": float(r["Latitud"]), "lng": float(r["Longitud"])}
            for r in cur.fetchall()
        }


# ============================================================================
# EVENTOS_MASTER
# ============================================================================

def upsert_evento_master(conn, row: dict, coordenadas_json: Optional[str]) -> int:
    """INSERT ... ON DUPLICATE KEY UPDATE de EVENTOS_MASTER.
    Devuelve rowcount: 1 = insertado nuevo, 2 = actualizado, 0 = sin cambios."""

    # Procesar precio
    precio_str = (row.get("precio_euros") or "").strip()
    precio = float(precio_str) if precio_str else None

    # Tags por idioma (JSON arrays en EVENTOS_MASTER).
    try:
        tags_ca_list = json.loads(row.get("tags_ca") or "[]")
    except json.JSONDecodeError:
        tags_ca_list = []
    try:
        tags_es_list = json.loads(row.get("tags_es") or "[]")
    except json.JSONDecodeError:
        tags_es_list = []
    tags_ca_json = json.dumps(tags_ca_list, ensure_ascii=False)
    tags_es_json = json.dumps(tags_es_list, ensure_ascii=False)

    # Si no hay Titulo_ES (no enriquecido aún), reutilizar el catalán
    titulo_ca = row.get("titulo") or ""
    titulo_es = row.get("titulo_es") or titulo_ca

    poblacion = (row.get("nombre_ciudad") or "").strip() or "Sin población"

    sql = """
    INSERT INTO EVENTOS_MASTER (
        ID_Unico_Evento, Metodo_Ingesta, ID_Usuario_Carga,
        Fuente_ID, Fuente_URL_Original, Estado,
        ID_Ciudad, CP_Evento, Poblacion_Nombre, Lugar_Nombre, Direccion_Fisica, Coordenadas_JSON,
        Organizador_Nombre, Es_Patrocinado, Idioma_Origen,
        Titulo_CAT, Titulo_ES, Desc_Larga_CAT, Desc_Larga_ES,
        Tags_CAT, Tags_ES,
        Es_Gratuito, Precio_Euros, Requiere_Inscripcion,
        Link_Entradas_Inscripcion
    ) VALUES (
        %(id_unico_evento)s, %(metodo_ingesta)s, %(id_usuario_carga)s,
        %(fuente_id)s, %(fuente_url_original)s, %(estado)s,
        %(id_ciudad)s, %(cp_evento)s, %(poblacion_nombre)s, %(lugar_nombre)s, %(direccion_fisica)s, %(coordenadas_json)s,
        %(organizador_nombre)s, 0, %(idioma_origen)s,
        %(titulo_ca)s, %(titulo_es)s, %(desc_larga_ca)s, %(desc_larga_es)s,
        %(tags_cat)s, %(tags_es)s,
        %(es_gratuito)s, %(precio_euros)s, %(requiere_inscripcion)s,
        %(link_inscripcion)s
    )
    ON DUPLICATE KEY UPDATE
        Fuente_URL_Original = VALUES(Fuente_URL_Original),
        ID_Ciudad = VALUES(ID_Ciudad),
        CP_Evento = VALUES(CP_Evento),
        Poblacion_Nombre = VALUES(Poblacion_Nombre),
        Lugar_Nombre = VALUES(Lugar_Nombre),
        Direccion_Fisica = VALUES(Direccion_Fisica),
        Coordenadas_JSON = VALUES(Coordenadas_JSON),
        Organizador_Nombre = VALUES(Organizador_Nombre),
        Idioma_Origen = VALUES(Idioma_Origen),
        Titulo_CAT = VALUES(Titulo_CAT),
        Titulo_ES = VALUES(Titulo_ES),
        Desc_Larga_CAT = VALUES(Desc_Larga_CAT),
        Desc_Larga_ES = VALUES(Desc_Larga_ES),
        Tags_CAT = VALUES(Tags_CAT),
        Tags_ES = VALUES(Tags_ES),
        Es_Gratuito = VALUES(Es_Gratuito),
        Precio_Euros = VALUES(Precio_Euros),
        Requiere_Inscripcion = VALUES(Requiere_Inscripcion),
        Link_Entradas_Inscripcion = VALUES(Link_Entradas_Inscripcion)
    """

    params = {
        "id_unico_evento": row["id_unico_evento"],
        "metodo_ingesta": row.get("metodo_ingesta") or "SCRAPING",
        "id_usuario_carga": row.get("id_usuario_carga") or "ingestion_cli",
        "fuente_id": row.get("fuente_id") or "URL_ESTRUCTURAL",
        "fuente_url_original": row.get("fuente_url_original") or "",
        "estado": row.get("estado") or "ACTIVO",
        "id_ciudad": int(row["id_ciudad"]),
        "cp_evento": row.get("cp_evento") or None,
        "poblacion_nombre": poblacion,
        "lugar_nombre": (row.get("lugar_nombre") or "").strip() or "Sin lugar",
        "direccion_fisica": (row.get("direccion_fisica") or "").strip() or None,
        "coordenadas_json": coordenadas_json,
        "organizador_nombre": (row.get("organizador_nombre") or "").strip() or None,
        "idioma_origen": row.get("idioma_origen") or "ca",
        "titulo_ca": titulo_ca,
        "titulo_es": titulo_es,
        "desc_larga_ca": row.get("descripcion_larga") or "",
        "desc_larga_es": row.get("desc_larga_es") or "",
        "tags_cat": tags_ca_json,
        "tags_es": tags_es_json,
        "es_gratuito": int(row.get("es_gratuito") or 1),
        "precio_euros": precio,
        "requiere_inscripcion": int(row.get("requiere_inscripcion") or 0),
        "link_inscripcion": (row.get("link_inscripcion") or "").strip() or None,
    }
    with conn.cursor() as cur:
        cur.execute(sql, params)
        return cur.rowcount


# ============================================================================
# EVENTO_HORARIOS (delete + insert para idempotencia)
# ============================================================================

def replace_horarios(conn, row: dict):
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM EVENTO_HORARIOS WHERE ID_Unico_Evento=%s",
            (row["id_unico_evento"],),
        )
        cur.execute("""
            INSERT INTO EVENTO_HORARIOS
                (ID_Unico_Evento, Fecha_Inicio, Fecha_Fin, Hora_Inicio, Hora_Fin, Es_Recurrente)
            VALUES (%s, %s, %s, %s, %s, 0)
        """, (
            row["id_unico_evento"],
            row["fecha_inicio"],
            (row.get("fecha_fin") or None),
            (row.get("hora_inicio") or None),
            (row.get("hora_fin") or None),
        ))


# ============================================================================
# EVENTO_CATEGORIAS
# ============================================================================

def upsert_categorias(conn, id_evento: str, cat_codes: list, cat_principal_code: str,
                      cat_map: dict):
    """Inserta las categorías del evento. Limpia primero las viejas para que
    si cambian las categorías al re-procesar, no se queden zombies."""
    with conn.cursor() as cur:
        cur.execute(
            "DELETE FROM EVENTO_CATEGORIAS WHERE ID_Unico_Evento=%s",
            (id_evento,),
        )
        # Sin columna Es_Principal en esquema: insertar la principal primero por convención.
        codes = list(cat_codes)
        if cat_principal_code in codes:
            codes = [cat_principal_code] + [c for c in codes if c != cat_principal_code]
        for code in codes:
            cat_id = cat_map.get(code)
            if not cat_id:
                log.warning(f"    Categoría '{code}' no existe en BD, omitida")
                continue
            cur.execute("""
                INSERT INTO EVENTO_CATEGORIAS
                    (ID_Unico_Evento, ID_Categoria)
                VALUES (%s, %s)
            """, (id_evento, cat_id))


# ============================================================================
# IMÁGENES
# ============================================================================

def determinar_orientacion(width: int, height: int) -> str:
    if height == 0:
        return "horizontal"
    ratio = width / height
    if ratio > RATIO_HORIZONTAL_MIN:
        return "horizontal"
    elif ratio < RATIO_VERTICAL_MAX:
        return "vertical"
    else:
        return "cuadrada"


def imagen_existe_en_bd(conn, id_evento: str, url_externa: str) -> bool:
    with conn.cursor() as cur:
        cur.execute("""
            SELECT 1 FROM BINARIOS_STORAGE
            WHERE ID_Unico_Evento=%s AND URL_Original_Externa=%s
            LIMIT 1
        """, (id_evento, url_externa))
        return cur.fetchone() is not None


def descargar_y_almacenar_imagen(conn, http_client: httpx.Client, id_evento: str,
                                  url: str, orden: int, es_principal: bool) -> bool:
    """Descarga, valida y persiste una imagen. Devuelve True si nueva, False si ya estaba."""

    if imagen_existe_en_bd(conn, id_evento, url):
        log.info(f"    Ya en BD: {url[:80]}")
        return False

    # Descarga
    response = http_client.get(url, follow_redirects=True)
    response.raise_for_status()
    content = response.content

    if len(content) > MAX_IMAGE_SIZE_BYTES:
        raise ValueError(f"Imagen demasiado grande ({len(content)} bytes)")
    if len(content) < 100:
        raise ValueError(f"Imagen sospechosamente pequeña ({len(content)} bytes), probablemente error HTTP")

    # Validar que es imagen real (no HTML 404, no error genérico)
    pil_img = Image.open(io.BytesIO(content))
    pil_img.verify()
    pil_img = Image.open(io.BytesIO(content))  # reabrir tras verify
    width, height = pil_img.size
    fmt = (pil_img.format or "").upper()

    # Determinar extensión y tipo (mapeo a los ENUMs del schema BINARIOS_STORAGE)
    ext_map = {"JPEG": "jpg", "PNG": "png", "WEBP": "webp", "GIF": "gif"}
    tipo_map = {"JPEG": "JPG", "PNG": "PNG", "WEBP": "WEBP"}
    ext = ext_map.get(fmt, "jpg")
    tipo_archivo = tipo_map.get(fmt, "JPG")

    # Calcular checksum
    checksum = hashlib.sha256(content).hexdigest()

    # Determinar orientación
    orientacion = determinar_orientacion(width, height)

    # Guardar en disco
    event_dir = IMAGES_DIR / id_evento
    event_dir.mkdir(parents=True, exist_ok=True)
    filename = f"{orden:02d}_{checksum[:12]}.{ext}"
    filepath = event_dir / filename
    filepath.write_bytes(content)

    # URL relativa para servir desde FastAPI (asumiendo que static/ se monta en /static/)
    local_url = f"/static/images/{id_evento}/{filename}"

    # INSERT en BINARIOS_STORAGE
    sql = """
    INSERT INTO BINARIOS_STORAGE (
        ID_Unico_Evento, Nombre_Archivo, Tipo_Archivo,
        URL_Almacenamiento_Nube, Es_Principal, Orden,
        Ancho_Px, Alto_Px, Orientacion, URL_Original_Externa,
        Checksum_SHA256
    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
    """
    with conn.cursor() as cur:
        cur.execute(sql, (
            id_evento, filename, tipo_archivo, local_url,
            1 if es_principal else 0, orden, width, height, orientacion,
            url, checksum,
        ))

    log.info(f"    Descargada: {orientacion} {width}x{height} ({tipo_archivo}) → {filename}")
    return True


def update_imagen_principal_cache(conn, id_evento: str):
    """Actualiza EVENTOS_MASTER.Imagen_Principal_URL con la URL de la imagen
    marcada como principal en BINARIOS_STORAGE. Si no hay, deja NULL."""
    with conn.cursor() as cur:
        cur.execute("""
            SELECT URL_Almacenamiento_Nube FROM BINARIOS_STORAGE
            WHERE ID_Unico_Evento=%s AND Es_Principal=1
            ORDER BY ID_Binario ASC
            LIMIT 1
        """, (id_evento,))
        r = cur.fetchone()
        url = r["URL_Almacenamiento_Nube"] if r else None
        cur.execute(
            "UPDATE EVENTOS_MASTER SET Imagen_Principal_URL=%s WHERE ID_Unico_Evento=%s",
            (url, id_evento),
        )


# ============================================================================
# PIPELINE POR EVENTO
# ============================================================================

def parse_imagenes(row: dict) -> list:
    """Lee el campo imagenes_urls (JSON array) y devuelve lista. Con fallback
    al campo legacy imagen_principal_url para CSVs antiguos."""
    raw = (row.get("imagenes_urls") or "").strip()
    if raw:
        try:
            data = json.loads(raw)
            if isinstance(data, list):
                return [u for u in data if u]
        except json.JSONDecodeError:
            # Compat: si raw es una URL pelada (no JSON)
            if raw.startswith("http"):
                return [raw]
    # Fallback campo viejo
    legacy = (row.get("imagen_principal_url") or "").strip()
    if legacy:
        return [legacy]
    return []


def process_event(conn, http_client: httpx.Client, row: dict,
                  cat_map: dict, cp_map: dict, stats: dict):
    titulo_short = (row.get("titulo") or "")[:60]

    # Validación: fecha de inicio es obligatoria
    if not (row.get("fecha_inicio") or "").strip():
        log.warning(f"  SIN FECHA, descartado: {titulo_short}")
        stats["skipped_no_date"] += 1
        return

    # Resolver coordenadas: si no vienen explícitas, derivar del centroide del CP
    coords_json = (row.get("coordenadas_json") or "").strip() or None
    if not coords_json:
        cp = row.get("cp_evento")
        if cp and cp in cp_map:
            coords_json = json.dumps(cp_map[cp])

    # Resolver categorías
    cat_principal_code = (row.get("categoria_principal") or "").strip()
    try:
        cat_codes = json.loads(row.get("categorias_codigos") or "[]")
    except json.JSONDecodeError:
        cat_codes = []
    if cat_principal_code and cat_principal_code not in cat_codes:
        cat_codes.insert(0, cat_principal_code)

    ensure_geografia(conn, row, cp_map)

    # 1) UPSERT evento
    rowcount = upsert_evento_master(conn, row, coords_json)
    if rowcount == 1:
        stats["events_inserted"] += 1
        log.info(f"  Insertado en EVENTOS_MASTER")
    elif rowcount == 2:
        stats["events_updated"] += 1
        log.info(f"  Actualizado en EVENTOS_MASTER")
    # rowcount == 0 significa que ya existía con los mismos valores, no contamos

    # 2) Horarios (delete + insert)
    replace_horarios(conn, row)

    # 3) Categorías (delete + insert)
    upsert_categorias(conn, row["id_unico_evento"], cat_codes, cat_principal_code, cat_map)

    # 4) Imágenes
    imagenes = parse_imagenes(row)
    if not imagenes:
        log.info(f"  Sin imágenes")
    else:
        log.info(f"  {len(imagenes)} imagen(es) a procesar")
        for idx, img_url in enumerate(imagenes):
            try:
                if descargar_y_almacenar_imagen(
                    conn, http_client, row["id_unico_evento"], img_url,
                    orden=idx, es_principal=(idx == 0),
                ):
                    stats["images_downloaded"] += 1
            except httpx.HTTPError as e:
                log.error(f"    HTTP error en {img_url}: {e}")
                stats["images_failed"] += 1
            except Exception as e:
                log.error(f"    Error en {img_url}: {e}")
                stats["images_failed"] += 1

    # 5) Cache de Imagen_Principal_URL en EVENTOS_MASTER
    update_imagen_principal_cache(conn, row["id_unico_evento"])


# ============================================================================
# PIPELINE PRINCIPAL
# ============================================================================

def process_csv(input_path: Path):
    if not input_path.exists():
        sys.exit(f"CSV no encontrado: {input_path}")

    conn = get_connection()
    http_client = httpx.Client(
        timeout=HTTP_TIMEOUT,
        headers={"User-Agent": HTTP_USER_AGENT},
    )

    try:
        log.info("Cargando catálogos desde BD...")
        cat_map = load_categorias_map(conn)
        cp_map = load_cps_map(conn)
        log.info(f"  Categorías cargadas: {len(cat_map)}")
        log.info(f"  CPs cargados: {len(cp_map)}")

        if not cat_map:
            sys.exit("ERROR: tabla CATEGORIAS vacía. Ejecuta categorias_jerarquia.sql primero.")

        with input_path.open("r", encoding="utf-8", newline="") as f:
            rows = list(csv.DictReader(f))
        log.info(f"Filas en CSV: {len(rows)}")

        stats = {
            "events_inserted": 0,
            "events_updated": 0,
            "skipped_no_date": 0,
            "errors": 0,
            "images_downloaded": 0,
            "images_failed": 0,
        }

        for i, row in enumerate(rows, 1):
            titulo_short = (row.get("titulo") or "")[:60]
            log.info(f"[{i}/{len(rows)}] {titulo_short}")
            try:
                process_event(conn, http_client, row, cat_map, cp_map, stats)
                conn.commit()
            except Exception as e:
                log.error(f"  ERROR procesando evento: {e}", exc_info=True)
                conn.rollback()
                stats["errors"] += 1

        log.info("=== Reporte ===")
        log.info(f"  Eventos insertados:        {stats['events_inserted']}")
        log.info(f"  Eventos actualizados:      {stats['events_updated']}")
        log.info(f"  Descartados sin fecha:     {stats['skipped_no_date']}")
        log.info(f"  Errores procesando evento: {stats['errors']}")
        log.info(f"  Imágenes descargadas:      {stats['images_downloaded']}")
        log.info(f"  Imágenes fallidas:         {stats['images_failed']}")

    finally:
        http_client.close()
        conn.close()


def main():
    parser = argparse.ArgumentParser(
        description="Fase C — Persistencia en BD de eventos enriquecidos."
    )
    parser.add_argument("--input", required=True,
                        help="CSV producido por enrich_phase_b.py")
    args = parser.parse_args()

    process_csv(Path(args.input))


if __name__ == "__main__":
    main()
