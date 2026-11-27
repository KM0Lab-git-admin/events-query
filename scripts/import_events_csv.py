"""
Importa eventos desde CSV (p. ej. out/malgrat_events.csv) a EVENTOS_MASTER + EVENTO_HORARIOS,
resolviendo RECINTOS por nombre canónico o dirección dentro de la ciudad.

Uso (desde la raíz del repo, con venv activo):
  python scripts/import_events_csv.py --csv out/malgrat_events.csv
  python scripts/import_events_csv.py --csv out/malgrat_events.csv --dry-run

Requiere esquema con RECINTOS / ID_Recinto (p. ej. SQL/SCHEMA_SQL_FINAL.sql o init Docker con scripts/schema.sql).
"""

from __future__ import annotations

import argparse
import asyncio
import csv
import logging
import re
import sys
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import TYPE_CHECKING, Any, Optional

from pymysql.err import IntegrityError

ROOT = Path(__file__).resolve().parent.parent
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.ingestion.persister import ensure_geography  # noqa: E402
from app.services.database import db_service  # noqa: E402

if TYPE_CHECKING:
    from app.services.database import DatabaseService

logger = logging.getLogger(__name__)

DEFAULT_LAT = 41.64
DEFAULT_LNG = 2.74


def normalize_alias(text: str) -> str:
    if not text:
        return ""
    s = text.strip()
    s = s.replace("\u201c", '"').replace("\u201d", '"').replace("\u00ab", '"').replace("\u00bb", '"')
    s = s.replace("'", "'")
    s = re.sub(r"\s+", " ", s)
    return s.lower()


def infer_tipo(lugar: str) -> str:
    t = normalize_alias(lugar)
    if "biblioteca" in t:
        return "BIBLIOTECA"
    if "centre cultural" in t or "centro cultural" in t:
        return "CENTRO_CULTURAL"
    if "teatre" in t or "teatro" in t:
        return "TEATRO"
    if "parc" in t or "parque" in t or "parcs" in t:
        return "PARQUE"
    return "OTRO"


def clean_display_name(lugar: str) -> str:
    s = (lugar or "").strip()
    s = s.replace("\u201c", '"').replace("\u201d", '"')
    return s[:255] if len(s) > 255 else s


def parse_bool(s: str) -> bool:
    return str(s).strip() in ("1", "true", "True", "yes", "si", "sí")


def parse_optional_decimal(s: str) -> Optional[Decimal]:
    t = (s or "").strip()
    if not t:
        return None
    try:
        return Decimal(t.replace(",", "."))
    except InvalidOperation:
        return None


def parse_time(s: str) -> Optional[str]:
    t = (s or "").strip()
    if not t:
        return None
    if re.match(r"^\d{1,2}:\d{2}$", t):
        parts = t.split(":")
        return f"{int(parts[0]):02d}:{parts[1]}:00"
    if re.match(r"^\d{1,2}:\d{2}:\d{2}$", t):
        return t
    return None


def parse_date(s: str) -> Optional[str]:
    t = (s or "").strip()
    return t if t else None


def titles_and_descs(idioma: str, titulo: str, desc: str) -> tuple[str, str, Optional[str], Optional[str]]:
    titulo = (titulo or "").strip()[:255] or "Sense títol"
    desc = (desc or "").strip() or None
    il = (idioma or "ca")[:2].lower()
    if il == "ca":
        return titulo, titulo if titulo != "Sense títol" else "Sin título", desc, desc
    return titulo, titulo, desc, desc


async def _lookup_by_address(
    db, id_ciudad: int, cp: str, direccion: Optional[str]
) -> Optional[int]:
    if not direccion or not direccion.strip():
        return None
    rows = await db.execute_query(
        """
        SELECT ID_Recinto FROM RECINTOS
        WHERE ID_Ciudad = %s AND CP = %s AND Direccion_Fisica = %s LIMIT 1
        """,
        (id_ciudad, cp, direccion.strip()[:255]),
        fetch_one=True,
    )
    if not rows:
        return None
    return int(rows[0]["ID_Recinto"])


async def _lookup_by_canonical_name(
    db, id_ciudad: int, nombre: str
) -> Optional[int]:
    nombre = clean_display_name(nombre)
    if not nombre:
        return None
    rows = await db.execute_query(
        """
        SELECT ID_Recinto FROM RECINTOS
        WHERE ID_Ciudad = %s AND Nombre_Canonico = %s LIMIT 1
        """,
        (id_ciudad, nombre),
        fetch_one=True,
    )
    if not rows:
        return None
    return int(rows[0]["ID_Recinto"])


async def _fetch_recinto(db, id_r: int) -> dict[str, Any]:
    rows = await db.execute_query(
        """
        SELECT ID_Recinto, Nombre_Canonico, Direccion_Fisica, Tipo
        FROM RECINTOS WHERE ID_Recinto = %s LIMIT 1
        """,
        (id_r,),
        fetch_one=True,
    )
    return rows[0] if rows else {}


