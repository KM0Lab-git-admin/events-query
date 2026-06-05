"""
Carga de imágenes desde BINARIOS_STORAGE para respuestas API.
Compatible con esquema base o con columnas extra (images_delta.sql).
"""

from __future__ import annotations

import logging
from typing import Any, Dict, List, Optional

import aiomysql
from pymysql.err import OperationalError

logger = logging.getLogger(__name__)


def _row_event_id(row: Dict[str, Any]) -> Optional[str]:
    return row.get("ID_Unico_Evento") or row.get("id_unico_evento")


def _norm_row_full(row: Dict[str, Any]) -> Dict[str, Any]:
    return {
        "url": row.get("URL_Almacenamiento_Nube") or row.get("url_almacenamiento_nube"),
        "nombre_archivo": row.get("Nombre_Archivo") or row.get("nombre_archivo"),
        "tipo_archivo": row.get("Tipo_Archivo") or row.get("tipo_archivo"),
        "es_principal": bool(row.get("Es_Principal") or row.get("es_principal")),
        "orden": int(row.get("Orden") if row.get("Orden") is not None else row.get("orden") or 0),
        "ancho_px": row.get("Ancho_Px") if row.get("Ancho_Px") is not None else row.get("ancho_px"),
        "alto_px": row.get("Alto_Px") if row.get("Alto_Px") is not None else row.get("alto_px"),
        "orientacion": row.get("Orientacion") or row.get("orientacion"),
        "url_original_externa": row.get("URL_Original_Externa") or row.get("url_original_externa"),
    }


def _norm_row_min(row: Dict[str, Any], idx: int) -> Dict[str, Any]:
    bid = row.get("ID_Binario") or row.get("id_binario") or idx
    return {
        "url": row.get("URL_Almacenamiento_Nube"),
        "nombre_archivo": row.get("Nombre_Archivo"),
        "tipo_archivo": row.get("Tipo_Archivo"),
        "es_principal": idx == 0,
        "orden": int(bid) if bid is not None else idx,
        "ancho_px": None,
        "alto_px": None,
        "orientacion": None,
        "url_original_externa": None,
    }


async def fetch_imagenes_por_eventos(
    conn, event_ids: List[str]
) -> Dict[str, List[Dict[str, Any]]]:
    """
    Devuelve mapa ID_Unico_Evento -> lista de dicts imagen (ordenadas).
    Usa DictCursor en el caller o pasa cursor aiomysql.DictCursor.
    """
    result: Dict[str, List[Dict[str, Any]]] = {}
    if not event_ids:
        return result

    unique_ids = list(dict.fromkeys(event_ids))
    placeholders = ",".join(["%s"] * len(unique_ids))
    sql_full = f"""
        SELECT
            ID_Unico_Evento,
            URL_Almacenamiento_Nube,
            Nombre_Archivo,
            Tipo_Archivo,
            Es_Principal,
            Orden,
            Ancho_Px,
            Alto_Px,
            Orientacion,
            URL_Original_Externa,
            ID_Binario
        FROM BINARIOS_STORAGE
        WHERE ID_Unico_Evento IN ({placeholders})
        ORDER BY
            ID_Unico_Evento,
            COALESCE(Es_Principal, 0) DESC,
            COALESCE(Orden, ID_Binario) ASC,
            ID_Binario ASC
    """
    sql_min = f"""
        SELECT
            ID_Unico_Evento,
            URL_Almacenamiento_Nube,
            Nombre_Archivo,
            Tipo_Archivo,
            ID_Binario
        FROM BINARIOS_STORAGE
        WHERE ID_Unico_Evento IN ({placeholders})
        ORDER BY ID_Unico_Evento, ID_Binario ASC
    """

    async with conn.cursor(aiomysql.DictCursor) as cursor:
        try:
            await cursor.execute(sql_full, tuple(unique_ids))
            rows = await cursor.fetchall() or []
            for row in rows:
                eid = _row_event_id(row)
                if not eid:
                    continue
                result.setdefault(eid, []).append(_norm_row_full(row))
        except OperationalError as e:
            if "Unknown column" not in str(e):
                raise
            logger.debug("BINARIOS_STORAGE sin columnas extendidas; usando consulta mínima")
            await cursor.execute(sql_min, tuple(unique_ids))
            rows = await cursor.fetchall() or []
            seen_eid: set = set()
            for row in rows:
                eid = _row_event_id(row)
                if not eid:
                    continue
                lst = result.setdefault(eid, [])
                d = _norm_row_min(row, len(lst))
                d["es_principal"] = eid not in seen_eid
                seen_eid.add(eid)
                lst.append(d)

    return result


def merge_imagenes_en_eventos(
    eventos: List[Dict[str, Any]],
    img_map: Dict[str, List[Dict[str, Any]]],
    id_key: str = "id",
) -> None:
    """Adjunta clave imagenes[] in-place."""
    for ev in eventos:
        eid = ev.get(id_key)
        if not eid:
            continue
        ev["imagenes"] = img_map.get(eid, [])
