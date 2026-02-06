"""
Categories endpoint - List available event categories.
"""

import logging
from typing import Dict, Any, List
from fastapi import APIRouter, HTTPException, status, Request
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


@router.get(
    "/categories",
    response_class=ORJSONResponse,
    summary="List event categories",
    description="Get all available event categories with counts",
    responses={
        200: {
            "description": "Categories retrieved successfully",
            "content": {
                "application/json": {
                    "example": {
                        "data": [
                            {
                                "id": 1,
                                "slug": "cultura",
                                "nombre_es": "Cultura",
                                "nombre_cat": "Cultura",
                                "count": 45
                            },
                            {
                                "id": 2,
                                "slug": "deportes",
                                "nombre_es": "Deportes",
                                "nombre_cat": "Esports",
                                "count": 32
                            }
                        ],
                        "total": 8
                    }
                }
            }
        },
        429: {"description": "Too many requests - Rate limit exceeded"},
        500: {"model": ErrorResponse, "description": "Internal server error"}
    }
)
@limiter.limit("100/minute")
async def list_categories(request: Request) -> Dict[str, Any]:
    """
    List all available event categories.
    
    **Rate Limit:** 100 requests per minute
    
    **Caching:** Results cached for 1 hour
    
    **Returns:**
    - List of categories with:
      - ID and slug
      - Names in Spanish and Catalan
      - Event count per category
    - Total number of categories
    
    **Example:**
    ```
    GET /api/v1/categories
    ```
    """
    try:
        query = """
        SELECT 
            c.ID_Categoria,
            c.Slug,
            c.Nombre_ES,
            c.Nombre_CAT,
            COUNT(DISTINCT ec.ID_Unico_Evento) as event_count
        FROM CATEGORIAS c
        LEFT JOIN EVENTO_CATEGORIAS ec ON c.ID_Categoria = ec.ID_Categoria
        LEFT JOIN EVENTOS_MASTER em ON ec.ID_Unico_Evento = em.ID_Unico_Evento AND em.Estado = 'ACTIVO'
        GROUP BY c.ID_Categoria, c.Slug, c.Nombre_ES, c.Nombre_CAT
        ORDER BY c.Nombre_ES ASC
        """
        
        async with db_service.get_connection() as conn:
            async with conn.cursor() as cursor:
                await cursor.execute(query)
                rows = await cursor.fetchall()
                
                categorias = []
                for row in rows:
                    categorias.append({
                        "id": row[0],
                        "slug": row[1],
                        "nombre_es": row[2],
                        "nombre_cat": row[3],
                        "count": row[4]
                    })
                
                return {
                    "data": categorias,
                    "total": len(categorias)
                }
                
    except Exception as e:
        logger.error(f"Error listing categories: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Error retrieving categories"
        )