async def resolve_recinto(
    db,
    *,
    id_ciudad: int,
    cp: str,
    lugar_nombre: str,
    direccion_fisica: str,
    dry_run: bool,
) -> tuple[Optional[int], str, Optional[str]]:
    """
    Devuelve (ID_Recinto|None, Lugar_Nombre para evento, Direccion_Fisica para evento).
    """
    d = (direccion_fisica or "").strip() or None
    if d:
        d = d[:255]

    id_r = None if dry_run else await _lookup_by_address(db, id_ciudad, cp, d)
    if id_r is None and not dry_run:
        id_r = await _lookup_by_canonical_name(db, id_ciudad, clean_display_name(lugar_nombre))

    if id_r is not None:
        row = await _fetch_recinto(db, id_r) if not dry_run else {}
        if row:
            lugar = str(row.get("Nombre_Canonico") or clean_display_name(lugar_nombre))
            dir_ev = row.get("Direccion_Fisica") or d
        else:
            lugar = clean_display_name(lugar_nombre)
            dir_ev = d
        return id_r, lugar, str(dir_ev)[:255] if dir_ev else None

    if dry_run:
        return None, clean_display_name(lugar_nombre), d

    tipo = infer_tipo(lugar_nombre)
    canon = clean_display_name(lugar_nombre)
    try:
        id_r = await db.execute_insert(
            """
            INSERT INTO RECINTOS (
                ID_Ciudad, CP, Nombre_Canonico, Tipo, Direccion_Fisica, Fuente_Datos
            ) VALUES (%s, %s, %s, %s, %s, 'import_csv')
            """,
            (id_ciudad, cp, canon, tipo, d),
        )
    except IntegrityError:
        id_r = await _lookup_by_address(db, id_ciudad, cp, d)
        if id_r is None:
            id_r = await _lookup_by_canonical_name(db, id_ciudad, canon)
        if id_r is None:
            raise
    row = await _fetch_recinto(db, id_r)
    lugar_out = str(row.get("Nombre_Canonico") or canon)
    dir_out = row.get("Direccion_Fisica") or d
    return id_r, lugar_out[:255], str(dir_out)[:255] if dir_out else None


