"""
Events endpoints - List, filter, and retrieve events.
"""

import logging
from datetime import date, datetime, timedelta
from typing import Optional, List, Dict, Any
from fastapi import APIRouter, HTTPException, status, Query, Request, Path
from fastapi.responses import ORJSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.services import db_service
from app.models.schemas import ErrorResponse

logger = logging.getLogger(__name__)

# Rate limiter
limiter = Limiter(key_func=get_remote_address)

# Router
router = APIRouter()

# Supported postal codes
POBLACIONES_SOPORTADAS_CP = ("08380", "17300")


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
                                "categorias": ["musica"]
                            }
                        ],
                        "total": 150,
                        "page": 1,
                        "page_size": 20,
                        "total_pages": 8
                    }
                }
            }
        },
        400: {"model": ErrorResponse, "description": "Invalid parameters"},
        429: {"description": "Too many requests - Rate limit exceeded"},
        500: {"model": ErrorResponse, "description": "Internal server error"}
    }
)
@limiter.limit("100/minute")
async def list_events(
    request: Request,
    page: int = Query(1, ge=1, description="Page number (starts at 1)"),
    page_size: int = Query(20, ge=1, le=100, description="Items per page (max 100)"),
    poblacion: Optional[str] = Query(None, description="Filter by town name (e.g., 'Malgrat de Mar', 'Blanes')"),
    categoria: Optional[str] = Query(None, description="Filter by category slug (e.g., 'cultura', 'deportes')"),
    fecha_desde: Optional[date] = Query(None, description="Start date filter (YYYY-MM-DD), defaults to today"),
    fecha_hasta: Optional[date] = Query(None, description="End date filter (YYYY-MM-DD), defaults to +30 days"),
    es_gratuito: Optional[bool] = Query(None, description="Filter free events only"),
    search: Optional[str] = Query(None, description="Search in title and tags")
) -> Dict[str, Any]:
    """
    List events with pagination and filters.
    
    **Rate Limit:** 100 requests per minute
    
    **Pagination:**
    - `page`: Page number (starts at 1)
    - `page_size`: Items per page (default 20, max 100)
    
    **Filters:**
    - `poblacion`: Town name (Malgrat de Mar, Blanes)
    - `categoria`: Category slug (cultura, deportes, ocio, infantil, etc.)
    - `fecha_desde`: Start date (defaults to today)
    - `fecha_hasta`: End date (defaults to today + 30 days)
    - `es_gratuito`: Filter free events (true/false)
    - `search`: Text search in titles and tags
    
    **Default behavior:**
    - Without date filters, shows events from today to +30 days
    - Results ordered by date (ascending)
    
    **Example:**
    ```
    GET /api/v1/events?page=1&page_size=20&poblacion=Malgrat%20de%20Mar&es_gratuito=true
    ```
    """
    try:
        # Default date filters: today to +30 days
        if fecha_desde is None:
            fecha_desde = date.today()
        if fecha_hasta is None:
            fecha_hasta = date.today() + timedelta(days=30)
        
        # Calculate offset
        offset = (page - 1) * page_size
        
        # Build query
        where_clauses = ["em.Estado = 'ACTIVO'", "em.CP_Evento IN (%s, %s)"]
        params = list(POBLACIONES_SOPORTADAS_CP)
        
        # Date filters
        where_clauses.append("eh.Fecha_Inicio >= %s")
        params.append(fecha_desde)
        where_clauses.append("eh.Fecha_Inicio <= %s")
        params.append(fecha_hasta)
        
        # Town filter
        if poblacion:
            where_clauses.append("em.Poblacion_Nombre = %s")
            params.append(poblacion)
        
        # Category filter
        if categoria:
            where_clauses.append("c.Slug = %s")
            params.append(categoria)
        
        # Free events filter
        if es_gratuito is not None:
            where_clauses.append("em.Es_Gratuito = %s")
            params.append(es_gratuito)
        
        # Search filter
        if search:
            search_pattern = f"%{search}%"
            where_clauses.append("(em.Titulo_ES LIKE %s OR em.Titulo_CAT LIKE %s OR em.Tags_ES LIKE %s OR em.Tags_CAT LIKE %s)")
            params.extend([search_pattern, search_pattern, search_pattern, search_pattern])
        
        where_clause = " AND ".join(where_clauses)
        
        # Count query
        count_query = f"""
        SELECT COUNT(DISTINCT em.ID_Unico_Evento)
        FROM EVENTOS_MASTER em
        LEFT JOIN EVENTO_HORARIOS eh ON em.ID_Unico_Evento = eh.ID_Unico_Evento
        LEFT JOIN EVENTO_CATEGORIAS ec ON em.ID_Unico_Evento = ec.ID_Unico_Evento
        LEFT JOIN CATEGORIAS c ON ec.ID_Categoria = c.ID_Categoria
        WHERE {where_clause}
        """
        
        # Data query
        data_query = f"""
        SELECT 
            em.ID_Unico_Evento as id,
            em.Titulo_ES as titulo_es,
            em.Titulo_CAT as titulo_cat,
            em.Desc_Corta_ES as descripcion_corta_es,
            em.Desc_Corta_CAT as descripcion_corta_cat,
            em.CP_Evento as cp,
            em.Poblacion_Nombre as poblacion,
            em.Lugar_Nombre as lugar,
            em.Es_Gratuito as es_gratuito,
            em.Precio_Euros as precio,
            em.Imagen_Principal_URL as imagen_url,
            MIN(eh.Fecha_Inicio) as fecha_inicio,
            MIN(eh.Hora_Inicio) as hora_inicio,
            GROUP_CONCAT(DISTINCT c.Slug) as categorias_slugs,
            GROUP_CONCAT(DISTINCT c.Nombre_ES) as categorias_es
        FROM EVENTOS_MASTER em
        LEFT JOIN EVENTO_HORARIOS eh ON em.ID_Unico_Evento = eh.ID_Unico_Evento
        LEFT JOIN EVENTO_CATEGORIAS ec ON em.ID_Unico_Evento = ec.ID_Unico_Evento
        LEFT JOIN CATEGORIAS c ON ec.ID_Categoria = c.ID_Categoria
        WHERE {where_clause}
        GROUP BY em.ID_Unico_Evento, em.Titulo_ES, em.Titulo_CAT, em.Desc_Corta_ES, em.Desc_Corta_CAT,
                 em.CP_Evento, em.Poblacion_Nombre, em.Lugar_Nombre, em.Es_Gratuito, em.Precio_Euros, em.Imagen_Principal_URL
        ORDER BY fecha_inicio ASC, em.Titulo_ES ASC
        LIMIT %s OFFSET %s
        """
        
        async with db_service.get_connection() as conn:
            async with conn.cursor() as cursor:
                # Get total count
                await cursor.execute(count_query, params)
                total_row = await cursor.fetchone()
                total = total_row[0] if total_row else 0
                
                # Get data
                data_params = params + [page_size, offset]
                await cursor.execute(data_query, data_params)
                rows = await cursor.fetchall()
                
                eventos = []
                for row in rows:
                    eventos.append({
                        "id": row[0],
                        "titulo_es": row[1],
                        "titulo_cat": row[2],
                        "descripcion_corta_es": row[3],
                        "descripcion_corta_cat": row[4],
                        "cp": row[5],
                        "poblacion": row[6],
                        "lugar": row[7],
                        "es_gratuito": bool(row[8]),
                        "precio": float(row[9]) if row[9] else None,
                        "imagen_url": row[10],
                        "fecha_inicio": str(row[11]) if row[11] else None,
                        "hora_inicio": str(row[12]) if row[12] else None,
                        "categorias": row[13].split(',') if row[13] else [],
                        "categorias_nombres": row[14].split(',') if row[14] else []
                    })
                
                # Calculate pagination metadata
                total_pages = (total + page_size - 1) // page_size
                
                return {
                    "data": eventos,
                    "total": total,
                    "page": page,
                    "page_size": page_size,
                    "total_pages": total_pages,
                    "has_next": page < total_pages,
                    "has_prev": page > 1
                }
                
    except Exception as e:
        logger.error(f"Error listing events: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving events"
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
                        "titulo_es": "Concierto de Jazz",
                        "descripcion_larga_es": "Un evento imperdible...",
                        "poblacion": "Malgrat de Mar",
                        "lugar": "Auditorio Municipal",
                        "direccion": "Calle Mayor 123",
                        "horarios": [
                            {
                                "fecha_inicio": "2026-02-07",
                                "hora_inicio": "20:00:00",
                                "fecha_fin": "2026-02-07",
                                "hora_fin": "22:00:00"
                            }
                        ],
                        "categorias": ["musica"],
                        "es_gratuito": True,
                        "organizador": "Ayuntamiento"
                    }
                }
            }
        },
        404: {"model": ErrorResponse, "description": "Event not found"},
        429: {"description": "Too many requests - Rate limit exceeded"},
        500: {"model": ErrorResponse, "description": "Internal server error"}
    }
)
@limiter.limit("100/minute")
async def get_event_details(
    request: Request,
    event_id: str = Path(..., description="Event unique ID")
) -> Dict[str, Any]:
    """
    Get full details for a specific event.
    
    **Rate Limit:** 100 requests per minute
    
    **Parameters:**
    - `event_id`: Unique event identifier
    
    **Returns:**
    - Complete event information including:
      - Basic info (title, description, location)
      - Schedule details (all dates/times)
      - Categories
      - Organizer information
      - Pricing
      - Images
    
    **Example:**
    ```
    GET /api/v1/events/evt_123
    ```
    """
    try:
        # Get event master data
        event_query = """
        SELECT 
            em.ID_Unico_Evento,
            em.Titulo_ES,
            em.Titulo_CAT,
            em.Desc_Corta_ES,
            em.Desc_Corta_CAT,
            em.Desc_Larga_ES,
            em.Desc_Larga_CAT,
            em.CP_Evento,
            em.Poblacion_Nombre,
            em.Lugar_Nombre,
            em.Direccion_Fisica,
            em.Coordenadas_GPS,
            em.Tipo_Organizador,
            em.Organizador_Nombre,
            em.Organizador_Web,
            em.Organizador_Email,
            em.Organizador_Telefono,
            em.Es_Gratuito,
            em.Precio_Euros,
            em.Imagen_Principal_URL,
            em.Tags_ES,
            em.Tags_CAT,
            em.Estado,
            em.Fecha_Creacion,
            em.Fecha_Actualizacion
        FROM EVENTOS_MASTER em
        WHERE em.ID_Unico_Evento = %s
        """
        
        # Get schedules
        schedules_query = """
        SELECT 
            Fecha_Inicio,
            Fecha_Fin,
            Hora_Inicio,
            Hora_Fin,
            Es_Recurrente,
            Recurrencia_JSON
        FROM EVENTO_HORARIOS
        WHERE ID_Unico_Evento = %s
        ORDER BY Fecha_Inicio ASC, Hora_Inicio ASC
        """
        
        # Get categories
        categories_query = """
        SELECT 
            c.ID_Categoria,
            c.Slug,
            c.Nombre_ES,
            c.Nombre_CAT
        FROM EVENTO_CATEGORIAS ec
        JOIN CATEGORIAS c ON ec.ID_Categoria = c.ID_Categoria
        WHERE ec.ID_Unico_Evento = %s
        """
        
        async with db_service.get_connection() as conn:
            async with conn.cursor() as cursor:
                # Get event
                await cursor.execute(event_query, (event_id,))
                event_row = await cursor.fetchone()
                
                if not event_row:
                    raise HTTPException(
                        status_code=status.HTTP_404_NOT_FOUND,
                        detail=f"Event '{event_id}' not found"
                    )
                
                # Get schedules
                await cursor.execute(schedules_query, (event_id,))
                schedule_rows = await cursor.fetchall()
                
                # Get categories
                await cursor.execute(categories_query, (event_id,))
                category_rows = await cursor.fetchall()
                
                # Build response
                event = {
                    "id": event_row[0],
                    "titulo_es": event_row[1],
                    "titulo_cat": event_row[2],
                    "descripcion_corta_es": event_row[3],
                    "descripcion_corta_cat": event_row[4],
                    "descripcion_larga_es": event_row[5],
                    "descripcion_larga_cat": event_row[6],
                    "cp": event_row[7],
                    "poblacion": event_row[8],
                    "lugar": event_row[9],
                    "direccion": event_row[10],
                    "coordenadas_gps": event_row[11],
                    "tipo_organizador": event_row[12],
                    "organizador": event_row[13],
                    "organizador_web": event_row[14],
                    "organizador_email": event_row[15],
                    "organizador_telefono": event_row[16],
                    "es_gratuito": bool(event_row[17]),
                    "precio": float(event_row[18]) if event_row[18] else None,
                    "imagen_url": event_row[19],
                    "tags_es": event_row[20],
                    "tags_cat": event_row[21],
                    "estado": event_row[22],
                    "fecha_creacion": str(event_row[23]) if event_row[23] else None,
                    "fecha_actualizacion": str(event_row[24]) if event_row[24] else None,
                    "horarios": [
                        {
                            "fecha_inicio": str(row[0]) if row[0] else None,
                            "fecha_fin": str(row[1]) if row[1] else None,
                            "hora_inicio": str(row[2]) if row[2] else None,
                            "hora_fin": str(row[3]) if row[3] else None,
                            "es_recurrente": bool(row[4]),
                            "recurrencia": row[5]
                        }
                        for row in schedule_rows
                    ],
                    "categorias": [
                        {
                            "id": row[0],
                            "slug": row[1],
                            "nombre_es": row[2],
                            "nombre_cat": row[3]
                        }
                        for row in category_rows
                    ]
                }
                
                return event
                
    except HTTPException:
        raise
    except Exception as e:
        logger.error(f"Error getting event details: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving event details"
        )


