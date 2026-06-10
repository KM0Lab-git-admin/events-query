"""
News endpoints - List and detail of municipal news (NOTICIAS_MASTER).

Las noticias las puebla el pipeline de ingesta (scripts/ingest_all.py, modo BD)
clasificando el contenido de webs oficiales, agregadores y redes sociales.
Solo se exponen las ACTIVAS (las caducadas pasan a ARCHIVADA y desaparecen).
"""

import json
import logging
from typing import Dict, Any, Optional

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import ORJSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.services import db_service
from app.models.schemas import ErrorResponse

logger = logging.getLogger(__name__)

limiter = Limiter(key_func=get_remote_address)

router = APIRouter()


def _parse_tags(raw) -> list:
    if not raw:
        return []
    try:
        return json.loads(raw) if isinstance(raw, str) else list(raw)
    except (ValueError, TypeError):
        return []


def _row_to_news(row) -> Dict[str, Any]:
    return {
        "id": row[0],
        "ciudad": row[1],
        "titulo_cat": row[2],
        "titulo_es": row[3],
        "cuerpo_cat": row[4],
        "cuerpo_es": row[5],
        "tags_cat": _parse_tags(row[6]),
        "tags_es": _parse_tags(row[7]),
        "fecha_publicacion": row[8].isoformat() if row[8] else None,
        "imagen_principal_url": row[9],
        "fuente_url_original": row[10],
        "idioma_origen": row[11],
    }


_SELECT_NEWS = """
    SELECT n.ID_Unico_Noticia, c.Nombre, n.Titulo_CAT, n.Titulo_ES,
           n.Cuerpo_CAT, n.Cuerpo_ES, n.Tags_CAT, n.Tags_ES,
           n.Fecha_Publicacion, n.Imagen_Principal_URL,
           n.Fuente_URL_Original, n.Idioma_Origen
    FROM NOTICIAS_MASTER n
    JOIN CIUDADES c ON c.ID_Ciudad = n.ID_Ciudad
    WHERE n.Estado = 'ACTIVA'
"""


@router.get(
    "/news",
    response_class=ORJSONResponse,
    summary="List municipal news",
    description="Get active municipal news, newest first, optionally filtered by city",
    responses={
        200: {"description": "News retrieved successfully"},
        429: {"description": "Too many requests - Rate limit exceeded"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
@limiter.limit("100/minute")
async def list_news(
    request: Request,
    city: Optional[str] = Query(None, description="Filtrar por nombre de ciudad (ej: 'Malgrat de Mar')"),
    limit: int = Query(20, ge=1, le=100, description="Máximo de noticias a devolver"),
    offset: int = Query(0, ge=0, description="Desplazamiento para paginación"),
) -> Dict[str, Any]:
    """
    List active municipal news, newest first.

    **Rate Limit:** 100 requests per minute

    **Example:**
    ```
    GET /api/v1/news?city=Malgrat de Mar&limit=10
    ```
    """
    try:
        query = _SELECT_NEWS
        params = []
        if city:
            query += " AND c.Nombre = %s"
            params.append(city)
        query += " ORDER BY n.Fecha_Publicacion DESC, n.Fecha_Creacion DESC LIMIT %s OFFSET %s"
        params.extend([limit, offset])

        count_query = """
            SELECT COUNT(*) FROM NOTICIAS_MASTER n
            JOIN CIUDADES c ON c.ID_Ciudad = n.ID_Ciudad
            WHERE n.Estado = 'ACTIVA'
        """
        count_params = []
        if city:
            count_query += " AND c.Nombre = %s"
            count_params.append(city)

        async with db_service.get_connection() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(count_query, count_params)
                total = (await cursor.fetchone())[0]
                await cursor.execute(query, params)
                rows = await cursor.fetchall()

        return {
            "data": [_row_to_news(r) for r in rows],
            "total": total,
            "limit": limit,
            "offset": offset,
        }

    except Exception as e:
        logger.error(f"Error listing news: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving news",
        )


@router.get(
    "/news/{news_id}",
    response_class=ORJSONResponse,
    summary="Get news detail",
    description="Get a single active news item by its ID",
    responses={
        200: {"description": "News item retrieved successfully"},
        404: {"model": ErrorResponse, "description": "News item not found"},
        429: {"description": "Too many requests - Rate limit exceeded"},
        500: {"model": ErrorResponse, "description": "Internal server error"},
    },
)
@limiter.limit("100/minute")
async def get_news(request: Request, news_id: str) -> Dict[str, Any]:
    """
    Get a single active news item by ID.

    **Example:**
    ```
    GET /api/v1/news/3f2a...c9
    ```
    """
    try:
        query = _SELECT_NEWS + " AND n.ID_Unico_Noticia = %s"
        async with db_service.get_connection() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(query, [news_id])
                row = await cursor.fetchone()

        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="News item not found",
            )
        return {"data": _row_to_news(row)}

    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting news {news_id}: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving news item",
        )