async def import_row(db: "DatabaseService", row: dict[str, str], dry_run: bool) -> None:
    id_ciudad = int(row.get("id_ciudad") or 0)
    cp = (row.get("cp_evento") or "").strip()[:5]
    poblacion = (row.get("nombre_ciudad") or "").strip() or "—"
    lugar_raw = row.get("lugar_nombre") or ""
    dir_raw = row.get("direccion_fisica") or ""

    if dry_run:
        id_recinto, lugar_nombre, direccion = await resolve_recinto(
            db,
            id_ciudad=id_ciudad,
            cp=cp,
            lugar_nombre=lugar_raw,
            direccion_fisica=dir_raw,
            dry_run=True,
        )
    else:
        coords = await db.get_coordenadas_cp(cp)
        lat = float(coords["lat"]) if coords and coords.get("lat") is not None else DEFAULT_LAT
        lng = float(coords["lng"]) if coords and coords.get("lng") is not None else DEFAULT_LNG

        await ensure_geography(
            db,
            id_ciudad=id_ciudad,
            cp=cp,
            nombre_ciudad=poblacion,
            lat=lat,
            lng=lng,
        )

        id_recinto, lugar_nombre, direccion = await resolve_recinto(
            db,
            id_ciudad=id_ciudad,
            cp=cp,
            lugar_nombre=lugar_raw,
            direccion_fisica=dir_raw,
            dry_run=False,
        )

    id_unico = (row.get("id_unico_evento") or "").strip()
    if not id_unico or len(id_unico) != 64:
        raise ValueError(f"ID_Unico_Evento inválido en fila: {id_unico!r}")

    titulo_cat, titulo_es, desc_cat, desc_es = titles_and_descs(
        row.get("idioma_origen") or "ca",
        row.get("titulo") or "",
        row.get("descripcion_larga") or "",
    )

    es_gratuito = 1 if parse_bool(row.get("es_gratuito") or "1") else 0
    requiere_ins = 1 if parse_bool(row.get("requiere_inscripcion") or "0") else 0
    precio = parse_optional_decimal(row.get("precio_euros") or "")

    fecha_inicio = parse_date(row.get("fecha_inicio") or "")
    if not fecha_inicio:
        raise ValueError("fecha_inicio obligatoria")
    fecha_fin = parse_date(row.get("fecha_fin") or "")
    hora_ini = parse_time(row.get("hora_inicio") or "")
    hora_fin = parse_time(row.get("hora_fin") or "")

    if dry_run:
        logger.info(
            "dry-run: %s | recinto=%s lugar=%s",
            id_unico[:12],
            id_recinto,
            lugar_nombre,
        )
        return

    await db.execute_query(
        """
        INSERT INTO EVENTOS_MASTER (
            ID_Unico_Evento, Metodo_Ingesta, ID_Usuario_Carga, Fuente_ID,
            Fuente_URL_Original, Estado,
            ID_Ciudad, ID_Recinto, CP_Evento, Poblacion_Nombre, Lugar_Nombre, Direccion_Fisica,
            Idioma_Origen, Titulo_CAT, Titulo_ES, Desc_Larga_CAT, Desc_Larga_ES,
            Es_Gratuito, Precio_Euros, Requiere_Inscripcion,
            Organizador_Nombre, Link_Entradas_Inscripcion, Imagen_Principal_URL,
            Es_Patrocinado
        ) VALUES (
            %s, %s, %s, %s,
            %s, %s,
            %s, %s, %s, %s, %s, %s,
            %s, %s, %s, %s, %s,
            %s, %s, %s,
            %s, %s, %s,
            0
        )
        ON DUPLICATE KEY UPDATE
            Titulo_ES = VALUES(Titulo_ES),
            Titulo_CAT = VALUES(Titulo_CAT),
            Desc_Larga_ES = VALUES(Desc_Larga_ES),
            Desc_Larga_CAT = VALUES(Desc_Larga_CAT),
            Lugar_Nombre = VALUES(Lugar_Nombre),
            Direccion_Fisica = VALUES(Direccion_Fisica),
            Fuente_URL_Original = VALUES(Fuente_URL_Original),
            CP_Evento = VALUES(CP_Evento),
            ID_Ciudad = VALUES(ID_Ciudad),
            ID_Recinto = VALUES(ID_Recinto),
            Precio_Euros = VALUES(Precio_Euros),
            Organizador_Nombre = VALUES(Organizador_Nombre),
            Link_Entradas_Inscripcion = VALUES(Link_Entradas_Inscripcion),
            Imagen_Principal_URL = VALUES(Imagen_Principal_URL)
        """,
        (
            id_unico,
            (row.get("metodo_ingesta") or "SCRAPING").strip()[:16],
            (row.get("id_usuario_carga") or "csv_import").strip()[:255],
            (row.get("fuente_id") or "URL_ESTRUCTURAL").strip(),
            (row.get("fuente_url_original") or "")[:2048] or None,
            (row.get("estado") or "ACTIVO").strip(),
            id_ciudad,
            id_recinto,
            cp,
            poblacion[:255],
            lugar_nombre[:255],
            direccion[:255] if direccion else None,
            (row.get("idioma_origen") or "ca")[:2],
            titulo_cat,
            titulo_es,
            desc_cat,
            desc_es,
            es_gratuito,
            precio,
            requiere_ins,
            (row.get("organizador_nombre") or "").strip()[:255] or None,
            (row.get("link_inscripcion") or "").strip()[:2048] or None,
            (row.get("imagen_principal_url") or "").strip()[:2048] or None,
        ),
        fetch_one=False,
        fetch_all=False,
    )

    await db.execute_query(
        "DELETE FROM EVENTO_HORARIOS WHERE ID_Unico_Evento = %s",
        (id_unico,),
        fetch_one=False,
        fetch_all=False,
    )
    await db.execute_query(
        """
        INSERT INTO EVENTO_HORARIOS (
            ID_Unico_Evento, Fecha_Inicio, Fecha_Fin, Hora_Inicio, Hora_Fin,
            Es_Recurrente, Horario_Texto_ES
        ) VALUES (%s, %s, %s, %s, %s, 0, NULL)
        """,
        (id_unico, fecha_inicio, fecha_fin, hora_ini, hora_fin),
        fetch_one=False,
        fetch_all=False,
    )


async def run(csv_path: Path, dry_run: bool) -> int:
    if not csv_path.is_file():
        logger.error("No existe el CSV: %s", csv_path)
        return 1

    rows: list[dict[str, str]] = []
    with csv_path.open(encoding="utf-8", newline="") as f:
        reader = csv.DictReader(f)
        for raw in reader:
            rows.append({k.strip().lower(): (v or "").strip() for k, v in raw.items() if k})

    if dry_run:
        for r in rows:
            await import_row(db_service, r, dry_run=True)
        logger.info("dry-run: %s filas", len(rows))
        return 0

    await db_service.connect()
    try:
        n = 0
        for r in rows:
            await import_row(db_service, r, dry_run=False)
            n += 1
        logger.info("Importadas %s filas desde %s", n, csv_path)
    finally:
        await db_service.disconnect()
    return 0


def main() -> None:
    logging.basicConfig(level=logging.INFO, format="%(levelname)s %(message)s")
    p = argparse.ArgumentParser(description="Importar eventos desde CSV con RECINTOS.")
    p.add_argument("--csv", type=Path, required=True, help="Ruta al CSV")
    p.add_argument("--dry-run", action="store_true", help="Solo validar y loguear")
    args = p.parse_args()
    code = asyncio.run(run(args.csv, args.dry_run))
    raise SystemExit(code)


if __name__ == "__main__":
    main()