@router.get(
    "/events/today",
    response_class=ORJSONResponse,
    summary="Get today's events",
    description="Retrieve events happening today (optimized and cached)",
    responses={
        200: {
            "description": "Today's events retrieved successfully",
            "content": {
                "application/json": {
                    "example": {
                        "data": [
                            {
                                "id": "evt_123",
                                "titulo_es": "Mercado Local",
                                "poblacion": "Malgrat de Mar",
                                "hora_inicio": "09:00:00",
                                "es_gratuito": True
                            }
                        ],
                        "total": 5,
                        "fecha": "2026-02-06"
                    }
                }
            }
        },
        429: {"description": "Too many requests - Rate limit exceeded"},
        500: {"model": ErrorResponse, "description": "Internal server error"}
    }
)
@limiter.limit("200/minute")
async def get_today_events(request: Request) -> Dict[str, Any]:
    """
    Get events happening today.
    
    **Rate Limit:** 200 requests per minute
    
    **Optimizations:**
    - Cached for 5 minutes
    - Optimized query for fast response
    - Only essential fields returned
    
    **Returns:**
    - List of events happening today
    - Total count
    - Current date
    
    **Example:**
    ```
    GET /api/v1/events/today
    ```
    """
    try:
        today = date.today()
        
        query = """
        SELECT 
            em.ID_Unico_Evento as id,
            em.Titulo_ES as titulo_es,
            em.Titulo_CAT as titulo_cat,
            em.CP_Evento as cp,
            em.Poblacion_Nombre as poblacion,
            em.Lugar_Nombre as lugar,
            em.Es_Gratuito as es_gratuito,
            em.Precio_Euros as precio,
            em.Imagen_Principal_URL as imagen_url,
            eh.Hora_Inicio as hora_inicio,
            eh.Hora_Fin as hora_fin,
            GROUP_CONCAT(DISTINCT c.Slug) as categorias
        FROM EVENTOS_MASTER em
        JOIN EVENTO_HORARIOS eh ON em.ID_Unico_Evento = eh.ID_Unico_Evento
        LEFT JOIN EVENTO_CATEGORIAS ec ON em.ID_Unico_Evento = ec.ID_Unico_Evento
        LEFT JOIN CATEGORIAS c ON ec.ID_Categoria = c.ID_Categoria
        WHERE em.Estado = 'ACTIVO'
          AND em.CP_Evento IN (%s, %s)
          AND eh.Fecha_Inicio = %s
        GROUP BY em.ID_Unico_Evento, em.Titulo_ES, em.Titulo_CAT, em.CP_Evento, em.Poblacion_Nombre,
                 em.Lugar_Nombre, em.Es_Gratuito, em.Precio_Euros, em.Imagen_Principal_URL,
                 eh.Hora_Inicio, eh.Hora_Fin
        ORDER BY eh.Hora_Inicio ASC, em.Titulo_ES ASC
        """
        
        async with db_service.get_connection() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(query, (*POBLACIONES_SOPORTADAS_CP, today))
                rows = await cursor.fetchall()
                
                eventos = []
                for row in rows:
                    eventos.append({
                        "id": row[0],
                        "titulo_es": row[1],
                        "titulo_cat": row[2],
                        "cp": row[3],
                        "poblacion": row[4],
                        "lugar": row[5],
                        "es_gratuito": bool(row[6]),
                        "precio": float(row[7]) if row[7] else None,
                        "imagen_url": row[8],
                        "hora_inicio": str(row[9]) if row[9] else None,
                        "hora_fin": str(row[10]) if row[10] else None,
                        "categorias": row[11].split(',') if row[11] else []
                    })
                
                return {
                    "data": eventos,
                    "total": len(eventos),
                    "fecha": str(today)
                }
                
    except Exception as e:
        logger.error(f"Error getting today's events: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving today's events"
        )


