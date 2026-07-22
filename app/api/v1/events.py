"""
Events endpoints - List, filter, and retrieve events.
"""

import json
import logging
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

import aiomysql
from fastapi import APIRouter, HTTPException, Path, Query, Request, status
from fastapi.responses import ORJSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.models.schemas import ErrorResponse
from app.services import db_service
from app.services.event_binarios import fetch_imagenes_por_eventos, merge_imagenes_en_eventos

logger = logging.getLogger(__name__)

# Rate limiter
limiter = Limiter(key_func=get_remote_address)

# Router
router = APIRouter()

# Supported postal codes
POBLACIONES_SOPORTADAS_CP = ("08380", "17300")


async def _attach_imagenes(conn: Any, eventos: List[Dict[str, Any]]) -> None:
    ids = [e["id"] for e in eventos if e.get("id")]
    img_map = await fetch_imagenes_por_eventos(conn, ids) if ids else {}
    merge_imagenes_en_eventos(eventos, img_map)


def _tags_from_db(val: Any) -> List[Any]:
    if val is None:
        return []
    if isinstance(val, (list, tuple)):
        return list(val)
    if isinstance(val, str):
        try:
            return json.loads(val) if val.strip() else []
        except (ValueError, TypeError):
            return []
    return []


def _coordenadas_from_db(val: Any) -> Optional[Dict[str, Any]]:
    if val is None:
        return None
    if isinstance(val, dict):
        return val
    if isinstance(val, (bytes, bytearray)):
        try:
            parsed = json.loads(val.decode())
            return parsed if isinstance(parsed, dict) else None
        except (ValueError, TypeError, UnicodeDecodeError):
            return None
    if isinstance(val, str):
        try:
            parsed = json.loads(val)
            return parsed if isinstance(parsed, dict) else None
        except (ValueError, TypeError):
            return None
    return None


