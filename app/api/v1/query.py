"""
Query endpoint - Natural language event search.
"""

import logging
from fastapi import APIRouter, HTTPException, status, Request
from fastapi.responses import ORJSONResponse
from slowapi import Limiter
from slowapi.util import get_remote_address

from app.models.schemas import QueryRequest, QueryResponse, ErrorResponse
from app.services import events_service

logger = logging.getLogger(__name__)

# Rate limiter
limiter = Limiter(key_func=get_remote_address)

# Router
router = APIRouter()


@router.post(
    "/query",
    response_model=QueryResponse,
    response_class=ORJSONResponse,
    summary="Search events with natural language",
    description="Search events using natural language queries. Supports Spanish and Catalan.",
    responses={
        200: {
            "description": "Events found successfully",
            "content": {
                "application/json": {
                    "example": {
                        "respuesta_texto": "He encontrado 5 eventos para ti este fin de semana...",
                        "eventos": [
                            {
                                "id": "evt_123",
                                "titulo_es": "Concierto de Jazz",
                                "poblacion": "Malgrat de Mar",
                                "fecha_inicio": "2026-02-07",
                                "es_gratuito": True
                            }
                        ],
                        "total": 5,
                        "idioma_respuesta": "es"
                    }
                }
            }
        },
        400: {"model": ErrorResponse, "description": "Invalid request"},
        429: {"description": "Too many requests - Rate limit exceeded"},
        500: {"model": ErrorResponse, "description": "Internal server error"}
    }
)
@limiter.limit("30/minute")
async def query_events(request: Request, query_request: QueryRequest) -> QueryResponse:
    """
    Search events using natural language.
    
    **Rate Limit:** 30 requests per minute
    
    **Request Body:**
    - `pregunta` (required): Natural language query in Spanish or Catalan
    - `cp_usuario` (optional): User postal code (08380 for Malgrat, 17300 for Blanes)
    - `debug` (optional): Enable debug mode for detailed information
    
    **Example Request:**
    ```json
    {
        "pregunta": "¿Qué hacer este fin de semana?",
        "cp_usuario": "08380",
        "debug": false
    }
    ```
    
    **Response:**
    - `respuesta_texto`: Natural language response with event recommendations
    - `eventos`: List of matching events with full details
    - `total`: Number of events found
    - `idioma_respuesta`: Response language (es/cat)
    """
    try:
        logger.info(f"POST /api/v1/query - pregunta: '{query_request.pregunta}', cp: {query_request.cp_usuario}")
        
        # Process search
        response = await events_service.search_events(query_request)
        
        logger.info(f"Search completed: {response.total} events found")
        
        return response
        
    except ValueError as e:
        logger.error(f"Validation error: {e}")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=str(e)
        )
    except Exception as e:
        logger.error(f"Internal error: {e}", exc_info=True)
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Internal server error"
        )