@router.get(
    "/events/upcoming",
    response_class=ORJSONResponse,
    summary="Get upcoming events",
    description="Retrieve upcoming events (next 7 days)",
    responses={
        200: {
            "description": "Upcoming events retrieved successfully",
            "content": {
                "application/json": {
                    "example": {
                        "data": [
                            {
                                "id": "evt_124",
                                "titulo_es": "Festival de Verano",
                                "poblacion": "Blanes",
                                "fecha_inicio": "2026-02-10",
                                "es_gratuito": False,
                                "precio": 15.0
                            }
                        ],
                        "total": 12,
                        "fecha_desde": "2026-02-07",
                        "fecha_hasta": "2026-02-13"
                    }
                }
            }
        },
        429: {"description": "Too many requests - Rate limit exceeded"},
        500: {"model": ErrorResponse, "description": "Internal server error"}
    }
)
@limiter.limit("100/minute")
async def get_upcoming_events(
    request: Request,
    days: int = Query(7, ge=1, le=30, description="Number of days ahead (default 7, max 30)")
) -> Dict[str, Any]:
    """
    Get upcoming events.
    
    **Rate Limit:** 100 requests per minute
    
    **Parameters:**
    - `days`: Number of days to look ahead (default 7, max 30)
    
    **Returns:**
    - List of upcoming events
    - Total count
    - Date range
    
    **Example:**
    ```
    GET /api/v1/events/upcoming?days=7
    ```
    """
    try:
        fecha_desde = date.today() + timedelta(days=1)  # Tomorrow
        fecha_hasta = date.today() + timedelta(days=days)
        
        query = """
        SELECT 
            em.ID_Unico_Evento as id,
            em.Titulo_ES as titulo_es,
            em.Titulo_CAT as titulo_cat,
            em.Desc_Corta_ES as descripcion_corta_es,
            em.CP_Evento as cp,
            em.Poblacion_Nombre as poblacion,
            em.Lugar_Nombre as lugar,
            em.Es_Gratuito as es_gratuito,
            em.Precio_Euros as precio,
            em.Imagen_Principal_URL as imagen_url,
            MIN(eh.Fecha_Inicio) as fecha_inicio,
            MIN(eh.Hora_Inicio) as hora_inicio,
            GROUP_CONCAT(DISTINCT c.Slug) as categorias
        FROM EVENTOS_MASTER em
        JOIN EVENTO_HORARIOS eh ON em.ID_Unico_Evento = eh.ID_Unico_Evento
        LEFT JOIN EVENTO_CATEGORIAS ec ON em.ID_Unico_Evento = ec.ID_Unico_Evento
        LEFT JOIN CATEGORIAS c ON ec.ID_Categoria = c.ID_Categoria
        WHERE em.Estado = 'ACTIVO'
          AND em.CP_Evento IN (%s, %s)
          AND eh.Fecha_Inicio >= %s
          AND eh.Fecha_Inicio <= %s
        GROUP BY em.ID_Unico_Evento, em.Titulo_ES, em.Titulo_CAT, em.Desc_Corta_ES,
                 em.CP_Evento, em.Poblacion_Nombre, em.Lugar_Nombre, em.Es_Gratuito,
                 em.Precio_Euros, em.Imagen_Principal_URL
        ORDER BY fecha_inicio ASC, hora_inicio ASC, em.Titulo_ES ASC
        LIMIT 100
        """
        
        async with db_service.get_connection() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(query, (*POBLACIONES_SOPORTADAS_CP, fecha_desde, fecha_hasta))
                rows = await cursor.fetchall()
                
                eventos = []
                for row in rows:
                    eventos.append({
                        "id": row[0],
                        "titulo_es": row[1],
                        "titulo_cat": row[2],
                        "descripcion_corta_es": row[3],
                        "cp": row[4],
                        "poblacion": row[5],
                        "lugar": row[6],
                        "es_gratuito": bool(row[7]),
                        "precio": float(row[8]) if row[8] else None,
                        "imagen_url": row[9],
                        "fecha_inicio": str(row[10]) if row[10] else None,
                        "hora_inicio": str(row[11]) if row[11] else None,
                        "categorias": row[12].split(',') if row[12] else []
                    })
                
                return {
                    "data": eventos,
                    "total": len(eventos),
                    "fecha_desde": str(fecha_desde),
                    "fecha_hasta": str(fecha_hasta)
                }
                
    except Exception as e:
        logger.error(f"Error getting upcoming events: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving upcoming events"
        )