@router.get(
    "/events",
    response_class=ORJSONResponse,
    summary="List events with filters and pagination",
    description="Get a paginated list of events with optional filters",
    responses={
        200: {
            "description": "Events retrieved successfully",
            "content": {
                "application/json": {
                    "example": {
                        "data": [
                            {
                                "id": "evt_123",
                                "titulo_es": "Concierto de Jazz",
                                "poblacion": "Malgrat de Mar",
                                "fecha_inicio": "2026-02-07",
                                "es_gratuito": True,
                                "categorias": ["musica"],
                                "imagen_url": "https://example.com/a.jpg",
                                "fuente_url_original": "https://t.me/AjuntamentdeMalgrat/3838",
                                "imagenes": [],
                            }
                        ],
                        "total": 150,
                        "page": 1,
                        "page_size": 20,
                        "total_pages": 8,
                    }
                }
            },
        },
        400: {"model": ErrorResponse, "description": "Invalid parameters"},
        429: {"description": "Too many requests - Rate limit exceeded"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
@limiter.limit("100/minute")
async def list_events(
    request: Request,
    page: int = Query(1, ge=1, description="Page number (starts at 1)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page (max 100)"),
    poblacion: Optional[str] = Query(
        None, description="Filter by town name (e.g., 'Malgrat de Mar', 'Blanes')"
    ),
    categoria: Optional[str] = Query(
        None, description="Filter by category slug (e.g., 'cultura', 'deportes')"
    ),
    fecha_desde: Optional[date] = Query(
        None, description="Start date filter (YYYY-MM-DD), defaults to today"
    ),
    fecha_hasta: Optional[date] = Query(
        None, description="End date filter (YYYY-MM-DD), defaults to +30 days"
    ),
    es_gratuito: Optional[bool] = Query(None, description="Filter free events only"),
    search: Optional[str] = Query(None, description="Search in title and tags"),
) -> Dict[str, Any]:
    """
    List events with pagination and filters.
    """
    try:
        if fecha_desde is None:
            fecha_desde = date.today()
        if fecha_hasta is None:
            fecha_hasta = date.today() + timedelta(days=30)

        offset = (page - 1) * page_size

        where_clauses = ["em.Estado = 'ACTIVO'", "em.CP_Evento IN (%s, %s)"]
        params: List[Any] = list(POBLACIONES_SOPORTADAS_CP)

        where_clauses.append("eh.Fecha_Inicio >= %s")
        params.append(fecha_desde)
        where_clauses.append("eh.Fecha_Inicio <= %s")
        params.append(fecha_hasta)

        if poblacion:
            where_clauses.append("em.Poblacion_Nombre = %s")
            params.append(poblacion)

        if categoria:
            where_clauses.append("c.Slug = %s")
            params.append(categoria)

        if es_gratuito is not None:
            where_clauses.append("em.Es_Gratuito = %s")
            params.append(es_gratuito)

        if search:
            search_pattern = f"%{search}%"
            where_clauses.append(
                "(em.Titulo_ES LIKE %s OR em.Titulo_CAT LIKE %s OR "
                "CAST(em.Tags_ES AS CHAR) LIKE %s OR CAST(em.Tags_CAT AS CHAR) LIKE %s)"
            )
            params.extend([search_pattern, search_pattern, search_pattern, search_pattern])

        where_clause = " AND ".join(where_clauses)

        # AGRUPACIÓN POR FAMILIA: los eventos que cuelgan de un evento paraguas
        # (festival, fira, ciclo) comparten EVENTOS_MASTER.ID_Familia. La lista
        # devuelve UNA tarjeta por familia: la cabeza (el miembro con el rango
        # de fechas más amplio) con sus 'actividades' anidadas. Los eventos sin
        # familia son su propia tarjeta. La agrupación y paginación se hacen en
        # Python: el volumen actual (cientos de filas) lo permite de sobra; si
        # crece a miles, mover la agrupación a SQL con window functions.
        data_query = f"""
        SELECT
            em.ID_Unico_Evento AS id,
            COALESCE(em.ID_Familia, em.ID_Unico_Evento) AS familia,
            em.Titulo_ES AS titulo_es,
            em.Titulo_CAT AS titulo_cat,
            COALESCE(NULLIF(em.Desc_Corta_ES, ''),
                     LEFT(COALESCE(em.Desc_Larga_ES, ''), 400)) AS descripcion_corta_es,
            COALESCE(NULLIF(em.Desc_Corta_CAT, ''),
                     LEFT(COALESCE(em.Desc_Larga_CAT, ''), 400)) AS descripcion_corta_cat,
            em.CP_Evento AS cp,
            em.Poblacion_Nombre AS poblacion,
            em.Lugar_Nombre AS lugar,
            em.Es_Gratuito AS es_gratuito,
            em.Precio_Euros AS precio,
            em.Imagen_Principal_URL AS imagen_url,
            em.Fuente_URL_Original AS fuente_url_original,
            MIN(eh.Fecha_Inicio) AS fecha_inicio,
            MAX(COALESCE(eh.Fecha_Fin, eh.Fecha_Inicio)) AS fecha_fin,
            MIN(eh.Hora_Inicio) AS hora_inicio,
            GROUP_CONCAT(DISTINCT c.Slug ORDER BY c.Slug) AS categorias_slugs,
            GROUP_CONCAT(DISTINCT c.Nombre_ES ORDER BY c.Slug) AS categorias_es
        FROM EVENTOS_MASTER em
        LEFT JOIN EVENTO_HORARIOS eh ON em.ID_Unico_Evento = eh.ID_Unico_Evento
        LEFT JOIN EVENTO_CATEGORIAS ec ON em.ID_Unico_Evento = ec.ID_Unico_Evento
        LEFT JOIN CATEGORIAS c ON ec.ID_Categoria = c.ID_Categoria
        WHERE {where_clause}
        GROUP BY em.ID_Unico_Evento
        ORDER BY fecha_inicio ASC, em.Titulo_ES ASC
        """

        def _row_to_event(row: Dict[str, Any]) -> Dict[str, Any]:
            slug_blob = row.get("categorias_slugs") or ""
            cats = [s for s in slug_blob.split(",") if s] if slug_blob else []
            nombre_blob = row.get("categorias_es") or ""
            cats_nom = [s for s in nombre_blob.split(",") if s] if nombre_blob else []
            return {
                "id": row["id"],
                "titulo_es": row["titulo_es"],
                "titulo_cat": row["titulo_cat"],
                "descripcion_corta_es": row["descripcion_corta_es"],
                "descripcion_corta_cat": row["descripcion_corta_cat"],
                "cp": row["cp"],
                "poblacion": row["poblacion"],
                "lugar": row["lugar"],
                "es_gratuito": bool(row["es_gratuito"]),
                "precio": float(row["precio"]) if row.get("precio") is not None else None,
                "imagen_url": row.get("imagen_url"),
                "fuente_url_original": row.get("fuente_url_original"),
                "fecha_inicio": str(row["fecha_inicio"]) if row.get("fecha_inicio") else None,
                "fecha_fin": str(row["fecha_fin"]) if row.get("fecha_fin") else None,
                "hora_inicio": str(row["hora_inicio"]) if row.get("hora_inicio") else None,
                "categorias": cats,
                "categorias_nombres": cats_nom,
            }

        def _span_dias(row: Dict[str, Any]) -> int:
            if row.get("fecha_inicio") and row.get("fecha_fin"):
                try:
                    return (row["fecha_fin"] - row["fecha_inicio"]).days
                except TypeError:
                    return 0
            return 0

        async with db_service.get_connection() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cursor:
                await cursor.execute(data_query, params)
                rows = await cursor.fetchall() or []

                # Agrupar por familia conservando el orden por fecha
                familias: Dict[str, List[Dict[str, Any]]] = {}
                orden_familias: List[str] = []
                for row in rows:
                    key = row["familia"]
                    if key not in familias:
                        familias[key] = []
                        orden_familias.append(key)
                    familias[key].append(row)

                tarjetas = []
                for key in orden_familias:
                    miembros = familias[key]
                    # cabeza = rango de fechas más amplio; empate -> descripción más larga
                    cabeza_row = max(
                        miembros,
                        key=lambda r: (_span_dias(r),
                                       len(r.get("descripcion_corta_cat") or "")),
                    )
                    cabeza = _row_to_event(cabeza_row)
                    actividades = [
                        _row_to_event(r) for r in miembros if r["id"] != cabeza_row["id"]
                    ]
                    cabeza["es_familia"] = bool(actividades)
                    cabeza["actividades"] = actividades
                    tarjetas.append(cabeza)

                total = len(tarjetas)
                pagina = tarjetas[offset:offset + page_size]

                await _attach_imagenes(conn, pagina)

                total_pages = (total + page_size - 1) // page_size if page_size else 0

                return {
                    "data": pagina,
                    "total": total,
                    "page": page,
                    "page_size": page_size,
                    "total_pages": total_pages,
                    "has_next": page < total_pages,
                    "has_prev": page > 1,
                }

    except Exception as e:
        logger.error(f"Error listing events: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving events",
        )


@router.get(
    "/events/today",
    response_class=ORJSONResponse,
    summary="Get today's events",
    description="Retrieve events happening today (includes multi-day schedules overlapping today)",
    responses={
        200: {
            "description": "Today's events retrieved successfully",
            "content": {
                "application/json": {
                    "example": {
                        "data": [],
                        "total": 0,
                        "fecha": "2026-02-06",
                    }
                }
            },
        },
        429: {"description": "Too many requests - Rate limit exceeded"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
@limiter.limit("200/minute")
async def get_today_events(request: Request) -> Dict[str, Any]:
    try:
        today = date.today()

        query = """
        SELECT
            em.ID_Unico_Evento AS id,
            em.Titulo_ES AS titulo_es,
            em.Titulo_CAT AS titulo_cat,
            em.CP_Evento AS cp,
            em.Poblacion_Nombre AS poblacion,
            em.Lugar_Nombre AS lugar,
            em.Es_Gratuito AS es_gratuito,
            em.Precio_Euros AS precio,
            em.Imagen_Principal_URL AS imagen_url,
            em.Fuente_URL_Original AS fuente_url_original,
            MIN(eh.Hora_Inicio) AS hora_inicio,
            MAX(eh.Hora_Fin) AS hora_fin,
            GROUP_CONCAT(DISTINCT c.Slug ORDER BY c.Slug) AS categorias
        FROM EVENTOS_MASTER em
        JOIN EVENTO_HORARIOS eh ON em.ID_Unico_Evento = eh.ID_Unico_Evento
        LEFT JOIN EVENTO_CATEGORIAS ec ON em.ID_Unico_Evento = ec.ID_Unico_Evento
        LEFT JOIN CATEGORIAS c ON ec.ID_Categoria = c.ID_Categoria
        WHERE em.Estado = 'ACTIVO'
          AND em.CP_Evento IN (%s, %s)
          AND (%s BETWEEN eh.Fecha_Inicio AND COALESCE(eh.Fecha_Fin, eh.Fecha_Inicio))
        GROUP BY em.ID_Unico_Evento
        ORDER BY MIN(eh.Hora_Inicio) ASC, em.Titulo_ES ASC
        """

        async with db_service.get_connection() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cursor:
                await cursor.execute(query, (*POBLACIONES_SOPORTADAS_CP, today))
                rows = await cursor.fetchall() or []

                eventos = []
                for row in rows:
                    cat_blob = row.get("categorias") or ""
                    cats = [s for s in cat_blob.split(",") if s] if cat_blob else []
                    eventos.append(
                        {
                            "id": row["id"],
                            "titulo_es": row["titulo_es"],
                            "titulo_cat": row["titulo_cat"],
                            "cp": row["cp"],
                            "poblacion": row["poblacion"],
                            "lugar": row["lugar"],
                            "es_gratuito": bool(row["es_gratuito"]),
                            "precio": float(row["precio"]) if row.get("precio") is not None else None,
                            "imagen_url": row.get("imagen_url"),
                            "fuente_url_original": row.get("fuente_url_original"),
                            "hora_inicio": str(row["hora_inicio"]) if row.get("hora_inicio") else None,
                            "hora_fin": str(row["hora_fin"]) if row.get("hora_fin") else None,
                            "categorias": cats,
                        }
                    )

                await _attach_imagenes(conn, eventos)

                return {
                    "data": eventos,
                    "total": len(eventos),
                    "fecha": str(today),
                }

    except Exception as e:
        logger.error(f"Error getting today's events: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving today's events",
        )


@router.get(
    "/events/upcoming",
    response_class=ORJSONResponse,
    summary="Get upcoming events",
    description="Retrieve upcoming events (next N days after today)",
    responses={
        200: {
            "description": "Upcoming events retrieved successfully",
            "content": {
                "application/json": {
                    "example": {
                        "data": [],
                        "total": 0,
                        "fecha_desde": "2026-02-07",
                        "fecha_hasta": "2026-02-13",
                    }
                }
            },
        },
        429: {"description": "Too many requests - Rate limit exceeded"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
@limiter.limit("100/minute")
async def get_upcoming_events(
    request: Request,
    days: int = Query(7, ge=1, le=30, description="Number of days ahead (default 7, max 30)"),
) -> Dict[str, Any]:
    try:
        fecha_desde = date.today() + timedelta(days=1)
        fecha_hasta = date.today() + timedelta(days=days)

        query = """
        SELECT
            em.ID_Unico_Evento AS id,
            em.Titulo_ES AS titulo_es,
            em.Titulo_CAT AS titulo_cat,
            COALESCE(NULLIF(em.Desc_Corta_ES, ''),
                     LEFT(COALESCE(em.Desc_Larga_ES, ''), 400)) AS descripcion_corta_es,
            em.CP_Evento AS cp,
            em.Poblacion_Nombre AS poblacion,
            em.Lugar_Nombre AS lugar,
            em.Es_Gratuito AS es_gratuito,
            em.Precio_Euros AS precio,
            em.Imagen_Principal_URL AS imagen_url,
            em.Fuente_URL_Original AS fuente_url_original,
            MIN(eh.Fecha_Inicio) AS fecha_inicio,
            MIN(eh.Hora_Inicio) AS hora_inicio,
            GROUP_CONCAT(DISTINCT c.Slug ORDER BY c.Slug) AS categorias
        FROM EVENTOS_MASTER em
        JOIN EVENTO_HORARIOS eh ON em.ID_Unico_Evento = eh.ID_Unico_Evento
        LEFT JOIN EVENTO_CATEGORIAS ec ON em.ID_Unico_Evento = ec.ID_Unico_Evento
        LEFT JOIN CATEGORIAS c ON ec.ID_Categoria = c.ID_Categoria
        WHERE em.Estado = 'ACTIVO'
          AND em.CP_Evento IN (%s, %s)
          AND eh.Fecha_Inicio >= %s
          AND eh.Fecha_Inicio <= %s
        GROUP BY em.ID_Unico_Evento
        ORDER BY fecha_inicio ASC, hora_inicio ASC, em.Titulo_ES ASC
        LIMIT 100
        """

        async with db_service.get_connection() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cursor:
                await cursor.execute(query, (*POBLACIONES_SOPORTADAS_CP, fecha_desde, fecha_hasta))
                rows = await cursor.fetchall() or []

                eventos = []
                for row in rows:
                    cat_blob = row.get("categorias") or ""
                    cats = [s for s in cat_blob.split(",") if s] if cat_blob else []
                    eventos.append(
                        {
                            "id": row["id"],
                            "titulo_es": row["titulo_es"],
                            "titulo_cat": row["titulo_cat"],
                            "descripcion_corta_es": row["descripcion_corta_es"],
                            "cp": row["cp"],
                            "poblacion": row["poblacion"],
                            "lugar": row["lugar"],
                            "es_gratuito": bool(row["es_gratuito"]),
                            "precio": float(row["precio"]) if row.get("precio") is not None else None,
                            "imagen_url": row.get("imagen_url"),
                            "fuente_url_original": row.get("fuente_url_original"),
                            "fecha_inicio": str(row["fecha_inicio"]) if row.get("fecha_inicio") else None,
                            "hora_inicio": str(row["hora_inicio"]) if row.get("hora_inicio") else None,
                            "categorias": cats,
                        }
                    )

                await _attach_imagenes(conn, eventos)

                return {
                    "data": eventos,
                    "total": len(eventos),
                    "fecha_desde": str(fecha_desde),
                    "fecha_hasta": str(fecha_hasta),
                }

    except Exception as e:
        logger.error(f"Error getting upcoming events: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving upcoming events",
        )


@router.get(
    "/events/{event_id}",
    response_class=ORJSONResponse,
    summary="Get event details",
    description="Retrieve full details for a specific event by ID",
    responses={
        200: {
            "description": "Event details retrieved successfully",
            "content": {
                "application/json": {
                    "example": {
                        "id": "evt_123",
                        "titulo_es": "Concierto",
                        "coordenadas": {"lat": 41.65, "lng": 2.74},
                        "horarios": [],
                        "categorias": [],
                        "imagenes": [],
                    }
                }
            },
        },
        404: {"model": ErrorResponse, "description": "Event not found"},
        429: {"description": "Too many requests - Rate limit exceeded"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
@limiter.limit("100/minute")
async def get_event_details(
    request: Request,
    event_id: str = Path(..., description="Event unique ID"),
) -> Dict[str, Any]:
    try:
        event_query = """
        SELECT
            em.ID_Unico_Evento AS id,
            em.Titulo_ES AS titulo_es,
            em.Titulo_CAT AS titulo_cat,
            em.Desc_Larga_ES AS descripcion_larga_es,
            em.Desc_Larga_CAT AS descripcion_larga_cat,
            em.CP_Evento AS cp,
            em.Poblacion_Nombre AS poblacion,
            em.Lugar_Nombre AS lugar,
            em.Direccion_Fisica AS direccion,
            em.Coordenadas_JSON AS coordenadas_json,
            em.Tipo_Organizador AS tipo_organizador,
            em.Organizador_Nombre AS organizador,
            em.Organizador_Web AS organizador_web,
            em.Es_Gratuito AS es_gratuito,
            em.Precio_Euros AS precio,
            em.Imagen_Principal_URL AS imagen_url,
            em.Fuente_URL_Original AS fuente_url_original,
            em.Tags_ES AS tags_es,
            em.Tags_CAT AS tags_cat,
            em.Estado AS estado,
            em.Fecha_Creacion AS fecha_creacion,
            em.Link_Entradas_Inscripcion AS link_entradas_inscripcion,
            em.Requiere_Inscripcion AS requiere_inscripcion
        FROM EVENTOS_MASTER em
        WHERE em.ID_Unico_Evento = %s
        """

        schedules_query = """
        SELECT
            Fecha_Inicio AS fecha_inicio,
            Fecha_Fin AS fecha_fin,
            Hora_Inicio AS hora_inicio,
            Hora_Fin AS hora_fin,
            Es_Recurrente AS es_recurrente,
            Recurrencia_JSON AS recurrencia
        FROM EVENTO_HORARIOS
        WHERE ID_Unico_Evento = %s
        ORDER BY Fecha_Inicio ASC, Hora_Inicio ASC
        """

        categories_query = """
        SELECT
            c.ID_Categoria AS id,
            c.Slug AS slug,
            c.Nombre_ES AS nombre_es,
            c.Nombre_CAT AS nombre_cat,
            c.Color_Hex AS color_hex,
            c.Icono AS icono
        FROM EVENTO_CATEGORIAS ec
        JOIN CATEGORIAS c ON ec.ID_Categoria = c.ID_Categoria
        WHERE ec.ID_Unico_Evento = %s
        """

        async with db_service.get_connection() as conn:
            async with conn.cursor(aiomysql.DictCursor) as cursor:
                await cursor.execute(event_query, (event_id,))
                event_row = await cursor.fetchone()

                if not event_row:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"Event '{event_id}' not found",
                    )

                await cursor.execute(schedules_query, (event_id,))
                schedule_rows = await cursor.fetchall() or []

                await cursor.execute(categories_query, (event_id,))
                category_rows = await cursor.fetchall() or []

                tags_es = _tags_from_db(event_row.get("tags_es"))
                tags_cat = _tags_from_db(event_row.get("tags_cat"))

                event = {
                    "id": event_row["id"],
                    "titulo_es": event_row["titulo_es"],
                    "titulo_cat": event_row["titulo_cat"],
                    "descripcion_larga_es": event_row.get("descripcion_larga_es"),
                    "descripcion_larga_cat": event_row.get("descripcion_larga_cat"),
                    "cp": event_row["cp"],
                    "poblacion": event_row["poblacion"],
                    "lugar": event_row["lugar"],
                    "direccion": event_row.get("direccion"),
                    "coordenadas": _coordenadas_from_db(event_row.get("coordenadas_json")),
                    "tipo_organizador": event_row.get("tipo_organizador"),
                    "organizador": event_row.get("organizador"),
                    "organizador_web": event_row.get("organizador_web"),
                    "es_gratuito": bool(event_row["es_gratuito"]),
                    "precio": float(event_row["precio"])
                    if event_row.get("precio") is not None
                    else None,
                    "imagen_url": event_row.get("imagen_url"),
                    "fuente_url_original": event_row.get("fuente_url_original"),
                    "tags_es": tags_es,
                    "tags_cat": tags_cat,
                    "estado": event_row["estado"],
                    "fecha_creacion": str(event_row["fecha_creacion"])
                    if event_row.get("fecha_creacion")
                    else None,
                    "link_entradas_inscripcion": event_row.get("link_entradas_inscripcion"),
                    "requiere_inscripcion": bool(event_row["requiere_inscripcion"])
                    if event_row.get("requiere_inscripcion") is not None
                    else None,
                    "horarios": [
                        {
                            "fecha_inicio": str(r["fecha_inicio"]) if r.get("fecha_inicio") else None,
                            "fecha_fin": str(r["fecha_fin"]) if r.get("fecha_fin") else None,
                            "hora_inicio": str(r["hora_inicio"]) if r.get("hora_inicio") else None,
                            "hora_fin": str(r["hora_fin"]) if r.get("hora_fin") else None,
                            "es_recurrente": bool(r["es_recurrente"]),
                            "recurrencia": r.get("recurrencia"),
                        }
                        for r in schedule_rows
                    ],
                    "categorias": [
                        {
                            "id": r["id"],
                            "slug": r["slug"],
                            "nombre_es": r["nombre_es"],
                            "nombre_cat": r["nombre_cat"],
                            "color_hex": r.get("color_hex"),
                            "icono": r.get("icono"),
                        }
                        for r in category_rows
                    ],
                }

                solo = [event]
                await _attach_imagenes(conn, solo)

                return solo[0]

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting event details: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving event details",
        )
